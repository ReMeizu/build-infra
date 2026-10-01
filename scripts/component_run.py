"""Prepare pinned public board inputs and run a full kernel build via Forge."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from component_manifest import artifacts, require, sha, validate
from component_forge import forge
from component_public import check_public_source
from kernel_run import extract, fetch, output, run, verify_receipt

HERE = Path(__file__).resolve().parents[1]


def report_failure(path):
    """Keep a bounded first-fatal context visible even before artifact download."""
    log = path / 'kernel-build.log'
    if log.is_file():
        lines = log.read_text(errors='replace').splitlines()
        for index, line in enumerate(lines):
            if re.search(r'error:|Error [0-9]|No rule|not found|fatal:', line):
                print('Kbuild failure context:\n' + '\n'.join(lines[max(0, index - 2):index + 5])[:4096], flush=True)
                return
    failure = path / 'FAILURE'
    if failure.is_file():
        print('Forge failure:\n' + failure.read_text()[:4096], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--scratch-mount', type=Path, required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    args = parser.parse_args()
    require(bool(re.fullmatch(r'[a-z0-9-]+', args.profile)), 'invalid profile name')
    profile = HERE / 'recipes/components' / (args.profile + '.json')
    require(profile.is_file() and not profile.is_symlink(), 'reviewed profile does not exist')
    m = validate(json.loads(profile.read_text()))
    mount, destination = args.scratch_mount, args.receipt_dir
    require(os.geteuid() == 0, 'host controller requires sudo; compilation uses UID1001')
    require(mount.is_absolute() and mount.resolve() == mount and mount != Path('/'), 'unsafe scratch mount')
    mounts = forge._mount_filesystems()
    require(mount in mounts and mounts[mount][1] in {'ext4', 'xfs'}
            and mounts[mount][0] != mounts[Path('/')][0], 'distinct ext4/xfs mounted scratch required')
    require(shutil.disk_usage(mount).free >= 8 * 1024**3, 'less than8GiB free scratch')
    require(destination.is_absolute() and destination.resolve() == destination and not destination.exists(), 'new canonical receipt directory required')
    destination.mkdir(parents=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + str(os.getpid())
    job = mount / ('kernel-component-' + stamp); job.mkdir()
    downloads = job / 'downloads'; downloads.mkdir()
    source = job / 'source'; source.mkdir()
    record = {'device': m['device'], 'profile_sha256': sha(profile),
              'full_kernel_linked': False, 'flash_ready': False, 'runtime_verified': False}
    try:
        record['anonymous_source_preflight'] = check_public_source(
            m['source']['url'], m['source']['commit'], m['source']['tree'])
        for name, key in (('kernel', 'source'), ('toolchain', 'toolchain')):
            item = m[key]
            archive, provenance = fetch(downloads, name, item['url'], item['commit'], item['tree'])
            extract(archive, source / name); record[key] = provenance
        if m['toolchain']['preparation'] == 'python3-wrappers':
            for name in ('aarch64-linux-android-gcc', 'aarch64-linux-android-g++'):
                path = source / 'toolchain/bin' / name
                data = path.read_bytes()
                require(data.startswith(b'#!/usr/bin/python\n'), 'compiler wrapper differs from reviewed original')
                path.write_bytes(data.replace(b'#!/usr/bin/python\n', b'#!/usr/bin/env python3\n', 1))
        elif m['toolchain']['preparation'] == 'elf-gcc-bfd':
            require((source / 'toolchain/bin/aarch64-linux-android-gcc').read_bytes()[:4] == b'\x7fELF', 'expected original ELF compiler')
        else:
            require((source / 'toolchain/bin/real-aarch64-linux-android-gcc').read_bytes()[:4] == b'\x7fELF', 'expected original real ELF compiler')
            require((source / 'toolchain/bin/aarch64-linux-android-ld').read_bytes()[:4] == b'\x7fELF', 'expected original ELF linker')
        for name, digest in m['toolchain']['bin_sha256'].items():
            require(sha(source / 'toolchain/bin' / name) == digest, 'compiler pin differs')
        tooling = source / '.forge'; tooling.mkdir()
        for name in ('component_manifest.py', 'component_compile.py'):
            shutil.copyfile(HERE / 'scripts' / name, tooling / name)
        shutil.copyfile(profile, tooling / 'profile.json')
        run(['git', 'init', '-q', source]); run(['git', '-C', source, 'add', '.forge'])
        run(['git', '-C', source, '-c', 'user.name=ReMeizu', '-c', 'user.email=build@remeizu.invalid',
             'commit', '-qm', 'Pin public board kernel build inputs'])
        run(['docker', 'pull', 'ubuntu:20.04'], timeout=300)
        base = json.loads(output(['docker', 'image', 'inspect', 'ubuntu:20.04']))[0]['RepoDigests'][0]
        require('@sha256:' in base, 'base container has no immutable digest')
        tag = 'androidforge/build-component:component-kernel-gcc49'
        dockerfile = HERE / 'recipes/component-gcc49.Dockerfile'
        run(['docker', 'build', '--build-arg', 'BASE_IMAGE=' + base, '-f', dockerfile,
             '-t', tag, HERE / 'recipes'], timeout=600)
        image = output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'])
        record.update(base_image_digest=base, image_id=image, dockerfile_sha256=sha(dockerfile),
                      launcher_sha256=sha(HERE / 'vendor/forge/forge_ephemeral_build.py'))
        recipe = {'image_tag': tag, 'image_id': image, 'build_env_key': 'component-kernel-gcc49',
                  'source_mount_path': str(source), 'output_dir_in_container': '/workspace/out',
                  'command': ['python3', '/workspace/src/.forge/component_compile.py'],
                  'env': {'FORGE_KERNEL_JOBS': str(m['jobs']), 'KBUILD_BUILD_TIMESTAMP': '2026-10-01 00:00:00 UTC',
                          'KBUILD_BUILD_VERSION': '1'}, 'idempotency_key': args.profile + '-' + stamp,
                  'timeout_seconds': m['timeout_seconds'] + 240, 'execution_profile': 'cloud-mounted',
                  'scratch_mount_path': str(mount), 'container_user': '1001:1001', 'required_artifacts': artifacts(m)}
        model = forge.recipe_from_dict(recipe); record['recipe_hash'] = model.recipe_hash()
        recipe_path = destination / 'kernel-recipe.json'
        recipe_path.write_text(json.dumps(recipe, indent=2) + '\n')
        completed = job / 'evidence' / model.recipe_hash()
        try:
            run([sys.executable, HERE / 'scripts/component_forge.py', '--recipe', recipe_path, '--no-resume'],
                env=dict(os.environ, FORGE_EPHEMERAL_BASE=str(job / 'evidence')), timeout=m['timeout_seconds'] + 600)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            report_failure(completed)
            raise
        record['success'] = verify_receipt(completed)
        proof = json.loads((completed / 'kernel-proof.json').read_text())
        require(proof['source'] == m['source'] and proof['full_kernel_linked'] is True, 'kernel proof identity differs')
        record['full_kernel_linked'] = True
    finally:
        (destination / 'kernel-preparation.json').write_text(json.dumps(record, indent=2) + '\n')
        if (job / 'evidence').exists():
            shutil.copytree(job / 'evidence', destination / 'forge')


if __name__ == '__main__':
    main()
