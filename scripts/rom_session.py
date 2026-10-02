#!/usr/bin/env python3
"""Bound an SSH-operated ROM worker without publishing private build inputs.

Builds are submitted over the provider's authenticated SSH transport and run
through Forge. This process controls the worker lifetime, not ROM acceptance.
The operator retrieves private artifacts before writing the completion marker.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

MAX_SECONDS = 345 * 60
IDLE_SECONDS = 35 * 60


def read_completion(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
        raise ValueError('invalid completion marker')
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != {'status', 'artifacts_collected'}:
        raise ValueError('invalid completion schema')
    if data['status'] not in ('completed', 'failed', 'blocked'):
        raise ValueError('invalid completion status')
    if data['artifacts_collected'] is not True:
        raise ValueError('collect private artifacts before releasing the worker')
    return data


def session_budget(minutes):
    if not 1 <= minutes <= MAX_SECONDS // 60:
        raise ValueError('session must fit the existing maximum')
    return minutes * 60


def expiration(now, started, heartbeat, max_seconds=MAX_SECONDS):
    if now - started >= max_seconds:
        return 'session_deadline'
    if now - max(started, heartbeat) >= IDLE_SECONDS:
        return 'idle_deadline'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--max-minutes', type=int, default=225)
    args = parser.parse_args()
    max_seconds = session_budget(args.max_minutes)
    folder = args.session_dir
    if os.geteuid() != 0 or folder != Path('/mnt/forge/rom-session'):
        raise ValueError('use the allocated ROM scratch mount')
    mount = folder.parent
    check = subprocess.run(['findmnt', '--mountpoint', str(mount), '-n', '-o', 'FSTYPE'],
                           check=True, capture_output=True, text=True, timeout=10)
    if check.stdout.strip() != 'ext4' or mount.stat().st_dev == Path('/').stat().st_dev:
        raise ValueError('distinct ext4 scratch mount required')
    if shutil.disk_usage(mount).free < 500 * 1024**3:
        raise ValueError('less than 500 GiB scratch available')
    uid, gid = int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID'])
    if uid == 0 or gid == 0:
        raise ValueError('non-root SSH operator required')
    folder.mkdir(mode=0o700)
    os.chown(folder, uid, gid)
    started = time.monotonic()
    started_utc = datetime.datetime.now(datetime.timezone.utc)
    report = {'schema': 'remeizu.rom-session.v1', 'state': 'ready',
              'started_at': started_utc.isoformat(),
              'deadline': (started_utc + datetime.timedelta(seconds=max_seconds)).isoformat(),
              'cpus': os.cpu_count(), 'scratch_free_bytes': shutil.disk_usage(mount).free,
              'public_artifact_upload': False, 'rom_verified': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    ready = folder / 'ready.json'
    ready.write_text(json.dumps(report, indent=2) + '\n')
    os.chown(ready, uid, gid)
    print('ROM worker ready for authenticated SSH input; session is time limited.', flush=True)
    last_beat = started
    last_mtime = None
    reason = None
    rejected = False
    while True:
        now = time.monotonic()
        beat = folder / 'activity'
        try:
            info = beat.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                raise ValueError('invalid activity marker')
            if info.st_mtime_ns != last_mtime:
                last_mtime = info.st_mtime_ns
                last_beat = now
        except FileNotFoundError:
            pass
        reason = expiration(now, started, last_beat, max_seconds)
        if reason:
            break
        try:
            result = read_completion(folder / 'finished.json')
            reason = result['status']
            report.update(result)
            break
        except FileNotFoundError:
            pass
        except ValueError:
            if not rejected:
                print('Completion marker rejected; retaining worker until corrected or deadline.', flush=True)
                rejected = True
        time.sleep(10)
    report.update(state=reason, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('ROM worker closed: ' + reason, flush=True)
    return 0 if reason == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
