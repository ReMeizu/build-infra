"""Validate public, immutable kernel component build profiles."""
import hashlib
from pathlib import Path, PurePosixPath
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relative(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_./+-]+', value)), 'invalid input path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and '..' not in p.parts and '.git' not in p.parts
            and str(p) == value and value != '.', 'noncanonical input path')
    return value


def digest(value, length=64):
    require(isinstance(value, str) and bool(re.fullmatch('[0-9a-f]{' + str(length) + '}', value)), 'invalid digest')
    return value


def validate(m):
    require(m['schema'] == 1, 'unsupported profile schema')
    require(m['device'] in {'m5c', 'm681', 'l681', 'u10', 'u20', 'm3s', 'm5s', 'm2note', 'mx6'}, 'unknown device')
    require(m['platform'] in {'mt6735', 'mt6737m', 'mt6750', 'mt6755', 'mt6753', 'mt6797'}, 'unknown platform')
    platforms = {'m5c': {'mt6735', 'mt6737m'}, 'm681': {'mt6755'}, 'l681': {'mt6755'},
                 'u10': {'mt6750'}, 'u20': {'mt6755'}, 'm3s': {'mt6750'},
                 'm5s': {'mt6753'}, 'm2note': {'mt6753'}, 'mx6': {'mt6797'}}
    require(m['platform'] in platforms[m['device']], 'board/platform mismatch')
    require(m['arch'] == 'arm64' and m['target'] == 'Image.gz-dtb', 'unsupported kernel target')
    require(m['kernel_version'] == '4.9', 'initial compiler contract supports 4.9 only')
    require(type(m['jobs']) is int and 1 <= m['jobs'] <= 4, 'unbounded compile jobs')
    require(type(m['timeout_seconds']) is int and 600 <= m['timeout_seconds'] <= 3600, 'unbounded compile duration')
    source = m['source']
    require(bool(re.fullmatch(r'https://github.com/(ReMeizu|nomorecoolnicknames)/[A-Za-z0-9_.-]+\.git', source['url'])), 'source must be a reviewed public project repository')
    for item in (source, m['toolchain']):
        digest(item['commit'], 40); digest(item['tree'], 40)
    require(m['toolchain']['url'] == 'https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9', 'unsupported toolchain origin')
    require(m['toolchain']['preparation'] in {'python3-wrappers', 'elf-gcc-bfd'}, 'unreviewed toolchain preparation')
    for paths in (source['files_sha256'], m['toolchain']['bin_sha256']):
        require(isinstance(paths, dict) and bool(paths), 'missing pinned input files')
        for name, value in paths.items():
            relative(name); digest(value)
    relative(m['config_file']); relative(m['dtb_file'])
    require(m['config_file'] in source['files_sha256'], 'unhashed board config')
    require(m['dtb_file'].startswith('arch/arm64/boot/dts/') and m['dtb_file'].endswith('.dtb'), 'invalid board DTB target')
    require(m['dtb_file'][:-4] + '.dts' in source['files_sha256'] and 'Makefile' in source['files_sha256'], 'unhashed board DTS/kernel version input')
    digest(m['expected_config_sha256']); digest(m['baseline_dtb_sha256'])
    objects = m['required_objects']
    require(isinstance(objects, list) and bool(objects) and len(objects) == len(set(objects)), 'missing/duplicate required objects')
    for obj in objects:
        relative(obj); require(obj.endswith('.o'), 'not a Kbuild object')
    require(m['build_variant'] == 'userdebug', 'initial public component variant is userdebug')
    return m


def artifacts(m):
    return ['arch/arm64/boot/Image.gz-dtb', 'arch/arm64/boot/Image.gz', m['dtb_file'],
            'vmlinux', 'System.map', 'kernel.config', 'kernel-build.log', 'kernel-proof.json',
            'tool-versions.txt'] + ['objects/' + p for obj in m['required_objects']
                                  for p in (obj, str(PurePosixPath(obj).with_name('.' + PurePosixPath(obj).name + '.cmd')))]
