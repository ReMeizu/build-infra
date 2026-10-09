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
    kbuild_platform = m.get('kbuild_platform', m['platform'])
    reviewed_kbuild = {'mt6735'} if m['platform'] == 'mt6753' else {m['platform']}
    if m['device'] == 'u10' and m['kernel_version'] == '3.18':
        reviewed_kbuild = {'mt6755'}
    require(kbuild_platform in reviewed_kbuild, 'unreviewed Kbuild platform mapping')
    require(m['arch'] == 'arm64' and m['target'] == 'Image.gz-dtb', 'unsupported kernel target')
    require(m['kernel_version'] in {'3.18', '4.9'}, 'unsupported reviewed GCC4.9 kernel version')
    require(m.get('board_preparation', 'kbuild') in {'kbuild', 'copy-tracked'}, 'unreviewed board data preparation')
    if m.get('board_preparation') == 'copy-tracked':
        require(m['kernel_version'] == '3.18' and 'scripts/drvgen/drvgen.mk' in m['source']['files_sha256'],
                'unhashed board data preparation rule')
    require(type(m['jobs']) is int and 1 <= m['jobs'] <= 4, 'unbounded compile jobs')
    require(type(m['timeout_seconds']) is int and 600 <= m['timeout_seconds'] <= 3600, 'unbounded compile duration')
    source = m['source']
    require(bool(re.fullmatch(r'https://github.com/(ReMeizu|nomorecoolnicknames)/[A-Za-z0-9_.-]+\.git', source['url'])), 'source must be a reviewed public project repository')
    for item in (source, m['toolchain']):
        digest(item['commit'], 40); digest(item['tree'], 40)
    require(m['toolchain']['url'] == 'https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9', 'unsupported toolchain origin')
    require(m['toolchain']['preparation'] in {'python3-wrappers', 'elf-gcc-bfd', 'elf-real-gcc'}, 'unreviewed toolchain preparation')
    for paths in (source['files_sha256'], m['toolchain']['bin_sha256']):
        require(isinstance(paths, dict) and bool(paths), 'missing pinned input files')
        for name, value in paths.items():
            relative(name); digest(value)
    if m['toolchain']['preparation'] == 'elf-real-gcc':
        require({'real-aarch64-linux-android-gcc', 'aarch64-linux-android-ld'}
                <= m['toolchain']['bin_sha256'].keys(), 'unhashed real compiler or linker')
    if m['toolchain']['preparation'] == 'elf-gcc-bfd':
        require({'aarch64-linux-android-gcc', 'aarch64-linux-android-ld.bfd'}
                <= m['toolchain']['bin_sha256'].keys(), 'unhashed ELF compiler or BFD linker')
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
    if m.get('config_seed'):
        require(m['device'] == 'u10' and m['jobs'] == 2, 'config seed is U10-only')
        relative(m['config_seed']['file']); digest(m['config_seed']['sha256'])
        reviewed_seeds = {
            'recipes/u10-devapc-selected.config': '06e84cb1b7540e8e715a25b472b0ae4f33a72d434fe8034de1ec6b6ba769cf4e',
            'recipes/u10-upright-selected.config': '930341e6f7558b4f2d05a903b82f14309295e363f26e80a9c2ee0b57c3eec854',
        }
        require(reviewed_seeds.get(m['config_seed']['file']) == m['config_seed']['sha256']
                == m['expected_config_sha256'], 'unreviewed U10 config seed')
    if m.get('required_symbol_table'):
        require(m['device'] == 'u10' and m['required_symbol_table'] == {'symbol': 'devapc_devices', 'bytes': 157 * 16}
                and 'drivers/misc/mediatek/devapc/mt6755/devapc.o' in m['required_objects'], 'unreviewed compiled table requirement')
    for field in ('retain_raw_image', 'require_baseline_dtb'):
        require(type(m.get(field, False)) is bool, 'nonboolean output requirement')
    return m


def validate_config_seed(m, data):
    validate(m)
    require(isinstance(data, bytes) and hashlib.sha256(data).hexdigest() == m['config_seed']['sha256'],
            'changed reviewed config seed')
    rows = data.decode().splitlines()
    required = ['CONFIG_MTK_CCCI_LEGACY_PORT_ABI5=y', 'CONFIG_MEIZU_U10_DEVAPC_STOCK_LAYOUT=y',
                'CONFIG_MTK_DEVAPC_DRIVER=y', 'CONFIG_MTK_LCM_PHYSICAL_ROTATION="0"', 'CONFIG_MTK_FB=y']
    rotation = ('# CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW is not set'
                if m['config_seed']['file'] == 'recipes/u10-upright-selected.config'
                else 'CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW=y')
    require(all(rows.count(row) == 1 for row in required + [rotation]), 'U10 board configuration differs')
    return data


def artifacts(m):
    extra = (['arch/arm64/boot/Image'] if m.get('retain_raw_image') else []) + (['compiled-devapc-table.json'] if m.get('required_symbol_table') else [])
    return extra + ['arch/arm64/boot/Image.gz-dtb', 'arch/arm64/boot/Image.gz', m['dtb_file'],
            'vmlinux', 'System.map', 'kernel.config', 'kernel-build.log', 'kernel-proof.json',
            'tool-versions.txt'] + ['objects/' + p for obj in m['required_objects']
                                  for p in (obj, str(PurePosixPath(obj).with_name('.' + PurePosixPath(obj).name + '.cmd')))]
