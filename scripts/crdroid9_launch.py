#!/usr/bin/env python3
"""Run one bounded ROM attempt through the preserved Forge launcher."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

infra = Path(__file__).resolve().parents[1]
mount = Path('/mnt/forge-circle-m6')
mount.mkdir(exist_ok=True)
image = Path('/home/circleci/forge-circle-m6.ext4')
assert not image.exists(), 'use an explicit resume recipe for an existing scratch disk'
subprocess.run(['truncate', '-s', '60G', str(image)], check=True)
subprocess.run(['mkfs.ext4', '-F', '-m', '0', str(image)], check=True)
subprocess.run(['mount', '-o', 'loop', str(image), str(mount)], check=True)
tag = 'androidforge/build-env:android-9'
image_id = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
recipe = {
    'image_tag': tag, 'image_id': image_id, 'build_env_key': 'android-9',
    'source_mount_path': '/home/circleci/crdroid9-m6',
    'execution_profile': 'cloud-mounted', 'scratch_mount_path': str(mount),
    'container_user': '1001:1001', 'output_dir_in_container': '/workspace/out',
    'idempotency_key': 'crdroid-pie-m6-circle-attempt1',
    'timeout_seconds': int(sys.argv[1]) if len(sys.argv) > 1 else 1200,
    'env': {'FORGE_ROM_BRANCH': 'lineage-16.0', 'FORGE_DEVICE': 'meizu_m6',
            'FORGE_OFFLINE_SOURCE_SNAPSHOT': '1'},
    'command': ['bash', '/workspace/src/.forge/run.sh'],
    'required_artifacts': ['rom-version.txt', 'boot.img', 'rom.zip', 'SHA256SUMS'],
}
(mount / 'recipe.json').write_text(json.dumps(recipe, indent=2) + '\n')
launcher = infra / 'vendor/forge/forge_ephemeral_build.py'
assert hashlib.sha256(launcher.read_bytes()).hexdigest() == '9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8'
env = dict(os.environ, FORGE_EPHEMERAL_BASE=str(mount / 'evidence'), GIT_CONFIG_COUNT='1',
           GIT_CONFIG_KEY_0='safe.directory', GIT_CONFIG_VALUE_0='*', GIT_OPTIONAL_LOCKS='0')
result = subprocess.run([sys.executable, str(launcher), '--recipe', str(mount / 'recipe.json'), '--verbose'], env=env)
(mount / 'attempt-result.json').write_text(json.dumps({'forge_exit': result.returncode, 'rom_complete': result.returncode == 0}) + '\n')
# Checkpoint stays private; the n8n controller retrieves this via existing SSH.
subprocess.run(['tar', '-C', str(mount), '-I', 'zstd -T2 -1', '-cf', '/home/circleci/m6-attempt1-checkpoint.tar.zst', '.'], check=True)
subprocess.run(['chown', 'circleci:circleci', '/home/circleci/m6-attempt1-checkpoint.tar.zst'], check=True)
raise SystemExit(result.returncode)
