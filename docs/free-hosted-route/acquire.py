"""Anonymous exact-pin public inputs, on ephemeral disk, without private carriers."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import urllib.parse
import urllib.request
from make_j2_successor import safe
from diagnostics import PublicInputError
from materialize_lfs import materialize

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024**2), b''):
            h.update(b)
    return h.hexdigest()

def public_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != 'https' or u.username or u.password or u.query or u.fragment or u.port not in (None,443):
        raise ValueError('anonymous canonical HTTPS input required')
    allowed = {'github.com','codeload.github.com','raw.githubusercontent.com','gitcode.com','gitee.com',
               'repo.huaweicloud.com','files.pythonhosted.org','mirrors.huaweicloud.com','api.gitcode.com'}
    if u.hostname not in allowed:
        raise ValueError('public source host outside reviewed allowlist')
    return url

def run(argv, **kwargs):
    return subprocess.run([str(x) for x in argv], check=True, capture_output=True, timeout=kwargs.pop('timeout',1200), **kwargs)

def download(row, dest):
    public_url(row['url'])
    if dest.exists():
        raise ValueError('new verified source download required')
    digest = row.get('archive_sha256',row.get('sha256'))
    size = row.get('archive_bytes',row.get('bytes'))
    if not isinstance(size,int) or size <= 0 or not isinstance(digest,str) or len(digest)!=64:
        raise ValueError('download exact size/hash missing')
    partial=dest.with_suffix(dest.suffix+'.partial')
    h=hashlib.sha256(); count=0
    with urllib.request.urlopen(row['url'],timeout=90) as response, partial.open('xb') as out:
        public_url(response.url)
        for data in iter(lambda:response.read(1024**2), b''):
            count+=len(data)
            if count>size:
                raise ValueError('public input exceeds exact admitted length')
            out.write(data);h.update(data)
    if count!=size or h.hexdigest()!=digest:
        raise ValueError('public input full size/hash differs')
    partial.rename(dest)

def extract_tool(archive, root, row):
    root.mkdir(parents=True,exist_ok=True)
    if row.get('kind','tar')=='file':
        target=root/safe(row['file_name'])
        target.parent.mkdir(parents=True,exist_ok=True)
        with archive.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
        target.chmod(row.get('mode',0o755));return
    strip=row.get('strip_components',0)
    if strip not in (0,1):raise ValueError('unsupported original tool extraction prefix')
    mapping=row.get('member_map'); seen=set(); links=[]
    with tarfile.open(archive,'r:*') as tar:
        for m in tar:
            name=m.name.removeprefix('./')
            if name in ('','.'):continue
            name=str(safe(name))
            if mapping is not None:
                if name not in mapping:continue
                destination=str(safe(mapping[name]))
            else:
                parts=PurePosixPath(name).parts[strip:]
                if not parts:continue
                destination=str(safe('/'.join(parts)))
            dest=root/destination
            dest.resolve().relative_to(root.resolve())
            if m.isdir():dest.mkdir(parents=True,exist_ok=True);continue
            if destination in seen or dest.exists() or dest.is_symlink():raise ValueError('tool output collision')
            seen.add(destination)
            dest.parent.mkdir(parents=True,exist_ok=True)
            if m.issym():
                target=PurePosixPath(m.linkname)
                if target.is_absolute():raise ValueError('tool absolute symlink')
                (dest.parent/m.linkname).resolve().relative_to(root.resolve())
                links.append((dest,m.linkname));continue
            if m.islnk():safe(m.linkname)
            if not m.isfile() and not m.islnk():raise ValueError('tool archive special member refused')
            with tar.extractfile(m) as src,dest.open('xb') as dst:shutil.copyfileobj(src,dst)
            dest.chmod(m.mode & 0o777)
    for dest,target in links:dest.symlink_to(target)
    if mapping is not None and set(mapping.values())!=seen:raise ValueError('incomplete exact tool member mapping')

def verify(root,row,diagnostic_member=None):
    path=root/safe(row['path'])
    member=row['path'] if diagnostic_member is None else diagnostic_member
    if 'symlink' in row:
        if not path.is_symlink() or os.readlink(path)!=row['symlink']:raise PublicInputError('SOURCE_LINK_MISMATCH',member)
        try:path.resolve().relative_to(root.resolve())
        except ValueError:raise PublicInputError('SOURCE_LINK_ESCAPE',member) from None
    else:
        if not path.is_file() or path.is_symlink() or sha(path)!=row['sha256']:raise PublicInputError('SOURCE_BYTES_MISMATCH',member)
        if 'bytes' in row and path.stat().st_size!=row['bytes']:raise PublicInputError('SOURCE_SIZE_MISMATCH',member)
        if 'mode' in row:
            mode=int(row['mode'],8) if isinstance(row['mode'],str) else row['mode']
            if stat.S_IMODE(path.stat().st_mode)!=mode:raise PublicInputError('SOURCE_MODE_MISMATCH',member)
    return path

def validate_lock(lock,inputs):
    if lock.get('schema')!='remeizu.free-hosted-native-public-inputs.v1' or lock.get('public_sources_only') is not True or lock.get('private_android_inputs') is not False:
        raise ValueError('reviewed source-only public acquisition lock required')
    if lock.get('source_projects')!=136 or lock.get('selected_part_count')!=110 or len(inputs['projects'])!=136 or lock.get('source_bytes')!=inputs.get('source_bytes'):
        raise ValueError('genuine reviewed 136/110 intermediate required; full375 not admitted')
    if lock.get('gn_inputs_sha256')!='c84761f5a94a3370aca702e6bdea222b3049b626ecfce9fc8987e6467ad26aa4':
        raise ValueError('reviewed measured cohort GN identity differs')
    proof_row=lock.get('cohort_proof',{})
    if proof_row!={'path':'inputs/RUST_CXX_COHORT_PROOF.a1.json','sha256':'e9bfe8607eaf598afa02a1b0c642c7a9a9010fd6ebe58e4452bf68f47bcd2b8e'}:
        raise ValueError('reviewed production cohort proof identity missing')
    actual={p['path']:p for p in inputs['projects']}
    if {x['path'] for x in lock['projects']}!=set(actual):raise ValueError('public source project coverage differs')
    for p in lock['projects']:
        if p['head']!=actual[p['path']]['head'] or p['git_tree']!=actual[p['path']]['git_tree']:raise ValueError('public source original pin changed')
        public_url(p['url']);safe(p['path'])
    if {x['payload_root'] for x in lock['tools']}!={x['payload_root'] for x in inputs['tools']}:
        raise ValueError('official tool root coverage differs')
    if {x['path']:x['sha256'] for x in lock['wheels']}!={x['path']:x['sha256'] for x in inputs['python_wheels']}:
        raise ValueError('offline wheel coverage differs')
    for item in lock['tools']+lock['wheels']:public_url(item['url'])


def validate_cohort_proof(lock,inputs,thin):
    if sha(thin/'GN_INPUTS.json')!=lock['gn_inputs_sha256']:raise ValueError('reviewed measured GN inventory bytes differ')
    row=lock['cohort_proof'];path=thin/safe(row['path'])
    if sha(path)!=row['sha256']:raise ValueError('reviewed measured cohort proof bytes differ')
    proof=json.loads(path.read_text())
    if proof.get('schema')!='remeizu.public-native-cohort-successor.v1' or proof.get('parent_gn_inputs_sha256')!='6e222d71be39e5ae6282ae6abca56d86be3aa0ac8af99f9f22a9428f71f53e6a' or proof.get('parent_public_lock_sha256')!='b1155bfed25503b75b6ea9bf19e92601c94b064ae8e16bbc3e1ba1759f1a3e36':
        raise ValueError('reviewed cohort original parent binding differs')
    baseline=proof['baseline_selected_parts'];actual=proof['actual_selected_parts']
    if len(baseline)!=72 or len(actual)!=lock['selected_part_count'] or any(actual.get(k)!=v for k,v in baseline.items()):
        raise ValueError('reviewed original parts/features/syscaps were not retained')
    if not proof.get('all_parent_source_rows_retained_unchanged') or not proof.get('all_parent_project_rows_retained_unchanged') or proof.get('full375_phone') or proof.get('runtime'):
        raise ValueError('reviewed cohort preservation boundary differs')
    for key,expected in [('baseline_source_files_sha256','01905ce5a7abac83939231a00251fc731428438055e7bcaf393a2ac04c3acd54'),('baseline_tools_sha256','433cc8f1fa9b567bfe4367c18bc184b22c720d90f56ada12732f7d40abb9aecf'),('baseline_python_wheels_sha256','f8fffec8e9bae98bc13784d72c9e7a43670c8451eaf7b480b923c7aa503a243c')]:
        if proof.get(key)!=expected:raise ValueError('reviewed original source/SDK/wheels identity differs')
    canonical=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if canonical(inputs['tools'])!=proof['baseline_tools_sha256'] or canonical(inputs['python_wheels'])!=proof['baseline_python_wheels_sha256']:
        raise ValueError('actual original SDK/wheel members changed')
    old_paths=[p['path'] for p in proof['baseline_source_projects']]
    old_rows={r['path']:r for r in inputs['source_files'] if r['path']=='.gn' or any(r['path'].startswith(p+'/') for p in old_paths)}
    if canonical(old_rows)!=proof['baseline_source_files_sha256']:raise ValueError('actual original source bytes/modes/links changed')
    project_map={p['path']:(p['head'],p['git_tree']) for p in inputs['projects']}
    for p in proof['baseline_source_projects']+proof['added_projects']:
        if project_map.get(p['path'])!=(p['head'],p['git_tree']):raise ValueError('reviewed production project identity differs')
    if len(proof['baseline_source_projects'])+len(proof['added_projects'])!=len(project_map) or proof['source_bytes']!=inputs['source_bytes'] or proof['source_file_count']!=len(inputs['source_files']):
        raise ValueError('reviewed measured production source inventory differs')
    sdk_projects=('interface/sdk-js', 'arkcompiler/ets_frontend', 'third_party/zlib', 'third_party/protobuf', 'third_party/typescript', 'developtools/ace_ets2bundle', 'third_party/abseil-cpp')
    sdk_parts={'arkcompiler:ets_frontend', 'sdk:sdk', 'thirdparty:abseil-cpp', 'thirdparty:zlib', 'thirdparty:protobuf', 'developtools:ace_ets2bundle', 'thirdparty:typescript'}
    storage_projects=('base/powermgr/power_manager', 'base/security/dataclassification', 'base/tee/tee_client', 'foundation/communication/netmanager_base', 'foundation/distributeddatamgr/preferences', 'foundation/distributedhardware/device_manager', 'foundation/filemanagement/dfs_service', 'foundation/filemanagement/storage_service', 'foundation/resourceschedule/memmgr', 'third_party/exfatprogs', 'third_party/gptfdisk', 'third_party/libfuse', 'third_party/ntfs-3g')
    storage_parts={'distributeddatamgr:preferences', 'distributedhardware:device_manager', 'thirdparty:exfatprogs', 'filemanagement:storage_service', 'thirdparty:libfuse', 'powermgr:power_manager', 'filemanagement:dfs_service', 'security:dataclassification', 'thirdparty:ntfs-3g', 'tee:tee_client', 'communication:netmanager_base', 'resourceschedule:memmgr', 'thirdparty:gptfdisk', 'thirdparty:f2fs-tools'}
    rust_projects=('third_party/rust/crates/cxx', 'third_party/rust/crates/clap', 'third_party/rust/crates/codespan', 'third_party/rust/crates/is-terminal', 'third_party/rust/crates/strsim-rs', 'third_party/rust/crates/termcolor', 'third_party/rust/crates/heck', 'third_party/rust/crates/unicode-width', 'third_party/rust/crates/os_str_bytes', 'third_party/rust/crates/io-lifetimes', 'third_party/rust/crates/rustix', 'third_party/rust/crates/memchr', 'third_party/rust/crates/linux-raw-sys')
    rust_parts={'thirdparty:rust_cxx'}
    parent=proof.get('source_admitted_parent101',{})
    if (parent.get('source_lock_sha256')!='cd0fd17d93ddf0c7f4cd2da211fafb746cca9aaf8e16e8a9f4867e9700cce4c0' or
            parent.get('gn_inputs_sha256')!='bc5b4da2894494c066978098d9e811cb208fca87588c1e73c0dea4f45e4d4e06' or
            parent.get('cohort_proof_sha256')!='8f92eec4f3e22a3afa1a91d3c08a555dc04b9bf7507f69f063eec09e03c5af9e' or
            parent.get('source_projects')!=101 or parent.get('selected_part_count')!=85):
        raise ValueError('source-admitted A6 immediate parent binding differs')
    parent_projects=[r for r in inputs['projects'] if r['path'] not in ('foundation/ability/idl_tool','commonlibrary/memory_utils')+sdk_projects+storage_projects+rust_projects]
    if len(parent_projects)!=101 or canonical(parent_projects)!='62e1c19c6a23411dad1dc38ccdaa22257c1b392267d2bcdd7702881c6dca2a0b':
        raise ValueError('source-admitted parent101 project rows changed')
    parent_rows={r['path']:r for r in inputs['source_files'] if not r['path'].startswith(('foundation/ability/idl_tool/','commonlibrary/memory_utils/')+tuple(p+'/' for p in sdk_projects+storage_projects+rust_projects))}
    if len(parent_rows)!=174299 or canonical(parent_rows)!='19a2f1db71a4aea28a2b04cc1da9d7fb8ecb7d4f8bf01fe37eca0cf7da27efe5':
        raise ValueError('source-admitted parent101 source rows changed')
    parent_parts=parent.get('selected_parts',{})
    if (len(parent_parts)!=85 or canonical(parent_parts)!='c5e92ea246fd97fe8a15642b2ca9ceeee9e9ca55470157e5949e086952bb6c84' or
            any(actual.get(k)!=v for k,v in parent_parts.items()) or set(actual)-set(parent_parts)!=({'ability:idl_tool','hdf:drivers_interface_memorytracker','commonlibrary:memory_utils'}|sdk_parts|storage_parts|rust_parts)):
        raise ValueError('source-admitted parent85 parts/features changed')
    parent_selector=parent.get('final_selector',{})
    if parent_selector!={'path':'inputs/public-relational-production-product.json','sha256':'c2a2f2061234de77b6103b473ec6ed2b2e261fceaa38b3d873cc6875e36ff41c'} or sha(thin/safe(parent_selector['path']))!=parent_selector['sha256']:
        raise ValueError('source-admitted A6 selector changed')
    immediate=proof.get('source_admitted_parent102',{})
    if (immediate.get('source_lock_sha256')!='c6bad3ed0f68ff1c8ee5bbbd82921468e8e76b26c82d54d79ce68427c9af7aa1' or
            immediate.get('gn_inputs_sha256')!='fd12937cafbb5c2e0d785a35529e96e0a7c572700243c05cdc38ddb1a2b87885' or
            immediate.get('cohort_proof_sha256')!='98ec359c29a5c64bc60776e672ecf9269c59c96d4dd099cf309ce41d7103f4b0' or
            immediate.get('source_projects')!=102 or immediate.get('selected_part_count')!=86):
        raise ValueError('actual A7 immediate parent identity differs')
    rows102={r['path']:r for r in inputs['source_files'] if not r['path'].startswith(('commonlibrary/memory_utils/',)+tuple(p+'/' for p in sdk_projects+storage_projects+rust_projects))}
    projects102=[r for r in inputs['projects'] if r['path'] not in ('commonlibrary/memory_utils',)+sdk_projects+storage_projects+rust_projects]
    if len(rows102)!=177773 or canonical(rows102)!='ae02161020c82cb309106c56e0209a236f41cf9407f43fabb47be7059df95c6e':
        raise ValueError('actual A7 source102 rows changed')
    if len(projects102)!=102 or canonical(projects102)!='3a1b12e0fd76f95c544a6c7d26ed703211ab0452739a71cf0ee08e95cba34856':
        raise ValueError('actual A7 project102 rows changed')
    parts86=immediate.get('selected_parts',{})
    if (len(parts86)!=86 or canonical(parts86)!='d4ff2b84c94bf55c2c08e008b17cea09544d8c82384cf0d05f9df908e7f462b0' or
            any(actual.get(k)!=v for k,v in parts86.items()) or set(actual)-set(parts86)!=({'hdf:drivers_interface_memorytracker','commonlibrary:memory_utils'}|sdk_parts|storage_parts|rust_parts)):
        raise ValueError('actual A7 part86 feature preservation differs')
    selector86=immediate.get('final_selector',{})
    if selector86!={'path':'inputs/public-idl-tool-product.json','sha256':'019c9e9b5c0ecddf2f91489768abbc1fbebfc5bc4f3cbd99ae656608554b9ede'} or sha(thin/safe(selector86['path']))!=selector86['sha256']:
        raise ValueError('actual A7 selector changed')
    parent103=proof.get('source_admitted_parent103',{})
    if (parent103.get('source_lock_sha256')!='75694eb3607edd20ad452a05882576552e0186ce64cf969c128437f8612e0bee' or
            parent103.get('gn_inputs_sha256')!='6718cc2eec672b640c46cd1c03ab353485d02b000887e26e1e90b831d344a022' or
            parent103.get('cohort_proof_sha256')!='bdef08ae8117c56669e4d359003b398e17d87d0e2f02f8937804dd925f14b840' or
            parent103.get('source_projects')!=103 or parent103.get('selected_part_count')!=88):
        raise ValueError('actual A8 immediate parent identity differs')
    rows103={r['path']:r for r in inputs['source_files'] if not r['path'].startswith(tuple(p+'/' for p in sdk_projects+storage_projects+rust_projects))}
    projects103=[r for r in inputs['projects'] if r['path'] not in sdk_projects+storage_projects+rust_projects]
    if len(rows103)!=177823 or canonical(rows103)!='2f45fd05c3c605b0387de37c03318c3baf40a958759a1ccf6e32902b85c0911c':
        raise ValueError('actual A8 source103 rows changed')
    if len(projects103)!=103 or canonical(projects103)!='31168cec7f3ba925b9965611b52eb93f2b34cf374355c8f1e68ae58fedfde087':
        raise ValueError('actual A8 project103 rows changed')
    parts88=parent103.get('selected_parts',{})
    if (len(parts88)!=88 or canonical(parts88)!='00d6c3b85aa8c8a85e9884b541d4717b890e6fbd8347bd2d8c7aea52a72eef98' or
            any(actual.get(k)!=v for k,v in parts88.items()) or set(actual)-set(parts88)!=(sdk_parts|storage_parts|rust_parts)):
        raise ValueError('actual A8 part88 feature preservation differs')
    selector88=parent103.get('final_selector',{})
    if selector88!={'path': 'inputs/public-memorytracker-product.json', 'sha256': 'd4147a7f37f96cdfa76de14391ceaba264bce15dad74199986abd3eb9994373c'} or sha(thin/safe(selector88['path']))!=selector88['sha256']:
        raise ValueError('actual A8 selector changed')
    closure=proof.get('sdk_production_closure',{})
    if (tuple(closure.get('approved_projects',[]))!=sdk_projects or closure.get('compiler_tool_archives_changed') is not False or
            closure.get('compiler_version_changed') is not False or closure.get('ets_targets_skipped') is not False or
            closure.get('abseil_required_by_protobuf') is not True or closure.get('frontend_independent_compiler_branch_unchanged_false') is not True):
        raise ValueError('actual SDK production closure boundary differs')
    witness=closure.get('compiler_mode_witness',{})
    if witness!={'path': 'build/config/BUILDCONFIG.gn', 'sha256': '068e37b0c9d7d4acb45a4d52a6f567c3bf1807906f82f90637728c1846375038', 'value': False} or next((r.get('sha256') for r in inputs['source_files'] if r['path']==witness['path']),None)!=witness['sha256']:
        raise ValueError('actual SDK original compiler mode witness differs')
    parent110=proof.get('source_admitted_parent110',{})
    if (parent110.get('source_lock_sha256')!='64bbb0df96cdecb99c69e440a4cdf79d1aa8a6f7ad6a580d26624d74739b32cb' or
            parent110.get('gn_inputs_sha256')!='f4f6a616da4127f3a1a137ac5a936d0ce8561a82d557d1a6b078bb6819e40eab' or
            parent110.get('cohort_proof_sha256')!='08e0c21c70bd0c61b08d0078a34475cc088308f8fb3a96936fa42871e33b9965' or
            parent110.get('source_projects')!=110 or parent110.get('selected_part_count')!=95):
        raise ValueError('actual A9 immediate parent identity differs')
    rows110={r['path']:r for r in inputs['source_files'] if not r['path'].startswith(tuple(p+'/' for p in storage_projects+rust_projects))}
    projects110=[r for r in inputs['projects'] if r['path'] not in storage_projects+rust_projects]
    if len(rows110)!=282999 or canonical(rows110)!='c3cf4c90df6cc81225a6c12050a1f6d56dc4fdbe794dce9a26dc1948c9498114':
        raise ValueError('actual A9 source110 rows changed')
    if len(projects110)!=110 or canonical(projects110)!='6788ea36d8821ce4f0dc1619b051f3d541ffd1f2880f75f7cf7f35a1efc2a5bf':
        raise ValueError('actual A9 project110 rows changed')
    parts95=parent110.get('selected_parts',{})
    if (len(parts95)!=95 or canonical(parts95)!='1a011bdc7b45ddaff935ce08693e72e51ceb03aa0f420cd1fe94fc5292703861' or
            any(actual.get(k)!=v for k,v in parts95.items()) or set(actual)-set(parts95)!=(storage_parts|rust_parts)):
        raise ValueError('actual A9 part95 feature preservation differs')
    selector95=parent110.get('final_selector',{})
    if selector95!={'path': 'inputs/public-sdk-production-product.json', 'sha256': '31ccdf0134844ab46f6f8e9a6f9997d3d91adf0d1314f18ccdb106f394d56164'} or sha(thin/safe(selector95['path']))!=selector95['sha256']:
        raise ValueError('actual A9 selector changed')
    storage=proof.get('storage_production_closure',{})
    if (tuple(storage.get('approved_new_projects',[]))!=storage_projects or set(storage.get('added_parts',[]))!=storage_parts or
            storage.get('existing_source_registration')!='thirdparty:f2fs-tools' or storage.get('new_component_feature_overrides') is not False or
            storage.get('unselected_conditional_neighbors_activated') is not False or storage.get('sdk_tools_worker_compiler_flags_changed') is not False or
            storage.get('closure_complete') is not False):
        raise ValueError('actual storage production closure boundary differs')
    defaults=storage.get('original_defaults_witnesses',{})
    if defaults!={'foundation/filemanagement/dfs_service/distributedfile.gni': {'sha256': '8e77714f54ba17176528a258cfc2e9e1bdf8f7399b4e2b0f39d3a78186b9fe20', 'unchanged_values': {'dfs_service_feature_enable_dist_file_daemon': True, 'dfs_service_feature_enable_distributed_ability': True}}, 'foundation/filemanagement/storage_service/storage_service_aafwk.gni': {'sha256': 'ec6eeb6231ab9828f758df8dc79e1a967d434f076212f260d905cf9913b4813a', 'unchanged_values': {'storage_service_cloud_fuse': True, 'storage_service_external_storage_manager': True, 'storage_service_fstools': True}}}:
        raise ValueError('actual storage original feature defaults differ')
    for name,row in defaults.items():
        if next((r.get('sha256') for r in inputs['source_files'] if r['path']==name),None)!=row['sha256']:
            raise ValueError('actual storage original feature source differs')
    parent123=proof.get('immediate_parent',{})
    if (parent123.get('source_lock_sha256')!='9a110423d47de74e663cc4d504f95303a5f97bb62a88e502423cfdae0a43da0d' or
            parent123.get('gn_inputs_sha256')!='a0fff331eac3f3594631b39be05b8f75f78dbfc87ba23798146db926f1ac0ba6' or
            parent123.get('cohort_proof_sha256')!='a72a3cba20cf2e1ae2d386631ac67b867bcdf224909347a1f025d41bfc1a689c' or
            parent123.get('source_projects')!=123 or parent123.get('selected_part_count')!=109):
        raise ValueError('actual A10 immediate parent identity differs')
    rows123={r['path']:r for r in inputs['source_files'] if not r['path'].startswith(tuple(p+'/' for p in rust_projects))}
    projects123=[r for r in inputs['projects'] if r['path'] not in rust_projects]
    if len(rows123)!=290070 or canonical(rows123)!='2b4328466fe4636613054aeb62ca59a6e1a2da21b02fa46565488853afbf1173':
        raise ValueError('actual A10 source123 rows changed')
    if len(projects123)!=123 or canonical(projects123)!='847df9bc2584c94ce1979f17e1e96f5033e7e22fd68998abe48d083630a7a541':
        raise ValueError('actual A10 project123 rows changed')
    parts109=parent123.get('selected_parts',{})
    if (len(parts109)!=109 or canonical(parts109)!='cae3552f3dd4dec1c443526d69da6faf64876a06d558580a48083c8f9504b417' or
            any(actual.get(k)!=v for k,v in parts109.items()) or set(actual)-set(parts109)!=rust_parts):
        raise ValueError('actual A10 part109 feature preservation differs')
    selector109=parent123.get('final_selector',{})
    if selector109!={'path': 'inputs/public-storage-production-product.json', 'sha256': '89c1486088efe8b7c29bc1f5cc189798bcdd8bee83f067177a4004df3fa0e15f'} or sha(thin/safe(selector109['path']))!=selector109['sha256']:
        raise ValueError('actual A10 selector changed')
    rust=proof.get('rust_cxx_production_closure',{})
    if (tuple(rust.get('approved_new_projects',[]))!=rust_projects or rust.get('only_selected_new_part')!='thirdparty:rust_cxx' or
            rust.get('compiler_rust_tool_versions_changed') is not False or rust.get('crate_features_changed') is not False or
            rust.get('original_independent_compiler_mode_false') is not True or rust.get('source_dependency_components_selected') is not False or
            rust.get('optional_gitlink_used_by_reached_gn') is not False or rust.get('full_recursive_source_closure') is not False):
        raise ValueError('actual CXX original compiler/source boundary differs')
    optional=rust.get('optional_uninitialized_gitlinks',[])
    if optional!=[{'directory_mode': 493, 'git_mode': '160000', 'git_object': '37752b6ec36a68c169053cb3f7ba359b677a22b6', 'materialized': False, 'path': 'third_party/rust/crates/cxx/tools/buck/prelude', 'recursive_source_closure': False}]:
        raise ValueError('actual CXX optional gitlink scope differs')
    parent_gitlinks=[{'directory_mode':493,'git_mode':'160000','git_object':'cc2552eb551e806e6892fe6871de7b173943afb6','materialized':False,
                      'path':'arkcompiler/runtime_core/static_core/tools/plugins/ecmascript','recursive_source_closure':False}]
    if inputs.get('uninitialized_gitlinks')!=parent_gitlinks+optional:
        raise ValueError('actual CXX original/gitlink scope changed')
    project=next(r for r in inputs['projects'] if r['path']=='third_party/rust/crates/cxx')
    locked=next(r for r in lock['projects'] if r['path']==project['path'])
    if project.get('recursive_source_closure') is not False or project.get('uninitialized_gitlinks')!=optional or locked.get('uninitialized_gitlinks')!=optional:
        raise ValueError('actual CXX project falsely claims recursive source closure')
    source_map={r['path']:r for r in inputs['source_files']}
    for edge in rust.get('direct_gn_source_dependency_edges',[]):
        if source_map.get(edge['path'],{}).get('sha256')!=edge['sha256']:
            raise ValueError('actual CXX production GN edge source differs')
    trigger=next(r for r in rust['direct_gn_source_dependency_edges'] if r['dependency_provider']=='third_party/rust/crates/cxx')
    if trigger['path']!='build/templates/rust/rust_cxx.gni' or trigger['line']!=40 or trigger['label']!='rust_cxx:cxxbridge($host_toolchain)':
        raise ValueError('actual CXX fatal active host-tool edge differs')
    for key in ('baseline_selector','final_selector'):
        r=proof[key]
        if sha(thin/safe(r['path']))!=r['sha256']:raise ValueError('reviewed production selector bytes differ')
    source_map={r['path']:r for r in inputs['source_files']}
    existing=proof.get('existing_source_component_additions',[])
    if len(existing)!=2 or {r.get('part') for r in existing}!={'hdf:drivers_interface_memorytracker','thirdparty:f2fs-tools'}:
        raise ValueError('actual pinned existing-source component registrations differ')
    for row in existing:
        if project_map.get(row['provider_path'])!=(row['head'],row['git_tree']) or source_map.get(row['bundle_path'],{}).get('sha256')!=row['bundle_sha256']:
            raise ValueError('existing pinned component provider/bundle differs')
    for r in proof['inherit_inputs']:
        if source_map.get(r['path'],{}).get('sha256')!=r['sha256']:raise ValueError('reviewed inherited selection source differs')
    final=[r for r in inputs['overlay_files'] if r['target']=='vendor/oniro/m5c/config.json'][-1]
    if final['path']!=proof['final_selector']['path'] or final['sha256']!=proof['final_selector']['sha256']:
        raise ValueError('reviewed actual final selector overlay differs')
    from libhybris_patch_guard import validate_patch_source_correction
    validate_patch_source_correction(lock,inputs,thin)
    return proof

def acquire(lock,thin,dest):
    if dest.exists():raise ValueError('fresh public source acquisition root required')
    inputs=json.loads((thin/'GN_INPUTS.json').read_text())
    if sha(thin/'GN_INPUTS.json')!=lock['gn_inputs_sha256']:raise ValueError('public GN inventory hash differs')
    validate_lock(lock,inputs)
    validate_cohort_proof(lock,inputs,thin)
    floor=lock['expanded_bytes']+sum(x['archive_bytes'] for x in lock['tools'])+2*inputs['source_bytes']+3*1024**3
    if shutil.disk_usage(dest.parent).free<floor:raise ValueError('actual disk cannot retain verified source/tools/downloads/Docker headroom')
    dest.mkdir(); original=dest/'original';shutil.copytree(thin,original)
    if any(p.name=='.git' or p.suffix in ('.bundle','.private') or '.private.' in p.name or 'ORIGINAL_FREEZE' in p.name for p in original.rglob('*')):
        raise ValueError('opaque/private carrier member in thin source export')
    checkouts=dest/'checkouts';checkouts.mkdir();downloads=dest/'downloads';downloads.mkdir()
    checkout_map={};proofs=[];lfs_materialization=[]
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_LFS_SKIP_SMUDGE='1')
    for i,p in enumerate(lock['projects']):
        print('PUBLIC_NATIVE_FETCH_PROJECT_BEGIN',i+1,len(lock['projects']),flush=True)
        target=checkouts/str(i);target.mkdir()
        run(['git','init','-q',target]);run(['git','-C',target,'remote','add','origin',p['url']])
        run(['git','-C',target,'-c','credential.helper=','fetch','--depth=1','origin',p['head']],env=env)
        run(['git','-C',target,'checkout','--detach','FETCH_HEAD'],env=env)
        if p.get('lfs_required'):
            run(['git','lfs','version']);run(['git','-C',target,'-c','credential.helper=','lfs','fetch','origin',p['head']],env=env)
            run(['git','-C',target,'lfs','checkout'],env=env)
        lfs_materialization.extend(materialize(target,p,env))
        head=run(['git','-C',target,'rev-parse','HEAD']).stdout.decode().strip()
        tree=run(['git','-C',target,'rev-parse','HEAD^{tree}']).stdout.decode().strip()
        if head!=p['head'] or tree!=p['git_tree']:raise ValueError('anonymous fetched original Git identity differs')
        checkout_map[p['path']]=target;proofs.append({'path':p['path'],'head':head,'git_tree':tree})
        print('PUBLIC_NATIVE_FETCH_PROJECT_PIN_PASS',i+1,len(lock['projects']),flush=True)
    source=original/'native-source-input';source.mkdir()
    owners=sorted(checkout_map,key=len,reverse=True)
    print('PUBLIC_NATIVE_MATERIALIZE_SOURCE_BEGIN',len(inputs['source_files']),flush=True)
    for row in inputs['source_files']:
        owner=next((x for x in owners if row['path'].startswith(x+'/')),None)
        if owner is None:
            if row['path']=='.gn' and row.get('symlink')=='build/core/gn/dotfile.gn':continue
            raise PublicInputError('SOURCE_OWNER_MISSING',row['path'])
        rel=row['path'][len(owner)+1:]
        source_row=dict(row,path=rel)
        source_row.pop('mode',None)
        if 'symlink' in row:
            p=checkout_map[owner]/safe(rel)
            if not p.is_symlink() or os.readlink(p)!=row['symlink']:
                raise PublicInputError('SOURCE_GIT_LINK_MISMATCH',row['path'])
        else:
            p=verify(checkout_map[owner],source_row,diagnostic_member=row['path'])
        declared_mode=int(row['mode'],8) if isinstance(row.get('mode'),str) else row.get('mode')
        if 'symlink' not in row and declared_mode is not None and bool(p.stat().st_mode & 0o111)!=bool(declared_mode & 0o111):
            raise PublicInputError('SOURCE_GIT_EXECUTABLE_MISMATCH',row['path'])
        target=source/safe(row['path']);target.parent.mkdir(parents=True,exist_ok=True)
        if 'symlink' not in row:
            with p.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
            target.chmod(declared_mode if declared_mode is not None else stat.S_IMODE(p.stat().st_mode))
    for row in inputs['source_files']:
        if 'symlink' in row:(source/safe(row['path'])).symlink_to(row['symlink'])
    for row in inputs.get('uninitialized_gitlinks',[]):
        p=source/safe(row['path']);p.mkdir(parents=True,exist_ok=False);p.chmod(row['directory_mode'])
    print('PUBLIC_NATIVE_MATERIALIZE_SOURCE_PASS',len(inputs['source_files']),flush=True)
    for i,row in enumerate(lock['tools']):
        print('PUBLIC_NATIVE_FETCH_TOOL_BEGIN',i+1,len(lock['tools']),flush=True)
        archive=downloads/('tool-'+str(i));download(row,archive)
        extract_tool(archive,original/safe(row['payload_root']),row)
    wheels=original/'official-python-wheels';wheels.mkdir()
    for row in lock['wheels']:download(row,wheels/safe(row['path']))
    verify_all(original,inputs)
    print('PUBLIC_NATIVE_ALL_SOURCE_TOOL_WHEEL_INVENTORY_PASS',flush=True)
    (dest/'PUBLIC_ACQUISITION.json').write_text(json.dumps({'schema':'remeizu.free-hosted-public-acquisition.v1','projects':proofs,
        'declared_lfs_materialization':lfs_materialization,
        'source_projects':len(inputs['projects']),'selected_part_count':lock['selected_part_count'],'all_source_tool_wheel_inventory_pass':True,
        'gn_inputs_sha256':sha(thin/'GN_INPUTS.json'),'private_android_inputs':False,'full375_phone':False,'runtime':False},indent=2)+'\n')
    return original

def verify_all(original,inputs):
    for row in inputs['source_files']:verify(original/'native-source-input',row)
    for tool in inputs['tools']:
        for row in tool['members']:
            if 'sha256' in row or 'symlink' in row:verify(original/tool['payload_root'],row)
    for row in inputs['python_wheels']:verify(original/'official-python-wheels',row)
