#!/usr/bin/env python3
"""Provision one NEW file-backed ext4 volume on an ephemeral CI runner.

Never format an existing file or block device. The backing file is on the
runner's ephemeral root disk, not a Blacksmith sticky disk. Forge still sees
and validates a distinct ext4 filesystem/device for its cloud-mounted profile.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

def run(argv):
    return subprocess.run(argv, check=True, timeout=45, capture_output=True, text=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner-temp', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not args.run_id.isdecimal():
        raise ValueError('root and a numeric GitHub run ID required')
    parent = args.runner_temp
    if not parent.is_absolute() or parent.resolve() != parent or not parent.is_dir():
        raise ValueError('runner temp must be an existing canonical directory')
    target = Path('/mnt/forge')
    if target.is_symlink() or target.parent.resolve() != target.parent:
        raise ValueError('mount path must not contain symlinks')
    check = subprocess.run(['findmnt', '--mountpoint', str(target), '-n'], capture_output=True, timeout=10)
    if check.returncode == 0:
        raise ValueError('existing mount must not be replaced')
    if check.returncode != 1:
        raise ValueError('cannot inspect existing mount')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('existing nonempty path must not be reused')
    size = 8 * 1024**3
    if shutil.disk_usage(parent).free < size + 12 * 1024**3:
        raise ValueError('insufficient ephemeral disk headroom')
    image = parent / ('remeizu-scratch-' + args.run_id + '.ext4')
    fd = os.open(image, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    try:
        os.ftruncate(fd, size)
        os.fsync(fd)
    finally:
        os.close(fd)
    target.mkdir(exist_ok=True)
    run(['mkfs.ext4', '-q', '-F', str(image)])
    run(['mount', '-t', 'ext4', '-o', 'loop,nodev,nosuid', str(image), str(target)])
    fs = run(['findmnt', '--mountpoint', str(target), '-n', '-o', 'FSTYPE']).stdout.strip()
    if fs != 'ext4' or target.stat().st_dev == Path('/').stat().st_dev:
        raise ValueError('distinct ext4 mount was not established')
    report = {'schema': 'remeizu.ephemeral-scratch.v1', 'run_id': args.run_id,
              'backing': 'new sparse regular file on the ephemeral runner root disk',
              'file': str(image), 'mount': str(target), 'virtual_bytes': size,
              'filesystem': fs, 'distinct_device': True, 'provider_sticky_storage': False}
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
