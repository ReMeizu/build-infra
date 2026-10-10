"""Separate full-source RAM allocation/artifact protocol; no old guard changes."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

GIB=1024**3

def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for data in iter(lambda:source.read(1024**2),b''):value.update(data)
    return value.hexdigest()

def filesystem(path):
    return subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',str(path)],timeout=10).decode().strip()

def verify_lower(root,rows,expected_inventory_sha256):
    """Exact original byte/mode/link identity; never inspect or copy Git metadata."""
    import json
    if hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=expected_inventory_sha256:raise ValueError('exact lower inventory binding required')
    if root.is_symlink() or filesystem(root)=='tmpfs':raise ValueError('readonly disk lower source required')
    options=subprocess.check_output(['findmnt','-n','-o','OPTIONS','-T',str(root)],timeout=10).decode().strip().split(',')
    if 'ro' not in options:raise ValueError('actual lower readonly bind mount required')
    if (root/'.git').exists() or (root/'out').exists():raise ValueError('sanitized source lower must exclude root Git metadata and generated out')
    actual={str(path.relative_to(root)) for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    if actual!={row['path'] for row in rows}:raise ValueError('no unlisted executable or opaque source lower members admitted')
    for row in rows:
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:raise ValueError('canonical source-only lower member required')
        path=root/relative
        if 'symlink' in row:
            if not path.is_symlink() or os.readlink(path)!=row['symlink']:raise ValueError('lower original symlink identity differs')
        elif (path.is_symlink() or not path.is_file() or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256'] or (path.stat().st_mode&0o777)!=int(row['mode'],8)):
            raise ValueError('lower original source SHA/size/mode differs')
    return {'lower_inventory_sha256':expected_inventory_sha256,'source_files':len(rows),'source_identity_verified':True,'full375_dependency_closure':False,'full375_images':False}

def admit_upper(ram,upper,rust_bytes,planned_copy_up_bytes,available_bytes):
    """New physical allocation model; original whole-source allocator stays intact."""
    if filesystem(ram)!='tmpfs' or filesystem(upper)!='tmpfs' or upper.is_symlink():raise ValueError('actual RAM upper/work/output required')
    upper.resolve().relative_to(ram.resolve())
    if type(rust_bytes) is not int or not 0<=rust_bytes<GIB or type(planned_copy_up_bytes) is not int or planned_copy_up_bytes<0:raise ValueError('measured original Rust and actual patch copy-up projection required')
    needed=rust_bytes+planned_copy_up_bytes+6*GIB
    if available_bytes<12*GIB or shutil.disk_usage(ram).free<needed:raise ValueError('RAM upper projection and unchanged output/memory reserve refused')
    return {'actual_RAM_free_bytes':shutil.disk_usage(ram).free,'Rust_RAM_bytes':rust_bytes,'planned_copy_up_bytes':planned_copy_up_bytes,'retained_prepare_output_reserve_bytes':6*GIB,'physical_RAM_floor_bytes':needed,'readonly_lower_source_bytes_not_copied':True,'full375_fit_proven':False}

def retain_ram_file(physical_upper_file,artifact_root,relative,expected_sha256,ram):
    """Zero-copy hardlink from physical RAM upper to genuine Forge artifact root."""
    target=artifact_root/relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or not re.fullmatch('[a-f0-9]{64}',expected_sha256):raise ValueError('bound native artifact member required')
    for path in (physical_upper_file,artifact_root):
        path.resolve().relative_to(ram.resolve())
        if path.is_symlink() or filesystem(path)!='tmpfs':raise ValueError('physical same-RAM upper/artifact path required')
    if not physical_upper_file.is_file() or sha(physical_upper_file)!=expected_sha256 or target.exists():raise ValueError('actual complete output full SHA/fresh artifact required')
    target.parent.mkdir(parents=True,exist_ok=True);os.link(physical_upper_file,target)
    if sha(target)!=expected_sha256 or target.stat().st_ino!=physical_upper_file.stat().st_ino or target.stat().st_dev!=physical_upper_file.stat().st_dev:raise ValueError('actual same-inode RAM artifact binding failed')
    return {'artifact_sha256':expected_sha256,'artifact_bytes':target.stat().st_size,'actual_same_inode_RAM_hardlink':True,'target_compilation_proven_by_filesystem_control':False}
