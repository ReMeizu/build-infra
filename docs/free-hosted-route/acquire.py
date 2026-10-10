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
    if lock.get('source_projects')!=102 or lock.get('selected_part_count')!=86 or len(inputs['projects'])!=102 or lock.get('source_bytes')!=inputs.get('source_bytes'):
        raise ValueError('genuine reviewed 102/86 intermediate required; full375 not admitted')
    if lock.get('gn_inputs_sha256')!='fd12937cafbb5c2e0d785a35529e96e0a7c572700243c05cdc38ddb1a2b87885':
        raise ValueError('reviewed measured cohort GN identity differs')
    proof_row=lock.get('cohort_proof',{})
    if proof_row!={'path':'inputs/IDL_PROVIDER_COHORT_PROOF.a1.json','sha256':'98ec359c29a5c64bc60776e672ecf9269c59c96d4dd099cf309ce41d7103f4b0'}:
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
    parent=proof.get('immediate_parent',{})
    if (parent.get('source_lock_sha256')!='cd0fd17d93ddf0c7f4cd2da211fafb746cca9aaf8e16e8a9f4867e9700cce4c0' or
            parent.get('gn_inputs_sha256')!='bc5b4da2894494c066978098d9e811cb208fca87588c1e73c0dea4f45e4d4e06' or
            parent.get('cohort_proof_sha256')!='8f92eec4f3e22a3afa1a91d3c08a555dc04b9bf7507f69f063eec09e03c5af9e' or
            parent.get('source_projects')!=101 or parent.get('selected_part_count')!=85):
        raise ValueError('source-admitted A6 immediate parent binding differs')
    parent_projects=[r for r in inputs['projects'] if r['path']!='foundation/ability/idl_tool']
    if len(parent_projects)!=101 or canonical(parent_projects)!='62e1c19c6a23411dad1dc38ccdaa22257c1b392267d2bcdd7702881c6dca2a0b':
        raise ValueError('source-admitted parent101 project rows changed')
    parent_rows={r['path']:r for r in inputs['source_files'] if not r['path'].startswith('foundation/ability/idl_tool/')}
    if len(parent_rows)!=174299 or canonical(parent_rows)!='19a2f1db71a4aea28a2b04cc1da9d7fb8ecb7d4f8bf01fe37eca0cf7da27efe5':
        raise ValueError('source-admitted parent101 source rows changed')
    parent_parts=parent.get('selected_parts',{})
    if (len(parent_parts)!=85 or canonical(parent_parts)!='c5e92ea246fd97fe8a15642b2ca9ceeee9e9ca55470157e5949e086952bb6c84' or
            any(actual.get(k)!=v for k,v in parent_parts.items()) or set(actual)-set(parent_parts)!={'ability:idl_tool'}):
        raise ValueError('source-admitted parent85 parts/features changed')
    parent_selector=parent.get('final_selector',{})
    if parent_selector!={'path':'inputs/public-relational-production-product.json','sha256':'c2a2f2061234de77b6103b473ec6ed2b2e261fceaa38b3d873cc6875e36ff41c'} or sha(thin/safe(parent_selector['path']))!=parent_selector['sha256']:
        raise ValueError('source-admitted A6 selector changed')
    for key in ('baseline_selector','final_selector'):
        r=proof[key]
        if sha(thin/safe(r['path']))!=r['sha256']:raise ValueError('reviewed production selector bytes differ')
    source_map={r['path']:r for r in inputs['source_files']}
    for r in proof['inherit_inputs']:
        if source_map.get(r['path'],{}).get('sha256')!=r['sha256']:raise ValueError('reviewed inherited selection source differs')
    final=[r for r in inputs['overlay_files'] if r['target']=='vendor/oniro/m5c/config.json'][-1]
    if final['path']!=proof['final_selector']['path'] or final['sha256']!=proof['final_selector']['sha256']:
        raise ValueError('reviewed actual final selector overlay differs')
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
