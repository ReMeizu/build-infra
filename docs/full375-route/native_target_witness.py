"""Record actual existing GN-desc output declarations and linked file identity."""
import hashlib
import json
from pathlib import Path, PurePosixPath

LABELS=(
    '//third_party/musl:soft_libc_musl_shared',
    '//commonlibrary/c_utils/base:utils',
    '//third_party/libhybris/hybris/common:libhybris-common',
    '//third_party/libhybris/hybris/common:q',
)
DECLARATIONS='NATIVE_GN_TARGET_DECLARATIONS.json'
TARGET_MAP='NATIVE_GN_TARGET_OUTPUTS.json'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024**2),b''):h.update(block)
    return h.hexdigest()

def safe(value):
    path=PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or str(path)!=value:raise ValueError('canonical actual target output required')
    return value

def write(path,data):
    pending=path.with_name('.'+path.name+'.pending')
    pending.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n');pending.replace(path)

def capture(out,inventory_sha,label,command,stdout,relative_outputs):
    """Called only on stdout returned by the unchanged real GN-desc call."""
    if label not in LABELS or not isinstance(stdout,str) or not relative_outputs:raise ValueError('actual original GN target declaration required')
    if len(command)!=6 or command[1]!='desc' or command[3:]!=[label,'outputs','--format=json']:raise ValueError('original GN-desc command identity required')
    data=json.loads(stdout)
    if not isinstance(data,dict) or set(data)!={label} or not isinstance(data[label],dict):raise ValueError('actual single default-toolchain GN response required')
    declared=data[label].get('outputs')
    if not isinstance(declared,list) or len(declared)!=len(relative_outputs) or any(not isinstance(p,str) or not p.startswith('//') for p in declared):raise ValueError('original declared output list required')
    relative_outputs=[safe(p) for p in relative_outputs]
    path=out/DECLARATIONS
    record=json.loads(path.read_text()) if path.is_file() else {'schema':'remeizu.actual-native-gn-target-declarations.v1','source_inventory_sha256':inventory_sha,'declarations':[]}
    if record['source_inventory_sha256']!=inventory_sha or label!=LABELS[len(record['declarations'])]:raise ValueError('original ordered GN target/source binding differs')
    raw=out/('native-gn-desc-'+str(len(record['declarations']))+'.json')
    with raw.open('xb') as dest:dest.write(stdout.encode('utf-8'))
    record['declarations'].append({'label':label,'actual_command':command,'declared_gn_outputs':declared,
        'relative_ninja_outputs':relative_outputs,'raw_desc':{'path':raw.name,'bytes':raw.stat().st_size,'sha256':sha(raw)}})
    write(path,record)

def complete(out,inventory_sha,libraries,source,native_out):
    """After real Ninja exit0, bind each declared output to its retained bytes."""
    record=json.loads((out/DECLARATIONS).read_text())
    if record['source_inventory_sha256']!=inventory_sha or [row['label'] for row in record['declarations']]!=list(LABELS):raise ValueError('complete exact original GN label declarations required')
    files={row['path']:row for row in libraries}
    if len(files)!=len(libraries):raise ValueError('duplicate actual linked output refused')
    labels={};used=set()
    for declaration in record['declarations']:
        raw=out/declaration['raw_desc']['path']
        if raw.is_symlink() or sha(raw)!=declaration['raw_desc']['sha256'] or raw.stat().st_size!=declaration['raw_desc']['bytes']:raise ValueError('actual GN stdout capture drift')
        names=[]
        for relative in declaration['relative_ninja_outputs']:
            path=native_out/safe(relative);path.resolve().relative_to(native_out.resolve())
            name='native-artifacts/'+str(path.relative_to(source))
            if name in used or name not in files or path.is_symlink() or not path.is_file():raise ValueError('unique genuine declared linked output required')
            artifact=out/name;artifact.resolve().relative_to(out.resolve());row=files[name]
            if artifact.is_symlink() or not artifact.is_file() or sha(path)!=row['sha256'] or sha(artifact)!=row['sha256'] or path.stat().st_size!=row['bytes'] or artifact.stat().st_size!=row['bytes']:raise ValueError('actual declared and retained output bytes differ')
            names.append(name);used.add(name)
        labels[declaration['label']]=names
    if used!=set(files):raise ValueError('unassociated output cannot become a target witness')
    result={'schema':'remeizu.native-gn-declared-target-outputs.v1','source_inventory_sha256':inventory_sha,
            'labels':labels,'declarations':record['declarations'],'actual_files':libraries,
            'actual_library_phase_exit_code':0,'targets_or_flags_changed':False,'runtime':False}
    write(out/TARGET_MAP,result)
    return result
