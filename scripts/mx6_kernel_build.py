#!/usr/bin/env python3
"""Build and prove the pinned MX6 kernel in a fresh, networkless Forge container."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from kernel_build import require, sha

OBJECTS = (
    'drivers/misc/mediatek/connectivity/wlan/gen3/mgmt/rlm.o',
    'drivers/misc/mediatek/connectivity/wlan/gen3/os/linux/gl_init.o',
    'drivers/misc/mediatek/connectivity/wlan/gen3/wlan_gen3.o',
)
CONFIG = {
    'CONFIG_MTK_COMBO': 'y',
    'CONFIG_MTK_COMBO_WIFI': 'y',
    'CONFIG_MTK_COMBO_CHIP': '"CONSYS_6797"',
    'CONFIG_MTK_PLATFORM': '"mt6797"',
}


def validate_pins(pins):
    for name in ('kernel_commit', 'kernel_tree', 'toolchain_commit', 'toolchain_tree'):
        require(isinstance(pins.get(name), str) and re.fullmatch('[0-9a-f]{40}', pins[name]), 'invalid pin: '+name)
    require(pins.get('kernel_url') == 'https://github.com/nomorecoolnicknames/android_kernel_meizu_m95.git', 'unreviewed kernel repository')
    require(pins.get('toolchain_url') == 'https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9', 'unreviewed toolchain repository')
    require(pins.get('defconfig') == 'lineage_m95_defconfig' and pins.get('target') == 'Image.gz-dtb', 'unreviewed build target')
    require(type(pins.get('jobs')) is int and pins['jobs'] == 4, 'four build jobs required')
    expected = {'arch/arm64/configs/lineage_m95_defconfig',
                'drivers/misc/mediatek/connectivity/wlan/gen3/include/mgmt/rlm.h',
                'drivers/misc/mediatek/connectivity/wlan/gen3/mgmt/rlm.c',
                'drivers/misc/mediatek/connectivity/wlan/gen3/os/linux/gl_init.c'}
    require(set(pins.get('source_sha256', {})) == expected, 'incomplete source identity')
    for mapping in ('source_sha256', 'toolchain_sha256'):
        require(isinstance(pins.get(mapping), dict) and bool(pins[mapping]), 'missing digest mapping')
        for name, digest in pins[mapping].items():
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and isinstance(digest, str)
                    and re.fullmatch('[0-9a-f]{64}', digest), 'unsafe or invalid digest pin')
    require(set(pins['toolchain_sha256']) == {'aarch64-linux-android-gcc', 'aarch64-linux-android-g++',
            'real-aarch64-linux-android-gcc', 'aarch64-linux-android-ld'}, 'incomplete compiler identity')


def verify_inputs(source, pins):
    validate_pins(pins)
    for name, digest in pins['source_sha256'].items():
        require(sha(source/'kernel'/name) == digest, 'changed public source: '+name)
    for name, digest in pins['toolchain_sha256'].items():
        require(sha(source/'toolchain/bin'/name) == digest, 'changed compiler: '+name)


def validate_config(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            require(key not in values, 'duplicate generated config symbol: '+key)
            values[key] = value
    for name, value in CONFIG.items():
        require(values.get(name) == value, 'generated configuration excludes MX6 gen3: '+name)
    return {name: values[name] for name in CONFIG}


def validate_outputs(out):
    required = ['arch/arm64/boot/Image.gz-dtb', 'System.map', '.config', 'vmlinux']
    for name in OBJECTS:
        required.extend((name, str(PurePosixPath(name).with_name('.'+PurePosixPath(name).name+'.cmd'))))
    for name in required:
        path = out/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0, 'missing actual build output: '+name)
        if name.endswith('.o'):
            with path.open('rb') as stream:
                header = stream.read(20)
            require(header[:6] == b'\x7fELF\x02\x01' and header[16:20] == b'\x01\x00\xb7\x00',
                    'expected AArch64 relocatable object: '+name)
        elif name.endswith('.cmd'):
            require('aarch64-linux-android-' in path.read_text(), 'missing actual cross-compiler command: '+name)
    with (out/'arch/arm64/boot/Image.gz-dtb').open('rb') as stream:
        require(stream.read(2) == b'\x1f\x8b', 'kernel image is not gzip')
    require(re.search(r'^[0-9a-fA-F]+ [Tt] rlmGetVhtCapIE$', (out/'System.map').read_text(), re.M),
            'VHT helper absent from linked kernel')
    return required


def main():
    source, out, publish = Path('/workspace/src'), Path('/workspace/scratch/out'), Path('/workspace/out')
    require(Path('/.dockerenv').is_file() and Path(__file__).resolve() == source/'.forge/mx6_kernel_build.py', 'Forge container only')
    pins = json.loads((source/'.forge/mx6-wifi-inputs.json').read_text())
    verify_inputs(source, pins)
    require(os.environ.get('FORGE_KERNEL_JOBS') == '4', 'four bounded build jobs required')
    require(not any(out.iterdir()), 'output is not fresh')
    base = ['make', '-C', str(source/'kernel'), 'O='+str(out), 'ARCH=arm64',
            'CROSS_COMPILE='+str(source/'toolchain/bin/aarch64-linux-android-'), 'TARGET_BUILD_VARIANT=userdebug', 'V=0']
    commands, generated, outputs, error = [], None, None, None
    try:
        with (publish/'kernel-build.log').open('x') as stream:
            for target, seconds in (([pins['defconfig']], 120), (['-j4', pins['target']], 1200)):
                command = base+target
                commands.append(command)
                stream.write(json.dumps(command)+'\n'); stream.flush()
                subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=seconds)
                if target == [pins['defconfig']]:
                    generated = validate_config(out/'.config')
            outputs = validate_outputs(out)
            validate_config(out/'.config')
            for name in outputs:
                target = publish/name
                target.parent.mkdir(parents=True, exist_ok=True)
                with (out/name).open('rb') as reader, target.open('xb') as writer:
                    shutil.copyfileobj(reader, writer)
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        if (out/'.config').is_file():
            shutil.copyfile(out/'.config', publish/'diagnostic-kernel.config')
        version_records = []
        for argv in (['dpkg-query', '-W'], [str(source/'toolchain/bin/aarch64-linux-android-gcc'), '--version'],
                     ['make', '--version']):
            try:
                versions = subprocess.run(argv, capture_output=True, text=True, timeout=30)
                version_records.append(json.dumps(argv)+'\n'+versions.stdout+versions.stderr)
            except (OSError, subprocess.SubprocessError) as exc:
                version_records.append(json.dumps(argv)+'\n'+type(exc).__name__+'\n')
        (publish/'tool-versions.txt').write_text('\n'.join(version_records))
        proof = {'kind': 'public-mx6-wifi-full-kernel', 'source': pins, 'commands': commands,
                 'generated_config': generated, 'artifact_hashes': {name: sha(publish/name) for name in (outputs or []) if (publish/name).is_file()},
                 'new_environment': True, 'full_kernel_linked': outputs is not None and error is None,
                 'error': error, 'boot_image_created': False, 'flash_ready': False, 'runtime_verified': False,
                 'wifi_ac_runtime_verified': False}
        (publish/'kernel-proof.json').write_text(json.dumps(proof, indent=2)+'\n')


if __name__ == '__main__':
    main()
