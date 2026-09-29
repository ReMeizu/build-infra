"""Compile the complete M681 Kbuild graph inside the admitted Forge container."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from m681_manifest import DTB, OBJECTS, check_config, require, sha, validate


def elf64_arm(path, linked=False):
    with Path(path).open('rb') as stream:
        header = stream.read(20)
    require(header[:6] == b'\x7fELF\x02\x01' and len(header) == 20
            and int.from_bytes(header[18:20], 'little') == 183, 'not an AArch64 ELF64: ' + str(path))
    require(int.from_bytes(header[16:18], 'little') == (2 if linked else 1), 'wrong ELF linkage: ' + str(path))


def commands(source, out, m):
    base = ['make', '-C', str(source / 'kernel'), 'O=' + str(out), 'ARCH=arm64',
            'MTK_PLATFORM=mt6755', 'CROSS_COMPILE=' + str(source / 'toolchain/bin/aarch64-linux-android-'),
            'V=0']
    return base + [m['config']['defconfig']], base + ['olddefconfig'], base + ['-j' + str(m['jobs'])] + m['targets']


def publish_file(source, target):
    require(source.is_file() and not source.is_symlink() and source.stat().st_size > 0, 'missing normal Kbuild output: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as reader, target.open('xb') as writer:
        shutil.copyfileobj(reader, writer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-only', action='store_true')
    args = parser.parse_args()
    source, out, publish = Path('/workspace/src'), Path('/workspace/scratch/out'), Path('/workspace/out')
    require(Path('/.dockerenv').is_file() and Path(__file__).resolve() == source / '.forge/m681_compile.py', 'Forge container only')
    m = validate(json.loads((source / '.forge/m681-full-inputs.json').read_text()))
    require(m['container']['image_id'] is not None, 'configuration/compile image must already be pinned')
    if not args.config_only:
        require(m['config']['generated_sha256'] is not None, 'configuration preparation must finish before full build')
    out.mkdir(parents=True, exist_ok=True)
    require(not any(out.iterdir()), 'fresh out directory required')
    for name, digest in m['source']['files_sha256'].items():
        require(sha(source / 'kernel' / name) == digest, 'public source hash mismatch')
    for name, digest in m['toolchain']['bin_sha256'].items():
        require(sha(source / 'toolchain/bin' / name) == digest, 'compiler hash mismatch')
    fragment_path = source / '.forge/m681-full-selected.fragment'
    require(sha(fragment_path) == m['config']['fragment_sha256'], 'selection fragment changed')
    log = publish / 'kernel-build.log'
    first, configure, build = commands(source, out, m)
    with log.open('x') as stream:
        for command in (first,):
            subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        with (out / '.config').open('a') as config:
            config.write('\n' + fragment_path.read_text() + '\n')
        subprocess.run(configure, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        publish_file(out / '.config', publish / 'kernel.config')
        proof = check_config(fragment_path.read_text(), (out / '.config').read_text())
        proof.update(config_sha256=sha(out / '.config'), source_commit=m['source']['commit'], container_image_id=m['container']['image_id'])
        if m['config']['generated_sha256'] is not None:
            require(sha(out / '.config') == m['config']['generated_sha256'], 'generated full config hash differs from pin')
        (publish / 'config-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
        if args.config_only:
            return
        stream.write(json.dumps(build) + '\n'); stream.flush()
        subprocess.run(build, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=m['timeout_seconds'])
    require(sha(out / '.config') == m['config']['generated_sha256'] == sha(publish / 'kernel.config'),
            'full make changed the prepared/saved kernel config')
    check_config(fragment_path.read_text(), (out / '.config').read_text())
    proof['full_make_config_unchanged'] = True
    (publish / 'config-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    elf64_arm(out / 'vmlinux', linked=True)
    for obj in OBJECTS:
        elf64_arm(out / obj)
        publish_file(out / obj, publish / 'objects' / obj)
        command_file = Path(obj).with_name('.' + Path(obj).name + '.cmd')
        publish_file(out / command_file, publish / 'objects' / command_file)
    names = ['arch/arm64/boot/Image.gz-dtb', 'arch/arm64/boot/Image.gz',
             'arch/arm64/boot/dts/' + DTB + '.dtb', 'vmlinux', 'System.map']
    for name in names: publish_file(out / name, publish / name)
    image = (out / names[0]).read_bytes()
    compressed, dtb = (out / names[1]).read_bytes(), (out / names[2]).read_bytes()
    require(compressed[:2] == b'\x1f\x8b' and dtb[:4] == b'\xd0\x0d\xfe\xed'
            and int.from_bytes(dtb[4:8], 'big') == len(dtb) and image == compressed + dtb,
            'Image.gz-dtb is not the pinned board gzip + compiled DTB')
    (publish / 'tool-versions.txt').write_text(subprocess.check_output(['dpkg-query', '-W'], text=True))
    receipt = {'source_commit': m['source']['commit'], 'source_tree': m['source']['tree'],
               'full_kbuild_traversal': True, 'required_objects': {p: sha(out / p) for p in OBJECTS},
               'config_sha256': sha(out / '.config'), 'image_sha256': sha(out / names[0]),
               'vmlinux_sha256': sha(out / 'vmlinux'), 'image_dtb_concatenation_verified': True,
               'container_image_id': m['container']['image_id'], 'compiler_sha256': m['toolchain']['bin_sha256'],
               'flash_ready': False, 'runtime_verified': False}
    (publish / 'kernel-proof.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__': main()
