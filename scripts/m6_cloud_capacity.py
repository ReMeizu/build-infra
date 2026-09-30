#!/usr/bin/env python3
"""Small cloud-only inventory; no Android checkout, Docker start or benchmark."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def text_file(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def main():
    if (os.environ.get('CIRCLECI') != 'true' or
            os.environ.get('CIRCLE_PROJECT_USERNAME') != 'ReMeizu' or
            os.environ.get('CIRCLE_PROJECT_REPONAME') != 'build-infra' or
            os.environ.get('CIRCLE_BRANCH') != 'm6-circle-cloud-only'):
        raise RuntimeError('Inventory restricted to the authorized cloud job')
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        mem[key] = int(value.strip().split()[0]) * 1024
    # No IP, machine/volume serial, account credential or SSH endpoint in artifacts.
    disks = json.loads(subprocess.check_output(
        ['lsblk', '--json', '--bytes', '--output', 'NAME,TYPE,SIZE,ROTA,MODEL'],
        timeout=20, text=True))
    space = shutil.disk_usage('/home/circleci')
    report = {
        'schema': 'remeizu.m6.cloud-capacity.v1',
        'infra_commit': os.environ.get('CIRCLE_SHA1'),
        'job': os.environ.get('CIRCLE_BUILD_NUM'),
        'platform': platform.system(), 'architecture': platform.machine(),
        'affinity_cpus': len(os.sched_getaffinity(0)),
        'mem_total_bytes': mem['MemTotal'], 'mem_available_bytes': mem['MemAvailable'],
        'root_total_bytes': space.total, 'root_free_bytes': space.free,
        'system_vendor': text_file('/sys/class/dmi/id/sys_vendor'),
        'product_name': text_file('/sys/class/dmi/id/product_name'),
        'block_devices': disks['blockdevices'],
        'physical_ssd_proven': False,
        'ssd_note': 'Virtual ROTA/model is inventory, not provider disk-type proof.',
        'android_started': False, 'container_started': False,
    }
    report['capacity_minimum_pass'] = (
        report['platform'] == 'Linux' and report['architecture'] == 'x86_64' and
        report['affinity_cpus'] >= 4 and report['mem_available_bytes'] >= 10 * 2**30 and
        report['root_free_bytes'] >= 100 * 2**30)
    output = Path('evidence/m6-cloud-capacity')
    output.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, indent=2) + '\n'
    (output / 'capacity.json').write_text(raw)
    print(raw, flush=True)
    if not report['capacity_minimum_pass']:
        raise RuntimeError('Cloud capacity below preparation minimum')


if __name__ == '__main__':
    main()
