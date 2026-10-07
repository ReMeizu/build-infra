"""Compile the pinned common ARM64 kernel and retain its compile evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

SOURCE = Path('/workspace/src/kernel')
OUT = Path('/workspace/out')
WORK = Path('/workspace/scratch/kbuild')
REQUIRED_CONFIG = ('ARCH_MEDIATEK', 'ARCH_QCOM', 'PINCTRL_MT6735', 'PINCTRL_MT6755',
                   'PINCTRL_MT6797', 'PINCTRL_MSM8953', 'COMMON_CLK_MT6735', 'COMMON_CLK_MT6797')
REQUIRED_SYMBOLS = ('mt6735_pinctrl_driver', 'mt6755_pinctrl_driver')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def configuration(text):
    active = set(text.splitlines())
    require(all('CONFIG_' + name + '=y' in active for name in REQUIRED_CONFIG),
            'common driver configuration was dropped')


def main():
    toolchain = os.environ['MAINLINE_TOOLCHAIN']
    require(toolchain in {'gcc13', 'clang18'}, 'unsupported compiler')
    require(os.geteuid() != 0, 'compiler must be unprivileged')
    WORK.mkdir(exist_ok=False)
    make = ['make', '-C', str(SOURCE), 'O=' + str(WORK), 'ARCH=arm64',
            'CROSS_COMPILE=aarch64-linux-gnu-']
    if toolchain == 'gcc13':
        make += ['CC=aarch64-linux-gnu-gcc-13', 'HOSTCC=gcc-13']
        compiler = 'aarch64-linux-gnu-gcc-13'
    else:
        make += ['LLVM=-18']
        compiler = 'clang-18'
    version = subprocess.check_output([compiler, '--version'], text=True)
    (OUT / 'compiler.txt').write_text(version)
    with (OUT / 'kernel-build.log').open('w') as log:
        for targets in [['defconfig'], ['remeizu.config']]:
            subprocess.run(make + targets, stdout=log, stderr=subprocess.STDOUT, check=True)
        configuration((WORK / '.config').read_text())
        subprocess.run(make + ['-j2', 'Image'], stdout=log, stderr=subprocess.STDOUT, check=True)
    configuration((WORK / '.config').read_text())
    symbols = subprocess.check_output(['aarch64-linux-gnu-nm', str(WORK / 'vmlinux')], text=True)
    names = {line.split()[-1] for line in symbols.splitlines() if line.split()}
    require(set(REQUIRED_SYMBOLS) <= names, 'common pinctrl drivers missing from linked ELF')
    (OUT / 'driver-symbols.txt').write_text('\n'.join(
        line for line in symbols.splitlines() if line.split()[-1] in REQUIRED_SYMBOLS) + '\n')
    for source, target in [('arch/arm64/boot/Image', 'Image'), ('System.map', 'System.map'),
                           ('.config', 'kernel.config')]:
        shutil.copyfile(WORK / source, OUT / target)
    image = (OUT / 'Image').read_bytes()
    require(len(image) > 64 and image[56:60] == b'ARM\x64', 'invalid ARM64 Image header')
    (OUT / 'kernel-proof.json').write_text(json.dumps({
        'schema': 1, 'toolchain': toolchain, 'compiler': version,
        'source': json.loads((SOURCE.parent / '.forge/source.json').read_text()),
        'image_sha256': hashlib.sha256(image).hexdigest(),
        'required_config': list(REQUIRED_CONFIG), 'linked_symbols': list(REQUIRED_SYMBOLS),
        'full_image_linked': True, 'hardware_accepted': False, 'flash_ready': False,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
