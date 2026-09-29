"""Prepare pinned public M681 inputs on an already admitted disposable cloud VM.

This command does not allocate a VM, provision a mount, pull/build an image,
modify the budget ledger or flash a phone. Use the existing admission gate first.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]
from kernel_run import extract, fetch, output, run, verify_receipt
from m681_forge import forge
from m681_manifest import artifacts, require, sha, validate


def recipe_for(m, source, mount, run_id, config_only=False):
    return {'image_tag': m['container']['image_tag'], 'image_id': m['container']['image_id'],
            'build_env_key': 'm681-kernel-gcc49', 'source_mount_path': str(source),
            'output_dir_in_container': '/workspace/out',
            'command': ['python3', '/workspace/src/.forge/m681_compile.py'] + (['--config-only'] if config_only else []),
            'env': {'KBUILD_BUILD_TIMESTAMP': '2026-09-29 00:00:00 UTC', 'KBUILD_BUILD_VERSION': '1'},
            'idempotency_key': ('m681-config-' if config_only else 'm681-full-') + run_id, 'timeout_seconds': 300 if config_only else m['timeout_seconds'],
            'execution_profile': 'cloud-mounted', 'scratch_mount_path': str(mount),
            'container_user': '1001:1001', 'required_artifacts': ['kernel.config', 'config-proof.json', 'kernel-build.log'] if config_only else artifacts()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=HERE / 'recipes/m681-full-inputs.json')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--scratch-mount', type=Path)
    parser.add_argument('--receipt-dir', type=Path)
    args = parser.parse_args(argv)
    m = validate(json.loads(args.manifest.read_text()))
    dockerfile = HERE / 'recipes/kernel-gcc49.Dockerfile'
    require(sha(dockerfile) == m['container']['dockerfile_sha256'], 'reviewed Dockerfile hash differs')
    if args.validate_only:
        print(json.dumps({'immutable_inputs_valid': True, 'flash_ready': False}))
        return 0
    require(args.scratch_mount is not None and args.receipt_dir is not None, 'explicit scratch and receipt paths required')
    require(os.geteuid() == 0, 'controller requires sudo; build uses non-root1001')
    mount = args.scratch_mount
    require(mount.is_absolute() and mount.resolve() == mount and mount != Path('/'), 'unsafe scratch mount')
    mounts = forge._mount_filesystems()
    require(mount in mounts and mounts[mount][1] in {'ext4', 'xfs'}
            and mounts[mount][0] != mounts[Path('/')][0], 'distinct mounted scratch filesystem required')
    require(shutil.disk_usage(mount).free >= 12 * 1024**3, 'less than12GiB kernel preparation/scratch headroom')
    destination = args.receipt_dir
    require(destination.is_absolute() and not destination.exists() and destination.resolve() == destination,
            'new canonical receipt directory required')
    destination.mkdir(parents=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + str(os.getpid())
    job = mount / ('m681-public-' + stamp); job.mkdir()
    downloads = job / 'downloads'; downloads.mkdir()
    source = job / 'source'; source.mkdir()
    preparation = {'kind': 'public-m681-full-kernel', 'source_input': None, 'toolchain_input': None,
                   'flash_ready': False, 'runtime_verified': False}
    try:
        run(['docker', 'pull', m['container']['base_image_digest']], timeout=300)
        run(['docker', 'build', '--build-arg', 'BASE_IMAGE=' + m['container']['base_image_digest'],
             '-f', dockerfile, '-t', m['container']['image_tag'], HERE / 'recipes'], timeout=600)
        actual_image = output(['docker', 'image', 'inspect', m['container']['image_tag'], '--format', '{{.Id}}'])
        if m['container']['image_id'] is not None:
            require(actual_image == m['container']['image_id'], 'prepared image differs from accepted pin')
        m['container']['image_id'] = actual_image
        preparation.update(container_image_id=actual_image, base_image_digest=m['container']['base_image_digest'],
                           dockerfile_sha256=m['container']['dockerfile_sha256'])
        for name, source_name in (('kernel', 'source'), ('toolchain', 'toolchain')):
            item = m[source_name]
            archive, provenance = fetch(downloads, name, item['url'], item['commit'], item['tree'])
            extract(archive, source / name)
            preparation[source_name + '_input'] = provenance
        for name in ('aarch64-linux-android-gcc', 'aarch64-linux-android-g++'):
            path = source / 'toolchain/bin' / name
            data = path.read_bytes()
            require(data.startswith(b'#!/usr/bin/python\n'), 'unexpected original public compiler wrapper')
            path.write_bytes(data.replace(b'#!/usr/bin/python\n', b'#!/usr/bin/env python3\n', 1))
        for name, digest in m['toolchain']['bin_sha256'].items():
            require(sha(source / 'toolchain/bin' / name) == digest, 'public compiler pin differs')
        for name, digest in m['source']['files_sha256'].items():
            require(sha(source / 'kernel' / name) == digest, 'public source file pin differs')
        tooling = source / '.forge'; tooling.mkdir()
        for name in ('m681_compile.py', 'm681_manifest.py'):
            shutil.copyfile(HERE / 'scripts' / name, tooling / name)
        fragment = source / 'kernel' / m['config']['fragment_path']
        require(sha(fragment) == m['config']['fragment_sha256'], 'public source-defined fragment hash differs')
        shutil.copyfile(fragment, tooling / 'm681-full-selected.fragment')
        (tooling / 'm681-full-inputs.json').write_text(json.dumps(m, indent=2) + '\n')
        # All fetched untracked bytes are also hashed by the Forge provenance pass.
        run(['git', 'init', '-q', source]); run(['git', '-C', source, 'add', '.forge'])
        run(['git', '-C', source, '-c', 'user.name=ReMeizu', '-c', 'user.email=build@remeizu.invalid',
             'commit', '-qm', 'Pin public M681 complete kernel inputs'])
        config_recipe = recipe_for(m, source, mount, stamp, config_only=True)
        config_model = forge.recipe_from_dict(config_recipe)
        config_path = destination / 'kernel-config-recipe.json'
        config_path.write_text(json.dumps(config_recipe, indent=2) + '\n')
        run([sys.executable, HERE / 'scripts/m681_forge.py', '--recipe', config_path, '--no-resume'],
            env=dict(os.environ, FORGE_EPHEMERAL_BASE=str(job / 'evidence')), timeout=600)
        config_output = job / 'evidence' / config_model.recipe_hash()
        preparation['config_success'] = verify_receipt(config_output)
        config_proof = json.loads((config_output / 'config-proof.json').read_text())
        require(config_proof['source_commit'] == m['source']['commit']
                and config_proof['container_image_id'] == actual_image, 'configuration preparation identity differs')
        generated_hash = sha(config_output / 'kernel.config')
        require(generated_hash == config_proof['config_sha256'], 'configuration preparation hash mismatch')
        if m['config']['generated_sha256'] is not None:
            require(generated_hash == m['config']['generated_sha256'], 'accepted full config hash differs')
        m['config']['generated_sha256'] = generated_hash
        preparation['generated_config_sha256'] = generated_hash
        # New Git provenance after preparing the same image/config identity.
        (tooling / 'm681-full-inputs.json').write_text(json.dumps(m, indent=2) + '\n')
        run(['git', '-C', source, 'add', '.forge/m681-full-inputs.json'])
        run(['git', '-C', source, '-c', 'user.name=ReMeizu', '-c', 'user.email=build@remeizu.invalid',
             'commit', '-qm', 'Pin prepared M681 configuration and container'])
        recipe = recipe_for(m, source, mount, stamp)
        model = forge.recipe_from_dict(recipe)
        preparation['recipe_hash'] = model.recipe_hash()
        recipe_path = destination / 'kernel-recipe.json'; recipe_path.write_text(json.dumps(recipe, indent=2) + '\n')
        run([sys.executable, HERE / 'scripts/m681_forge.py', '--recipe', recipe_path, '--no-resume'],
            env=dict(os.environ, FORGE_EPHEMERAL_BASE=str(job / 'evidence')), timeout=m['timeout_seconds'] + 300)
        preparation['success'] = verify_receipt(job / 'evidence' / model.recipe_hash())
    finally:
        (destination / 'kernel-preparation.json').write_text(json.dumps(preparation, indent=2) + '\n')
        if (job / 'evidence').exists():
            shutil.copytree(job / 'evidence', destination / 'forge')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
