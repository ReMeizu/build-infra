#!/usr/bin/env python3
"""Create a new real source controller; retain original j6 input unchanged."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

FORGE_SHA = '9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8'
HERE = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def safe(value):
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or not p.parts or str(p) != value:
        raise ValueError('unsafe public source path')
    return p

def replace_once(code, old, new):
    if code.count(old) != 1:
        raise ValueError('reviewed original worker context drift: ' + old[:64])
    return code.replace(old, new, 1)

def transformed_worker(code):
    start = '    if len(os.sched_getaffinity(0)) < 6:\n'
    end = "    source = out / 'native-source'\n"
    if code.count(start) != 1 or code.count(end) != 1:
        raise ValueError('original six-job resource block drift')
    before, remainder = code.split(start)
    old, after = remainder.split(end, 1)
    if "available < 24*1024**3" not in old or "ninja_jobs':6" not in old:
        raise ValueError('original actual resource contract not the reviewed j6 contract')
    code = before + "    from free_hosted_resource import admit\n    admit(out, 'prepare', inputs)\n" + end + after
    if code.count("'-j6'") != 2:
        raise ValueError('actual runtime/images Ninja invocations differ')
    code = code.replace("'-j6'", "'-j2'")
    code = replace_once(code, "        print('NATIVE_GN_PHASE real-libc-utils-loader-build-starting', flush=True)",
                          "        admit(out, 'libraries', inputs)\n        print('NATIVE_GN_PHASE real-libc-utils-loader-build-starting', flush=True)")
    code = replace_once(code, "            if shutil.disk_usage(out).free < 4*1024**3:\n                raise ValueError('native images RAM capacity floor')",
                          "            admit(out, 'images', inputs)")
    code = replace_once(code, "            admit(out, 'images', inputs)",
        "            _milestone=out/'NATIVE_LIBRARIES_RESULT.pending.json'\n"
        "            _milestone.write_text(json.dumps({\n"
        "                'schema':'remeizu.public-native-linked-libraries-milestone.v1',\n"
        "                'source_inventory_sha256':sha(manifest),'native_gn_completed':True,\n"
        "                'build_phases':phases,'native_libraries':native_libraries,\n"
        "                'native_image_built':False,'native_images':[],\n"
        "                'complete_gui_phone':False,'whole_image_producer_admission':False,\n"
        "                'runtime':False},indent=2)+'\\n')\n"
        "            _milestone.replace(out/'NATIVE_LIBRARIES_RESULT.json')\n"
        "            admit(out, 'images', inputs)")
    # Original dependency checks, labels, GN arguments, source transformations,
    # SDK/Clang tools, hashes and refusal/runtime fields remain byte-identical.
    return code

def prepare(original, target, lock):
    original, target = Path(original), Path(target)
    if target.exists() or target.is_symlink():
        raise ValueError('fresh source controller required')
    inp = original / 'GN_INPUTS.json'
    if sha(inp) != lock['gn_inputs_sha256']:
        raise ValueError('real public GN inputs differ')
    inputs = json.loads(inp.read_text())
    from acquire import validate_lock,validate_cohort_proof
    validate_lock(lock,inputs);validate_cohort_proof(lock,inputs,original)
    target.mkdir(parents=True)
    names = {'layout_native_rust.py', 'worker.sh'}
    names.update(x['path'] for x in inputs['patches'] + inputs['overlay_files'])
    names.update(inputs['successor_evidence'])
    for name in sorted(names):
        source = original / safe(name)
        if not source.is_file() or source.is_symlink():
            raise ValueError('regular reviewed public control file required')
        dest = target / safe(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        dest.chmod(source.stat().st_mode & 0o777)
    parent_worker_sha = sha(original / 'native_gn_worker.py')
    if inputs['worker_sha256'] != parent_worker_sha:
        raise ValueError('original worker self-hash differs')
    worker = transformed_worker((original / 'native_gn_worker.py').read_text())
    (target / 'native_gn_worker.py').write_text(worker)
    shutil.copyfile(HERE / 'resource.py', target / 'free_hosted_resource.py')
    projection = {}
    # Use the original pure manifest projection; never install host tools.
    sys.path.insert(0, str(original))
    try:
        from layout_native_rust import project_manifest
        for tool in inputs['tools']:
            if tool.get('layout') == 'rust-components':
                _, rows = project_manifest(original / tool['payload_root'], tool['subdir'], tool['members'])
                for row in rows:
                    size = (original / tool['payload_root'] / row['path']).stat().st_size
                    old = projection.get(row['destination'])
                    if old and old != (row['sha256'], size):
                        raise ValueError('conflicting real Rust layout')
                    projection[row['destination']] = (row['sha256'], size)
    finally:
        sys.path.pop(0)
    seconds=min(285*60,int(lock.get('execution_seconds',285*60)))
    if seconds<600:raise ValueError('bounded compiler window below ten minutes')
    inputs.update(worker_sha256=sha(target / 'native_gn_worker.py'), free_hosted_intermediate=True,
                  free_hosted_rust_layout_bytes=sum(x[1] for x in projection.values()), execution_deadline_seconds=seconds)
    inputs['successor_evidence']['free_hosted_resource.py'] = sha(target / 'free_hosted_resource.py')
    (target / 'GN_INPUTS.json').write_text(json.dumps(inputs, sort_keys=True, indent=2) + '\n')
    # Empty mount targets are replaced by readonly immutable disk inputs.
    for name in ('native-source-input', 'tools', 'official-python-wheels'):
        (target / name).mkdir()
        (target / name / '.mount-target').write_text('readonly public input mount\n')
    receipt = {'schema': 'remeizu.free-hosted-j2-source-successor.v1', 'parent_gn_inputs_sha256': sha(inp),
               'parent_worker_sha256': parent_worker_sha, 'worker_sha256': inputs['worker_sha256'],
               'gn_inputs_sha256': sha(target / 'GN_INPUTS.json'), 'source_projects': len(inputs['projects']),
               'selected_part_count': lock['selected_part_count'], 'rust_layout_bytes': inputs['free_hosted_rust_layout_bytes'],
               'jobs': 2, 'original_source_mutated': False, 'full375_phone': False, 'runtime': False}
    (target / 'J2_SOURCE_SUCCESSOR.json').write_text(json.dumps(receipt, indent=2) + '\n')
    for cmd in (['git', 'init', '-q', str(target)], ['git', '-C', str(target), 'add', '--'] + sorted(x.name for x in target.iterdir() if x.name != '.git'),
                ['git', '-C', str(target), '-c', 'user.name=ReMeizu', '-c', 'user.email=build@remeizu.invalid', 'commit', '-qm', 'Freeze public native intermediate j2 resource successor']):
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return receipt
