"""Compile one complete board kernel in the Forge container."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from component_manifest import require, sha, validate


def elf(path, linked=False):
    with path.open('rb') as stream:
        h = stream.read(20)
    require(h[:6] == b'\x7fELF\x02\x01' and int.from_bytes(h[18:20], 'little') == 183
            and int.from_bytes(h[16:18], 'little') == (2 if linked else 1), 'invalid AArch64 output: ' + str(path))


def publish_file(src, dst):
    require(src.is_file() and not src.is_symlink() and src.stat().st_size > 0, 'missing Kbuild output: ' + str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open('rb') as r, dst.open('xb') as w:
        shutil.copyfileobj(r, w)


def main():
    source, out, publish = Path('/workspace/src'), Path('/workspace/scratch/out'), Path('/workspace/out')
    require(Path('/.dockerenv').exists() and Path(__file__).resolve() == source / '.forge/component_compile.py', 'Forge container only')
    m = validate(json.loads((source / '.forge/profile.json').read_text()))
    require(os.environ.get('FORGE_KERNEL_JOBS') == str(m['jobs']), 'compile job bound changed')
    require(not any(out.iterdir()), 'fresh Kbuild output required')
    for name, digest in m['source']['files_sha256'].items():
        require(sha(source / 'kernel' / name) == digest, 'changed board input: ' + name)
    for name, digest in m['toolchain']['bin_sha256'].items():
        require(sha(source / 'toolchain/bin' / name) == digest, 'changed compiler: ' + name)
    makefile = (source / 'kernel/Makefile').read_text()
    version = '.'.join(re.search(r'^' + key + r'\s*=\s*(\d+)\s*$', makefile, re.M)[1]
                       for key in ('VERSION', 'PATCHLEVEL'))
    require(version == m['kernel_version'], 'kernel version differs from compiler contract')
    shutil.copyfile(source / 'kernel' / m['config_file'], out / '.config')
    base = ['make', '-C', str(source / 'kernel'), 'O=' + str(out), 'ARCH=arm64',
            'MTK_PLATFORM=' + m['platform'], 'V=0',
            'TARGET_BUILD_VARIANT=' + m['build_variant'], 'HOSTCFLAGS=-fcommon',
            'CROSS_COMPILE=' + str(source / 'toolchain/bin/aarch64-linux-android-')]
    if m['toolchain']['preparation'] == 'elf-gcc-bfd':
        base.append('LD=' + str(source / 'toolchain/bin/aarch64-linux-android-ld.bfd'))
    commands = [base + ['olddefconfig'], base + ['-j' + str(m['jobs']), m['target']]]
    with (publish / 'kernel-build.log').open('x') as log:
        log.write(json.dumps(commands) + '\n'); log.flush()
        subprocess.run(commands[0], check=True, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        publish_file(out / '.config', publish / 'kernel.config')
        require(sha(out / '.config') == m['expected_config_sha256'], 'generated config differs from reviewed board pin')
        subprocess.run(commands[1], check=True, stdout=log, stderr=subprocess.STDOUT, timeout=m['timeout_seconds'])
    require(sha(out / '.config') == sha(publish / 'kernel.config') == m['expected_config_sha256'], 'full make changed configuration')
    elf(out / 'vmlinux', linked=True)
    for obj in m['required_objects']:
        elf(out / obj)
        publish_file(out / obj, publish / 'objects' / obj)
        cmd = Path(obj).with_name('.' + Path(obj).name + '.cmd')
        publish_file(out / cmd, publish / 'objects' / cmd)
    paths = ['arch/arm64/boot/Image.gz-dtb', 'arch/arm64/boot/Image.gz', m['dtb_file'], 'vmlinux', 'System.map']
    for name in paths:
        publish_file(out / name, publish / name)
    image, compressed, dtb = [(out / p).read_bytes() for p in paths[:3]]
    require(compressed[:2] == b'\x1f\x8b' and dtb[:4] == b'\xd0\x0d\xfe\xed'
            and int.from_bytes(dtb[4:8], 'big') == len(dtb) and image == compressed + dtb,
            'kernel image is not gzip plus the selected compiled board DTB')
    proof = {'device': m['device'], 'platform': m['platform'], 'source': m['source'],
             'toolchain': m['toolchain'], 'commands': commands,
             'full_kernel_linked': True, 'image_dtb_concatenation_verified': True,
             'config_sha256': sha(out / '.config'), 'dtb_sha256': sha(out / m['dtb_file']),
             'dtb_identical_to_baseline': sha(out / m['dtb_file']) == m['baseline_dtb_sha256'],
             'artifact_hashes': {p: sha(out / p) for p in paths + m['required_objects']},
             'boot_image_created': False, 'flash_ready': False, 'runtime_verified': False}
    (publish / 'kernel-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    (publish / 'tool-versions.txt').write_text(subprocess.check_output(['dpkg-query', '-W'], text=True))


if __name__ == '__main__':
    main()
