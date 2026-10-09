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

def verify(root,row):
    path=root/safe(row['path'])
    if 'symlink' in row:
        if not path.is_symlink() or os.readlink(path)!=row['symlink']:raise ValueError('public input link differs')
        path.resolve().relative_to(root.resolve())
    else:
        if not path.is_file() or path.is_symlink() or sha(path)!=row['sha256']:raise ValueError('public input byte mismatch: '+row['path'])
        if 'bytes' in row and path.stat().st_size!=row['bytes']:raise ValueError('public input size mismatch')
        if 'mode' in row:
            mode=int(row['mode'],8) if isinstance(row['mode'],str) else row['mode']
            if stat.S_IMODE(path.stat().st_mode)!=mode:raise ValueError('public input mode mismatch')
    return path

def validate_lock(lock,inputs):
    if lock.get('schema')!='remeizu.free-hosted-native-public-inputs.v1' or lock.get('public_sources_only') is not True or lock.get('private_android_inputs') is not False:
        raise ValueError('reviewed source-only public acquisition lock required')
    if lock.get('source_projects')!=88 or lock.get('selected_part_count')!=72 or len(inputs['projects'])!=88:
        raise ValueError('genuine 88/72 intermediate required; full375 not admitted')
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

def acquire(lock,thin,dest):
    if dest.exists():raise ValueError('fresh public source acquisition root required')
    inputs=json.loads((thin/'GN_INPUTS.json').read_text())
    if sha(thin/'GN_INPUTS.json')!=lock['gn_inputs_sha256']:raise ValueError('public GN inventory hash differs')
    validate_lock(lock,inputs)
    floor=lock['expanded_bytes']+sum(x['archive_bytes'] for x in lock['tools'])+2*inputs['source_bytes']+3*1024**3
    if shutil.disk_usage(dest.parent).free<floor:raise ValueError('actual disk cannot retain verified source/tools/downloads/Docker headroom')
    dest.mkdir(); original=dest/'original';shutil.copytree(thin,original)
    if any(p.name=='.git' or p.suffix in ('.bundle','.private') or '.private.' in p.name or 'ORIGINAL_FREEZE' in p.name for p in original.rglob('*')):
        raise ValueError('opaque/private carrier member in thin source export')
    checkouts=dest/'checkouts';checkouts.mkdir();downloads=dest/'downloads';downloads.mkdir()
    checkout_map={};proofs=[]
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
        head=run(['git','-C',target,'rev-parse','HEAD']).stdout.decode().strip()
        tree=run(['git','-C',target,'rev-parse','HEAD^{tree}']).stdout.decode().strip()
        if head!=p['head'] or tree!=p['git_tree']:raise ValueError('anonymous fetched original Git identity differs')
        checkout_map[p['path']]=target;proofs.append({'path':p['path'],'head':head,'git_tree':tree})
        print('PUBLIC_NATIVE_FETCH_PROJECT_PIN_PASS',i+1,len(lock['projects']),flush=True)
    source=original/'native-source-input';source.mkdir()
    owners=sorted(checkout_map,key=len,reverse=True)
    for row in inputs['source_files']:
        owner=next((x for x in owners if row['path'].startswith(x+'/')),None)
        if owner is None:
            if row['path']=='.gn' and row.get('symlink')=='build/core/gn/dotfile.gn':continue
            raise ValueError('source member has no exact pinned project owner')
        rel=row['path'][len(owner)+1:]
        source_row=dict(row,path=rel)
        source_row.pop('mode',None)
        if 'symlink' in row:
            p=checkout_map[owner]/safe(rel)
            if not p.is_symlink() or os.readlink(p)!=row['symlink']:
                raise ValueError('Git source link differs from admitted original member')
        else:
            p=verify(checkout_map[owner],source_row)
        declared_mode=int(row['mode'],8) if isinstance(row.get('mode'),str) else row.get('mode')
        if 'symlink' not in row and declared_mode is not None and bool(p.stat().st_mode & 0o111)!=bool(declared_mode & 0o111):
            raise ValueError('Git executable bit differs from admitted source member')
        target=source/safe(row['path']);target.parent.mkdir(parents=True,exist_ok=True)
        if 'symlink' not in row:
            with p.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
            target.chmod(declared_mode if declared_mode is not None else stat.S_IMODE(p.stat().st_mode))
    for row in inputs['source_files']:
        if 'symlink' in row:(source/safe(row['path'])).symlink_to(row['symlink'])
    for row in inputs.get('uninitialized_gitlinks',[]):
        p=source/safe(row['path']);p.mkdir(parents=True,exist_ok=False);p.chmod(row['directory_mode'])
    for i,row in enumerate(lock['tools']):
        print('PUBLIC_NATIVE_FETCH_TOOL_BEGIN',i+1,len(lock['tools']),flush=True)
        archive=downloads/('tool-'+str(i));download(row,archive)
        extract_tool(archive,original/safe(row['payload_root']),row)
    wheels=original/'official-python-wheels';wheels.mkdir()
    for row in lock['wheels']:download(row,wheels/safe(row['path']))
    verify_all(original,inputs)
    print('PUBLIC_NATIVE_ALL_SOURCE_TOOL_WHEEL_INVENTORY_PASS',flush=True)
    (dest/'PUBLIC_ACQUISITION.json').write_text(json.dumps({'schema':'remeizu.free-hosted-public-acquisition.v1','projects':proofs,
        'source_projects':88,'selected_part_count':72,'all_source_tool_wheel_inventory_pass':True,
        'gn_inputs_sha256':sha(thin/'GN_INPUTS.json'),'private_android_inputs':False,'full375_phone':False,'runtime':False},indent=2)+'\n')
    return original

def verify_all(original,inputs):
    for row in inputs['source_files']:verify(original/'native-source-input',row)
    for tool in inputs['tools']:
        for row in tool['members']:
            if 'sha256' in row or 'symlink' in row:verify(original/tool['payload_root'],row)
    for row in inputs['python_wheels']:verify(original/'official-python-wheels',row)
