"""Validate immutable public M681 build inputs before any provisioning."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

OBJECTS = (
    'sound/built-in.o',
    'drivers/misc/mediatek/eccci1/ccci.o',
    'drivers/misc/mediatek/ccci_util/ccci_util_lib.o',
    'drivers/misc/mediatek/ccmni/eccmni.o',
    'drivers/misc/mediatek/base/power/mt6755/mt_clkbuf_ctl.o',
    'drivers/iio/imu/inv_mpu_m681/inv-mpu-iio.o',
    'drivers/misc/mediatek/gud/302c/gud/mcDrvModule.o',
    'drivers/misc/mediatek/gud/302c/gud/mcKernelApi.o',
    'drivers/input/fingerprint/goodix/gf_spi_tee.o',
)
SOURCE_URL = 'https://github.com/nomorecoolnicknames/mtk-t-alps-release-q0-kernel-4.9-lc.git'
TC_URL = 'https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9'
DTB = 'mediatek/wt6755_66_sz_l'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relative(value):
    require(isinstance(value, str) and value and not PurePosixPath(value).is_absolute()
            and '..' not in PurePosixPath(value).parts and str(PurePosixPath(value)) == value,
            'noncanonical relative path')
    return value


def pinned(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def validate(m):
    require(m.get('schema') == 'remeizu.m681-kernel-cloud.v1', 'unknown manifest schema')
    require(m.get('ready') is True, 'public M681 immutable inputs are not ready')
    require(m.get('source_license_reviewed') is True, 'public source dependency review incomplete')
    require(m.get('flash_ready') is False and m.get('runtime_verified') is False,
            'compile recipe cannot claim hardware acceptance')
    for name in ('source', 'toolchain'):
        item = m[name]
        require(item['url'] == (SOURCE_URL if name == 'source' else TC_URL), 'unreviewed public input URL')
        require(pinned(item.get('commit'), 40) and pinned(item.get('tree'), 40), 'missing immutable ' + name + ' identity')
    require(m['source'].get('files_sha256'), 'source file hashes missing')
    for name, digest in m['source']['files_sha256'].items():
        relative(name); require(pinned(digest, 64), 'source file hash missing')
        require(not any(x.startswith('.') for x in PurePosixPath(name).parts), 'private input path')
    require(m['toolchain'].get('python_wrapper_rewrite') is True, 'unreviewed compiler wrapper transformation')
    for name in ('aarch64-linux-android-gcc', 'aarch64-linux-android-g++',
                 'real-aarch64-linux-android-gcc', 'aarch64-linux-android-ld'):
        require(pinned(m['toolchain']['bin_sha256'].get(name), 64), 'compiler hash missing')
    c = m['config']
    require(c.get('defconfig') == 'm681_49_a13_defconfig', 'unexpected board defconfig')
    require('arch/arm64/configs/' + c['defconfig'] in m['source']['files_sha256'], 'base defconfig not pinned')
    require(c.get('fragment_path') == 'arch/arm64/configs/m681_49_components.config', 'unreviewed selection fragment')
    require(pinned(c.get('fragment_sha256'), 64), 'selection fragment hash missing')
    require(c.get('generated_sha256') is None or pinned(c['generated_sha256'], 64), 'invalid generated config identity')
    require(m['source']['files_sha256'].get(c['fragment_path']) == c['fragment_sha256'], 'source-defined fragment not pinned')
    require(isinstance(m['container'].get('base_image_digest'), str) and re.fullmatch(r'ubuntu@sha256:[0-9a-f]{64}', m['container']['base_image_digest']), 'immutable base image digest missing')
    require(pinned(m['container'].get('dockerfile_sha256'), 64), 'Dockerfile source hash missing')
    require(m['targets'] == ['Image.gz-dtb', 'vmlinux'] and m['required_objects'] == list(OBJECTS),
            'normal complete Kbuild targets changed')
    require(type(m['jobs']) is int and 1 <= m['jobs'] <= 8, 'compiler job limit exceeded')
    require(type(m['timeout_seconds']) is int and 0 < m['timeout_seconds'] <= 1800, 'build deadline exceeded')
    require(m['container'].get('image_tag') == 'androidforge/build-kernel:m681-kernel-gcc49'
            and (m['container'].get('image_id') is None or (isinstance(m['container']['image_id'], str)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', m['container']['image_id']))), 'invalid prepared container identity')
    return m


def parse_config(text):
    values = {}
    for line in text.splitlines():
        enabled = re.fullmatch(r'(CONFIG_[A-Za-z0-9_]+)=(.*)', line)
        disabled = re.fullmatch(r'# (CONFIG_[A-Za-z0-9_]+) is not set', line)
        if enabled: values[enabled[1]] = enabled[2]
        elif disabled: values[disabled[1]] = 'n'
    return values


def check_config(fragment, generated):
    wanted, actual = parse_config(fragment), parse_config(generated)
    differences = {k: (v, actual.get(k, 'n')) for k, v in wanted.items() if actual.get(k, 'n') != v}
    require(not differences, 'olddefconfig changed selected values: ' + json.dumps(differences, sort_keys=True))
    guards = {'CONFIG_INV_MPU_M681_FACTORY_CALIBRATION': 'n', 'CONFIG_MACH_MT6755': 'y',
              'CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE': 'y',
              'CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE_NAMES': '"' + DTB + '"'}
    require(all(actual.get(k, 'n') == v for k, v in guards.items()), 'board or persistent-calibration guard changed')
    return {'fragment_retained': True, 'board_guards_retained': True, 'runtime_verified': False}


def artifacts():
    names = ['arch/arm64/boot/Image.gz-dtb', 'arch/arm64/boot/Image.gz',
             'arch/arm64/boot/dts/' + DTB + '.dtb', 'vmlinux', 'System.map', 'kernel.config',
             'kernel-build.log', 'config-proof.json', 'kernel-proof.json', 'tool-versions.txt']
    for obj in OBJECTS:
        names += ['objects/' + obj, 'objects/' + str(PurePosixPath(obj).with_name('.' + PurePosixPath(obj).name + '.cmd'))]
    return names
