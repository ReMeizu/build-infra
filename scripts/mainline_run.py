"""Stage immutable free-software inputs for the common kernel compile check."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
from kernel_run import extract, fetch, output, run, sha, verify_receipt
from mainline_forge import forge

HERE = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://github.com/ReMeizu/linux-remeizu.git'
SOURCE_COMMIT = 'b82a7ece2830f57896d79939547941698260e041'
SOURCE_TREE = 'af06c94a89127fa56fbc29c26b9bd76d853d101d'
ARTIFACTS = ['Image', 'System.map', 'kernel.config', 'kernel-proof.json',
             'kernel-build.log', 'compiler.txt', 'driver-symbols.txt']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', choices=('gcc13', 'clang18'), required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    args = parser.parse_args()
    mount = Path('/mnt/forge')
    if os.geteuid() != 0 or not mount.is_mount() or mount.stat().st_dev == Path('/').stat().st_dev:
        raise ValueError('controller requires a separate ephemeral scratch mount')
    if shutil.disk_usage(mount).free < 10 * 1024**3:
        raise ValueError('less than10GiB scratch space')
    destination = args.receipt_dir
    if not destination.is_absolute() or destination.resolve() != destination:
        raise ValueError('noncanonical receipt directory')
    destination.mkdir(parents=True, exist_ok=False)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    job = mount / ('mainline-' + args.toolchain + '-' + stamp)
    job.mkdir()
    downloads = job / 'downloads'; downloads.mkdir()
    source = job / 'source'; source.mkdir()
    record = {'toolchain': args.toolchain, 'full_image_linked': False,
              'hardware_accepted': False, 'flash_ready': False}
    completed = None
    try:
        archive, provenance = fetch(downloads, 'kernel', SOURCE_URL, SOURCE_COMMIT, SOURCE_TREE)
        extract(archive, source / 'kernel')
        record['source'] = provenance
        tooling = source / '.forge'; tooling.mkdir()
        shutil.copyfile(HERE / 'scripts/mainline_build.py', tooling / 'mainline_build.py')
        (tooling / 'source.json').write_text(json.dumps(provenance))
        run(['git', 'init', '-q', source])
        run(['git', '-C', source, 'add', '.forge'])
        run(['git', '-C', source, '-c', 'user.name=ReMeizu', '-c', 'user.email=build@remeizu.invalid',
             'commit', '-qm', 'Pin mainline build inputs'])
        run(['docker', 'pull', 'ubuntu:24.04'], timeout=300)
        base = json.loads(output(['docker', 'image', 'inspect', 'ubuntu:24.04']))[0]['RepoDigests'][0]
        if '@sha256:' not in base:
            raise ValueError('base image has no immutable digest')
        tag = 'androidforge/build-mainline:mainline-6.18'
        run(['docker', 'build', '--build-arg', 'BASE_IMAGE=' + base, '-f',
             HERE / 'recipes/mainline.Dockerfile', '-t', tag, HERE / 'recipes'], timeout=600)
        image = output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'])
        recipe = {'image_tag': tag, 'image_id': image, 'build_env_key': 'mainline-6.18',
                  'source_mount_path': str(source), 'output_dir_in_container': '/workspace/out',
                  'command': ['python3', '/workspace/src/.forge/mainline_build.py'],
                  'env': {'MAINLINE_TOOLCHAIN': args.toolchain, 'KBUILD_BUILD_TIMESTAMP': '2026-10-07 00:00:00 UTC'},
                  'idempotency_key': job.name, 'timeout_seconds': 3600,
                  'execution_profile': 'cloud-mounted', 'scratch_mount_path': str(mount),
                  'container_user': '1001:1001', 'required_artifacts': ARTIFACTS}
        model = forge.recipe_from_dict(recipe)
        recipe_path = destination / 'recipe.json'
        recipe_path.write_text(json.dumps(recipe, indent=2) + '\n')
        record.update(recipe_hash=model.recipe_hash(), base_image=base, image_id=image)
        completed = job / 'evidence' / model.recipe_hash()
        run([sys.executable, HERE / 'scripts/mainline_forge.py', '--recipe', recipe_path, '--no-resume'],
            env=dict(os.environ, FORGE_EPHEMERAL_BASE=str(job / 'evidence')), timeout=3900)
        record['success'] = verify_receipt(completed)
        proof = json.loads((completed / 'kernel-proof.json').read_text())
        if (proof['source'] != provenance or proof['full_image_linked'] is not True
                or proof['toolchain'] != args.toolchain or proof['image_sha256'] != sha(completed / 'Image')
                or proof['hardware_accepted'] is not False or proof['flash_ready'] is not False):
            raise ValueError('compiled proof does not match pinned source')
        record['full_image_linked'] = True
    finally:
        (destination / 'preparation.json').write_text(json.dumps(record, indent=2) + '\n')
        if completed and completed.exists():
            shutil.copytree(completed, destination / 'forge')


if __name__ == '__main__':
    main()
