"""Prepared readonly source with RAM copy-up; retain only real generated files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import re
from pathlib import PurePosixPath

from full_overlay_protocol import filesystem, verify_lower, admit_upper, retain_ram_file, sha
from original_resource_snapshot import snapshot

GIB = 1024 ** 3
RAM = Path('/workspace/ram')
MERGED = RAM / 'merged'
UPPER = RAM / 'upper'


def physical_output_alias(output, ram):
    """Forge's /workspace/out bind and its RAM path share a directory inode."""
    if output.is_symlink() or filesystem(output) != 'tmpfs':
        raise ValueError('real Forge RAM artifact directory required')
    try:
        output.resolve().relative_to(ram.resolve())
        return output
    except ValueError:
        pass
    owned = ram / 'forge'
    if owned.is_symlink() or not owned.is_dir():
        raise ValueError('owned Forge RAM output binding required')
    original = output.stat()
    matches = []
    for path in owned.iterdir():
        if not re.fullmatch('[a-f0-9]{64}', path.name) or path.is_symlink() or not path.is_dir():
            continue
        actual = path.stat()
        if (actual.st_dev, actual.st_ino) == (original.st_dev, original.st_ino):
            matches.append(path)
    if len(matches) != 1:
        raise ValueError('exact unique original Forge output inode alias required')
    return matches[0]


def require_shared_ram(output, ram, upper, work=None):
    alias = physical_output_alias(output, ram)
    paths = [ram, upper, alias] + ([work] if work is not None else [])
    device = ram.stat().st_dev
    for path in paths:
        path.resolve().relative_to(ram.resolve())
        if path.is_symlink() or filesystem(path) != 'tmpfs' or path.stat().st_dev != device:
            raise ValueError('output/upper/work must share the actual owned RAM filesystem')
    return alias


def require_full_source(inputs):
    if inputs.get('full375_source_closed') is not True or inputs.get('original375_source_bindings_verified') is not True:
        raise ValueError('actual full source and original component binding proof required')
    original = inputs.get('original375_selected_parts', {})
    actual = inputs.get('actual_selected_parts', {})
    if len(original) != 375 or any(actual.get(key) != value for key, value in original.items()):
        raise ValueError('all original375 feature and syscap maps required')
    if inputs.get('original_dynamic_parts') != ['product_m5c:product_m5c', 'device_hybris_generic:device_hybris_generic']:
        raise ValueError('both original dynamic device/product parts required')
    if any(key not in actual for key in inputs['original_dynamic_parts']):
        raise ValueError('actual registration of both dynamic device/product parts required')
    if inputs.get('uninitialized_gitlinks'):
        raise ValueError('full source cannot substitute empty gitlink children')


def admit_values(row, phase, rust_bytes, copy_up_bytes):
    if phase not in ('prepare', 'libraries', 'images'):
        raise ValueError('exact original resource phase required')
    if type(rust_bytes) is not int or not 0 <= rust_bytes < GIB or type(copy_up_bytes) is not int or copy_up_bytes < 0:
        raise ValueError('measured Rust and patch copy-up bytes required')
    if row['cpu_affinity'] < 2 or (row['cpu_quota'] is not None and row['cpu_quota'] < 2):
        raise ValueError('actual two-job CPU allowance required')
    mem_floor = 12 * GIB if phase == 'prepare' else 3 * GIB
    free_floor = rust_bytes + copy_up_bytes + 6 * GIB if phase == 'prepare' else (5 * GIB if phase == 'images' else 4 * GIB)
    if row['available_bytes'] < mem_floor or row['tmpfs_free_bytes'] < free_floor:
        raise ValueError('unchanged compiler/output memory reserve refused')
    return dict(row, phase=phase, jobs=2, rust_layout_bytes=rust_bytes,
                planned_copy_up_bytes=copy_up_bytes, memory_floor_bytes=mem_floor,
                free_floor_bytes=free_floor, readonly_source_not_RAM_copy=True,
                full375_fit_proven=False, runtime=False)


def admit(output, phase, inputs):
    require_full_source(inputs)
    require_shared_ram(output, RAM, UPPER, RAM / 'work')
    row = admit_values(snapshot(output), phase, inputs['free_hosted_rust_layout_bytes'], inputs['planned_copy_up_bytes'])
    (output / ('FULL_OVERLAY_RESOURCE.' + phase + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    return row


def prepared_source(controller, output, inputs):
    require_full_source(inputs)
    if filesystem(MERGED) != 'overlay' or MERGED.is_symlink() or filesystem(RAM) != 'tmpfs':
        raise ValueError('actual host-visible prepared overlay and RAM root required')
    original = controller / 'native-source-input'
    rows = inputs['source_files']
    inventory = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if inventory != inputs['lower_inventory_sha256']:
        raise ValueError('bound original lower source inventory required')
    before = verify_lower(original, rows, inventory)
    verify_overlay_binding(MERGED, inputs, rows)
    # The merged mount must expose the same pristine source before patching.
    for row in rows:
        path = MERGED / row['path']
        if 'symlink' in row:
            if not path.is_symlink() or os.readlink(path) != row['symlink']:
                raise ValueError('prepared merged original symlink drift')
            path.resolve().relative_to(MERGED.resolve())
        elif path.is_symlink() or path.stat().st_size != row['bytes'] or sha(path) != row['sha256'] or stat.S_IMODE(path.stat().st_mode) != int(row['mode'], 8):
            raise ValueError('prepared merged original bytes or mode drift')
    if any(UPPER.iterdir()) or filesystem(RAM / 'work') != 'tmpfs' or (RAM / 'work').is_symlink():
        raise ValueError('fresh owned upper and actual RAM work required before compilation')
    projection = admit_upper(RAM, UPPER, inputs['free_hosted_rust_layout_bytes'], inputs['planned_copy_up_bytes'], snapshot(output)['available_bytes'])
    (output / 'FULL_OVERLAY_SOURCE_BEFORE.json').write_text(json.dumps({'lower': before, 'physical_RAM_admission': projection}, indent=2) + '\n')
    return original, MERGED


def verify_overlay_binding(merged, inputs, rows):
    expected = inputs.get('overlay_host_paths', {})
    if set(expected) != {'lower', 'upper', 'work'}:
        raise ValueError('exact owned host lower/upper/work mount binding required')
    parents = set()
    for name, value in expected.items():
        if not isinstance(value, str):
            raise ValueError('canonical owned host overlay paths required')
        path = PurePosixPath(value)
        if not path.is_absolute() or str(path) != value or '..' in path.parts or path.name != name or any(char in value for char in ',:\\\n'):
            raise ValueError('canonical owned host overlay paths required')
        parents.add(str(path.parent))
    if len(parents) != 1:
        raise ValueError('one owned host overlay root required')
    options = subprocess.check_output(['findmnt', '-n', '-o', 'OPTIONS', '-T', str(merged)], timeout=10).decode().strip().split(',')
    actual = dict(field.split('=', 1) for field in options if '=' in field)
    if any(actual.get(name+'dir') != value for name, value in expected.items()):
        raise ValueError('actual overlay does not bind declared owned source/upper/work')
    members = {str(path.relative_to(merged)) for path in merged.rglob('*') if path.is_file() or path.is_symlink()}
    if members != {row['path'] for row in rows}:
        raise ValueError('unlisted prepared merged source member refused')


def retain_generated(logical, output, source, upper, ram):
    relative = logical.relative_to(source)
    if not relative.parts or relative.parts[0] != 'out' or '..' in relative.parts:
        raise ValueError('only genuine generated source/out artifacts required')
    if (source / 'out').is_symlink() or (upper / 'out').is_symlink():
        raise ValueError('generated output roots cannot be source aliases')
    logical.resolve().relative_to((source / 'out').resolve())
    if logical.is_symlink() or not logical.is_file():
        raise ValueError('actual regular generated artifact required')
    physical = upper / relative
    physical.resolve().relative_to((upper / 'out').resolve())
    if physical.is_symlink() or not physical.is_file() or physical.stat().st_size != logical.stat().st_size or sha(physical) != sha(logical):
        raise ValueError('logical output must match its genuine physical RAM upper file')
    target = 'native-artifacts/' + str(relative)
    artifact_root = require_shared_ram(output, ram, upper)
    existing = artifact_root / target
    for ancestor in existing.parents:
        if ancestor == artifact_root:
            break
        if ancestor.is_symlink() or (ancestor.exists() and not ancestor.is_dir()):
            raise ValueError('retained artifact ancestors cannot be aliases')
    existing.resolve().relative_to(artifact_root.resolve())
    if existing.exists() or existing.is_symlink():
        if existing.is_symlink() or existing.stat().st_dev != physical.stat().st_dev or existing.stat().st_ino != physical.stat().st_ino or sha(existing) != sha(physical):
            raise ValueError('retained output conflicts with original RAM file')
    else:
        retain_ram_file(physical, artifact_root, target, sha(physical), ram)
    visible = output / target
    if visible.is_symlink() or not visible.is_file() or (visible.stat().st_dev, visible.stat().st_ino) != (physical.stat().st_dev, physical.stat().st_ino):
        raise ValueError('retained artifact is not visible through actual Forge output bind')
    return target


def retain_output(logical, output, source):
    return retain_generated(logical, output, source, UPPER, RAM)


def source_after(controller, output, inputs):
    require_full_source(inputs)
    proof = verify_lower(controller / 'native-source-input', inputs['source_files'], inputs['lower_inventory_sha256'])
    (output / 'FULL_OVERLAY_SOURCE_AFTER.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof
