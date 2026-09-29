#!/usr/bin/env python3
"""Download public Pie sources, preserving partial progress before Free timeout."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

MANIFEST = 'b6d768250babf86854c5b0ff61547b111f05e48e'
ROOT = Path('/home/circleci/crdroid9-m6')
HERE = Path(__file__).resolve().parents[1]
EVIDENCE = HERE / 'evidence/crdroid9'
REPO = [sys.executable, str(HERE / 'scripts/repo-launcher')]


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def sync():
    ROOT.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    os.environ.update(GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
    for args in (['user.name', 'ReMeizu CI'], ['user.email', 'ci@users.noreply.github.com'],
                 ['url.https://github.com/.insteadOf', 'git://github.com/']):
        run(['git', 'config', '--global', *args])
    run(REPO + ['init', '-u', 'https://github.com/crdroidandroid/android.git',
                '-b', MANIFEST, '--depth=1', '--no-clone-bundle',
                '-g', 'default,-darwin', '--repo-rev=stable'], timeout=300)
    local = ROOT / '.repo/local_manifests'
    local.mkdir(exist_ok=True)
    shutil.copyfile(HERE / 'inputs/crdroid9-m6.xml', local / 'remeizu-m6.xml')
    command = REPO + ['sync', '-c', '-j4', '--no-tags', '--no-clone-bundle',
                      '--fail-fast', '--retry-fetches=2']
    started = time.monotonic()
    reason = None
    with (EVIDENCE / 'sync.log').open('w') as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        while process.poll() is None:
            free = shutil.disk_usage(ROOT).free
            elapsed = int(time.monotonic() - started)
            print(f'sync elapsed={elapsed}s free={free // 2**30}GiB', flush=True)
            if elapsed >= 1800 or free < 35 * 2**30:
                reason = 'checkpoint-time' if elapsed >= 1800 else 'disk-reserve'
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                break
            time.sleep(20)
    result = {'manifest_commit': MANIFEST, 'sync_exit': process.returncode,
              'stop_reason': reason, 'sync_complete': process.returncode == 0,
              'rom_started': False, 'lfs_payloads_verified': False,
              'free_bytes': shutil.disk_usage(ROOT).free,
              'elapsed_seconds': round(time.monotonic() - started),
              'missing_build_inputs': ['matching M6 common tree', 'prepared LOS16 vendor/MTK inputs',
                                       'matching prebuilt kernel', 'crDroid product adaptation']}
    if result['sync_complete']:
        run(REPO + ['manifest', '-r', '-o', str(EVIDENCE / 'resolved-manifest.xml')], timeout=120)
    (EVIDENCE / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copyfile(EVIDENCE / 'status.json', ROOT / 'sync-status.json')
    print(json.dumps(result, indent=2), flush=True)
    # Return normally so the next CI step can save an incomplete source cache.
    # The final validation step makes incomplete syncs visibly fail.


if __name__ == '__main__':
    sync()
