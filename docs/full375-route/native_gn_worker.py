#!/usr/bin/env python3
"""Forge-only real native preloader/GN attempt; never emits an OS acceptance."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time

_run = subprocess.run
_deadline = None

def bounded_run(*args, **kwargs):
    remaining = _deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('native worker global execution deadline exhausted')
    kwargs['timeout'] = min(remaining, kwargs.get('timeout', remaining))
    return _run(*args, **kwargs)


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def safe_path(value):
    p = PurePosixPath(value)
    if p.is_absolute() or not p.parts or '..' in p.parts or str(p) != value:
        raise ValueError('unsafe source path: ' + value)
    return p


def verify_file(root, item):
    p = root / safe_path(item['path'])
    try:
        p.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError('source file path escapes input mount')
    if 'symlink' in item:
        if not p.is_symlink() or os.readlink(p) != item['symlink']:
            raise ValueError('source symlink drift: ' + item['path'])
    elif not p.is_file() or p.is_symlink() or sha(p) != item['sha256']:
        raise ValueError('source byte drift: ' + item['path'])
    return p

def native_output(source, config):
    if config.get('root_path') != str(source) or config.get('product') != 'm5c' or config.get('target_cpu') != 'arm64':
        raise ValueError('foreign native product output identity')
    result = Path(config['out_path'])
    try:
        result.resolve().relative_to((source/'out').resolve())
    except ValueError:
        raise ValueError('native output escapes owned RAM source')
    if result == source/'out':
        raise ValueError('specific native product output required')
    return result

def gn_output_target(source, native_out, value):
    if not value.startswith('//'):
        raise ValueError('actual GN source-root output required')
    target = source / safe_path(value[2:])
    try:
        relative = target.resolve().relative_to(native_out.resolve())
    except ValueError:
        raise ValueError('GN compile output escapes admitted native output')
    return str(relative)

def gn_target_outputs(data, label):
    # Official command_desc.cc emits a dictionary keyed by visible target label,
    # even when a single requested property is 'outputs'.
    if not isinstance(data, dict) or set(data) != {label} or not isinstance(data[label], dict):
        raise ValueError('actual single default-toolchain GN target identity required')
    outputs = data[label].get('outputs')
    if not isinstance(outputs, list) or not outputs or any(not isinstance(x,str) for x in outputs):
        raise ValueError('actual native target outputs missing: '+label)
    return outputs


def run():
    global _deadline
    controller = Path('/workspace/src')
    manifest = controller / 'GN_INPUTS.json'
    if sha(manifest) != os.environ['GN_INPUTS_SHA256']:
        raise ValueError('controller manifest drift')
    inputs = json.loads(manifest.read_text())
    if sha(controller/'native_gn_worker.py') != inputs['worker_sha256']:
        raise ValueError('successor worker bytes drift')
    for name, digest in inputs['successor_evidence'].items():
        verify_file(controller, {'path':name, 'sha256':digest})
    _deadline = time.monotonic() + inputs['execution_deadline_seconds']
    subprocess.run = bounded_run
    print('NATIVE_GN_PHASE controller-identity-verified', flush=True)
    out = Path('/workspace/out')
    from overlay_io import admit, prepared_source, retain_output, source_after
    admit(out, 'prepare', inputs)
    original, source = prepared_source(controller, out, inputs)
    rust_layouts = []
    for tool in inputs['tools']:
        root = controller / tool['payload_root']
        for item in tool['members']:
            if 'sha256' in item:
                verify_file(root, item)
            elif 'symlink' in item:
                verify_file(root, item)
        target = source / safe_path(tool['native_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        if tool.get('layout') == 'rust-components':
            from layout_native_rust import install
            rust_layouts.append(install(root, tool['subdir'], tool['members'], target))
        else:
            target.symlink_to(root / tool.get('subdir', ''))
    if rust_layouts:
        (out / 'NATIVE_RUST_LAYOUT.json').write_text(json.dumps(rust_layouts, indent=2) + '\n')
    print('NATIVE_GN_PHASE source-and-official-tools-verified', flush=True)
    # Genuine uninitialized parent Git pointer; no child source fabricated.
    for item in inputs.get('uninitialized_gitlinks', []):
        path = original / safe_path(item['path'])
        if not path.is_dir() or path.is_symlink() or list(path.iterdir()):
            raise ValueError('original uninitialized gitlink drift')
        (source / safe_path(item['path'])).mkdir(parents=True, exist_ok=True, mode=item['directory_mode'])
    patches = []
    for item in inputs['patches']:
        patch = verify_file(controller, item)
        cwd = source / item['target']
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=cwd, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=cwd, check=True)
        patches.append({'target': item['target'], 'sha256': item['sha256']})
    for item in inputs['overlay_files']:
        p = verify_file(controller, item)
        dst = source / safe_path(item['target'])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
        if sha(dst) != item['sha256']:
            raise ValueError('overlay RAM copy drift')
    env = os.environ.copy()
    native_tmp = out / 'native-tmp'
    native_tmp.mkdir(exist_ok=False)
    env['TMPDIR'] = str(native_tmp)
    if inputs.get('mke2fs_config_product_path'):
        env['MKE2FS_CONFIG'] = str(source / safe_path(inputs['mke2fs_config_product_path']))
        if not Path(env['MKE2FS_CONFIG']).is_file():
            raise ValueError('actual native image filesystem policy absent')
    python = source / 'prebuilts/python/linux-x86/3.11.4/bin/python3'
    native_python_bin = out / 'native-host-bin'
    native_python_bin.mkdir(exist_ok=False)
    (native_python_bin / 'python').symlink_to(python)
    env['PATH'] = str(native_python_bin) + ':' + str(python.parent) + ':' + str(source / 'prebuilts/build-tools/linux-x86/bin') + ':' + env['PATH']
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    (out / 'NATIVE_HOST_RUNTIME.json').write_text(json.dumps({
        'actual_glibc': os.confstr('CS_GNU_LIBC_VERSION'),
        'native_python_shebang_alias': str(native_python_bin / 'python'),
        'native_python_shebang_target': str(python),
        'native_python_shebang_version': subprocess.run([str(native_python_bin / 'python'), '--version'], env=env, capture_output=True, text=True, check=True).stdout.strip(),
        'python_archive_minimum_glibc': '2.27',
        'python_wheel_abi_validation': 'actual native Python pip compatible tags'}, indent=2) + '\n')
    wheel_root = controller / 'official-python-wheels'
    for item in inputs['python_wheels']:
        verify_file(wheel_root, item)
    site = out / 'native-python-site'
    if site.exists():
        raise ValueError('fresh offline Python dependency destination required')
    # Normal native platform dependencies only; no host/global installation,
    # no network, no source compilation, no bytecode or cache side effects.
    install = [str(python), '-m', 'pip', 'install', '--no-index', '--no-compile',
               '--no-cache-dir', '--no-deps', '--target', str(site)]
    install += [str(wheel_root / x['path']) for x in inputs['python_wheels']]
    with (out / 'native-python-install.log').open('wb') as log:
        subprocess.run(install, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    env['PYTHONPATH'] = str(site)
    print('NATIVE_GN_PHASE native-python-dependencies-installed', flush=True)
    cmd = [str(python), 'build/hb/main.py', 'build', '--no-indep',
           '--product-name', 'm5c', '--build-variant', 'root', '--build-only-gn']
    with (out / 'native-gn.log').open('wb') as log:
        print('NATIVE_GN_PHASE real-hb-preloader-gn-starting', flush=True)
        rc = subprocess.run(cmd, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    # Re-read original inputs, not only our shadow. Compiler output cannot
    # substitute for a matching source input identity.
    for item in inputs['source_files']:
        verify_file(original, item)
    for item in inputs.get('uninitialized_gitlinks', []):
        for root in (original, source):
            path = root / safe_path(item['path'])
            if not path.is_dir() or path.is_symlink() or list(path.iterdir()):
                raise ValueError('uninitialized original or RAM shadow gitlink drift')
    native_config = json.loads((source/'out/ohos_config.json').read_text())
    native_out = native_output(source, native_config)
    product = json.loads((source/'vendor/oniro/m5c/config.json').read_text())
    if product.get('build_selinux') is not False:
        raise ValueError('experimental child global-policy ownership requires build_selinux=false')
    gn_rc = rc
    phases = []
    native_images = []
    native_libraries = []
    if rc == 0 and inputs.get('build_runtime_then_images'):
        if not (native_out/'build.ninja').is_file():
            raise ValueError('genuine native GN output required before compilation')
        gn = source/'prebuilts/build-tools/linux-x86/bin/gn'
        ninja = source/'prebuilts/build-tools/linux-x86/bin/ninja'
        # These are genuine pinned GN definitions, not fabricated SDK shims.
        labels = ['//third_party/musl:soft_libc_musl_shared',
                  '//commonlibrary/c_utils/base:utils',
                  '//third_party/libhybris/hybris/common:libhybris-common',
                  '//third_party/libhybris/hybris/common:q']
        outputs = []
        for label in labels:
            command = [str(gn), 'desc', str(native_out), label, 'outputs', '--format=json']
            data = json.loads(subprocess.run(command, cwd=source, env=env,
                capture_output=True, text=True, check=True).stdout)
            outputs.extend(gn_output_target(source, native_out, x) for x in gn_target_outputs(data,label))
        command = [str(ninja), '-C', str(native_out), '-j2'] + sorted(set(outputs))
        admit(out, 'libraries', inputs)
        print('NATIVE_GN_PHASE real-libc-utils-loader-build-starting', flush=True)
        with (out/'native-runtime-build.log').open('wb') as log:
            rc = subprocess.run(command, cwd=source, env=env, stdout=log,
                                stderr=subprocess.STDOUT).returncode
        phases.append({'phase':'libc-utils-loader', 'labels':labels,'command':command,'exit_code':rc})
        if rc == 0:
            for relative in outputs:
                if not (native_out/relative).is_file():
                    raise ValueError('Ninja success without admitted target output')
                native_libraries.append({'path':retain_output(native_out/relative, out, source),
                    'sha256':sha(native_out/relative),'bytes':(native_out/relative).stat().st_size})
            _milestone=out/'NATIVE_LIBRARIES_RESULT.pending.json'
            _milestone.write_text(json.dumps({
                'schema':'remeizu.public-native-linked-libraries-milestone.v1',
                'source_inventory_sha256':sha(manifest),'native_gn_completed':True,
                'build_phases':phases,'native_libraries':native_libraries,
                'native_image_built':False,'native_images':[],
                'complete_gui_phone':False,'whole_image_producer_admission':False,
                'runtime':False},indent=2)+'\n')
            _milestone.replace(out/'NATIVE_LIBRARIES_RESULT.json')
            admit(out, 'images', inputs)
            command = [str(ninja), '-C', str(native_out), '-j2', 'images']
            print('NATIVE_GN_PHASE real-native-images-build-starting', flush=True)
            with (out/'native-images-build.log').open('wb') as log:
                rc = subprocess.run(command, cwd=source, env=env, stdout=log,
                                    stderr=subprocess.STDOUT).returncode
            phases.append({'phase':'native-images','command':command,'exit_code':rc})
            if rc == 0:
                for name in ('system','vendor','sys_prod','chip_prod'):
                    paths = list(native_out.glob('packages/*/images/'+name+'.img'))
                    if len(paths) != 1 or paths[0].is_symlink() or paths[0].stat().st_size <= 0:
                        raise ValueError('exact four native image outputs required: '+name)
                    p = paths[0]
                    with p.open('rb') as f:
                        f.seek(1080)
                        if f.read(2) != b'\x53\xef':
                            raise ValueError('native raw ext4 superblock required: '+name)
                    native_images.append({'partition':name,'path':retain_output(p, out, source),
                        'sha256':sha(p),'bytes':p.stat().st_size,'raw_ext4_magic_verified':True,
                        'kernel_feature_admission':False,'whole_inode_xattr_admission':False})
        for item in inputs['source_files']:
            verify_file(original, item)
    artifacts = []
    for p in (source/'out/ohos_config.json', source/'out/preloader/m5c/build_gnargs.prop', native_out/'build.ninja'):
        if p.is_file():
            artifacts.append({'path': retain_output(p, out, source), 'sha256': sha(p), 'bytes': p.stat().st_size})
    result = {'schema': 'remeizu.m5c-native-gn-attempt.v1', 'native_command': cmd,
              'exit_code': rc, 'source_inventory_sha256': sha(manifest),
              'project_count': len(inputs['projects']), 'patches': patches,
              'source_before_after_verified': True, 'artifacts': artifacts,
              'selected_product_source_closure': False, 'full506_checkout': False,
              'native_output_relative': str(native_out.relative_to(source)), 'build_phases':phases,
              'native_gn_completed': gn_rc == 0 and (native_out/'build.ninja').is_file(),
              'native_image_built': len(native_images) == 4, 'native_images':native_images,
              'native_libraries':native_libraries, 'native_product_build_selinux':False,
              'whole_image_producer_admission':False,'complete_gui_phone':False,'runtime': False}
    source_after(controller, out, inputs)
    (out / 'GN_RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    print('NATIVE_PRELOADER_GN_ATTEMPT_EXIT', rc, flush=True)
    return rc


if __name__ == '__main__':
    try:
        sys.exit(run())
    except Exception as error:
        out = Path('/workspace/out')
        if out.is_dir():
            (out / 'GN_FAILURE.json').write_text(json.dumps({'error': str(error),
                'native_image_built': False, 'runtime': False}, indent=2) + '\n')
        raise
