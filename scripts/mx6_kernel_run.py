#!/usr/bin/env python3
"""Fetch reviewed public MX6 inputs on an ephemeral cloud runner, then run Forge."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time

from kernel_forge import forge
from kernel_run import extract, fetch, output, run, verify_receipt
from kernel_build import require, sha
from mx6_kernel_build import OBJECTS, validate_pins, verify_inputs

HERE = Path(__file__).resolve().parents[1]


def required_artifacts():
    names = ['arch/arm64/boot/Image.gz-dtb', 'System.map', '.config', 'vmlinux',
             'kernel-build.log', 'kernel-proof.json', 'tool-versions.txt']
    for name in OBJECTS:
        path = Path(name)
        names.extend((name, str(path.with_name('.'+path.name+'.cmd'))))
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-mount', type=Path, required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    args = parser.parse_args()
    mount, receipt = args.scratch_mount, args.receipt_dir
    require(os.geteuid() == 0, 'root cloud preparer required; Forge uses non-root UID1001')
    require(mount.is_absolute() and mount.resolve() == mount and mount != Path('/'), 'noncanonical scratch mount')
    mounts = forge._mount_filesystems()
    require(mount in mounts and mounts[mount][1] in {'ext4', 'xfs'} and mounts[mount][0] != mounts[Path('/')][0],
            'distinct mounted ext4/xfs scratch filesystem required')
    require(shutil.disk_usage(mount).free > 6*1024**3, 'less than6GiB scratch available')
    require(receipt.is_absolute() and receipt.resolve() == receipt and not receipt.is_symlink(), 'unsafe receipt directory')
    receipt.mkdir(parents=True, exist_ok=True)
    require(not any(receipt.iterdir()), 'receipt directory must be new and empty')
    pins = json.loads((HERE/'recipes/mx6-wifi-inputs.json').read_text())
    validate_pins(pins)
    # A rerun in the same cloud run must not silently recreate a second job.
    job = mount/('remeizu-mx6-'+pins['kernel_commit'])
    job.mkdir()
    downloads, source = job/'downloads', job/'source'
    downloads.mkdir(); source.mkdir()
    start = time.monotonic()
    record = {'kind': 'public-mx6-kernel-preparation', 'kernel_input': None, 'toolchain_input': None,
              'full_kernel_linked': False, 'flash_ready': False, 'runtime_verified': False}

    def bounded_stop(signum, frame):
        raise TimeoutError('cloud preparation exceeded35minutes or was cancelled')

    previous = {s: signal.signal(s, bounded_stop) for s in (signal.SIGALRM, signal.SIGTERM)}
    signal.alarm(2100)
    try:
        for name in ('kernel', 'toolchain'):
            archive, provenance = fetch(downloads, name, pins[name+'_url'], pins[name+'_commit'], pins[name+'_tree'])
            extract(archive, source/name)
            record[name+'_input'] = provenance
        for name in ('aarch64-linux-android-gcc', 'aarch64-linux-android-g++'):
            path = source/'toolchain/bin'/name
            data = path.read_bytes()
            require(data.startswith(b'#!/usr/bin/python\n'), 'unexpected original compiler wrapper')
            path.write_bytes(data.replace(b'#!/usr/bin/python\n', b'#!/usr/bin/env python3\n', 1))
        verify_inputs(source, pins)
        tooling = source/'.forge'
        tooling.mkdir()
        for name in ('mx6_kernel_build.py', 'kernel_build.py'):
            shutil.copy2(HERE/'scripts'/name, tooling/name)
        shutil.copy2(HERE/'recipes/mx6-wifi-inputs.json', tooling/'mx6-wifi-inputs.json')
        run(['git', 'init', source])
        run(['git', '-C', source, 'add', '.forge'])
        env = dict(os.environ, GIT_AUTHOR_DATE='2026-09-30T00:00:00Z', GIT_COMMITTER_DATE='2026-09-30T00:00:00Z')
        run(['git', '-C', source, '-c', 'user.name=ReMeizu', '-c', 'user.email=build@remeizu.invalid',
             'commit', '-m', 'Pinned public MX6 kernel inputs'], env=env)
        run(['docker', 'pull', 'ubuntu:20.04'], timeout=240)
        base = json.loads(output(['docker', 'image', 'inspect', 'ubuntu:20.04']))[0]['RepoDigests'][0]
        require('@sha256:' in base, 'base image has no immutable digest')
        tag = 'androidforge/build-kernel:kernel-gcc49'
        run(['docker', 'build', '--build-arg', 'BASE_IMAGE='+base, '-f', HERE/'recipes/kernel-gcc49.Dockerfile',
             '-t', tag, HERE/'recipes'], timeout=600)
        image = output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'])
        record.update(base_image_digest=base, image_id=image,
                      dockerfile_sha256=sha(HERE/'recipes/kernel-gcc49.Dockerfile'),
                      launcher_sha256=sha(HERE/'vendor/forge/forge_ephemeral_build.py'), new_environment=True)
        # Leave enough time for Forge to stop its own container and save failure evidence.
        require(time.monotonic()-start < 720, 'source/image preparation left less than23minutes for Forge')
        recipe = {'image_tag': tag, 'image_id': image, 'build_env_key': 'kernel-gcc49',
                  'source_mount_path': str(source), 'output_dir_in_container': '/workspace/out',
                  'command': ['python3', '/workspace/src/.forge/mx6_kernel_build.py'],
                  'env': {'FORGE_KERNEL_JOBS': '4', 'KBUILD_BUILD_TIMESTAMP': '2026-09-30 00:00:00 UTC',
                          'KBUILD_BUILD_VERSION': '1'},
                  'idempotency_key': 'mx6-wifi-full-kernel-'+pins['kernel_commit'],
                  'timeout_seconds': 1320, 'execution_profile': 'cloud-mounted',
                  'scratch_mount_path': str(mount), 'container_user': '1001:1001',
                  'required_artifacts': required_artifacts()}
        model = forge.recipe_from_dict(recipe)
        record['recipe_hash'] = model.recipe_hash()
        recipe_file = receipt/'kernel-recipe.json'
        recipe_file.write_text(json.dumps(recipe, indent=2)+'\n')
        run([sys.executable, HERE/'scripts/kernel_forge.py', '--recipe', recipe_file, '--no-resume'],
            env=dict(os.environ, FORGE_EPHEMERAL_BASE=str(job/'evidence')), timeout=1380)
        record['success'] = verify_receipt(job/'evidence'/model.recipe_hash())
        proof = json.loads((job/'evidence'/model.recipe_hash()/'kernel-proof.json').read_text())
        require(proof.get('full_kernel_linked') is True and proof.get('error') is None,
                'Forge receipt lacks complete kernel proof')
        record['full_kernel_linked'] = True
    except Exception as exc:
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        signal.alarm(0)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        record['elapsed_seconds'] = round(time.monotonic()-start, 3)
        (receipt/'kernel-preparation.json').write_text(json.dumps(record, indent=2)+'\n')
        if (job/'evidence').exists():
            shutil.copytree(job/'evidence', receipt/'forge', dirs_exist_ok=False)
        # Keep this job's inputs/output until the ephemeral runner tears down.
        # Never unmount, format or remove another run's scratch/evidence.


if __name__ == '__main__':
    main()
