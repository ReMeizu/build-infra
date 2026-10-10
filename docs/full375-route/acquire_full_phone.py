"""Anonymous full expected source acquisition; every body checked before closure."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import time
from acquire import download, extract_tool, verify, public_url
from make_j2_successor import safe
import source_inventory_shards as shards

FLOOR=20*1024**3

def progress(phase,project=None,member=None,**facts):
    # Only fixed source-owned phases and inventory-declared canonical paths;
    # no command text, URLs, stderr, environment or credentials are emitted.
    if phase not in ('init','origin','fetch','checkout','lfs-materialize','source-materialize','source-symlink','tool-download','wheel-download','source-final-readback'):raise ValueError('fixed public acquisition phase required')
    row={'phase':phase}
    if project is not None:row['project']=str(safe(project))
    if member is not None:row['member']=str(safe(member))
    row.update(facts);print('FULL_PUBLIC_INPUT_DIAGNOSTIC '+json.dumps(row,sort_keys=True),flush=True)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(1024**2),b''):h.update(block)
    return h.hexdigest()

def disk_floor(path):
    if shutil.disk_usage(path).free<FLOOR:raise ValueError('actual single-filesystem source/cache/tool20GiB floor')

def source_disk_minimum(registry):
    projects=[]
    for parent in registry['public_projects']:
        projects.append(parent);projects.extend(parent.get('resolved_child_layers',[]))
    sizes=[row.get('object_bytes',row.get('bytes')) for project in projects for row in project.get('lfs_objects',[])]
    if type(registry['source_bytes']) is not int or registry['source_bytes']<=0 or any(type(size) is not int or size<=0 for size in sizes):raise ValueError('exact declared source/cache byte budget required')
    # The smudge cache and material body are different files. Git packs/tools
    # are additional unknown costs; their actual running floor remains strict.
    return registry['source_bytes']+sum(sizes)+FLOOR

def command(argv,env,log,seconds=900,project=None,phase=None):
    disk_floor(log.parent);start=time.monotonic();reason=None
    with log.open('xb') as output:
        proc=subprocess.Popen([str(x) for x in argv],env=env,stdout=output,stderr=output,start_new_session=True)
        try:
            while proc.poll() is None:
                if time.monotonic()-start>=seconds or shutil.disk_usage(log.parent).free<FLOOR:
                    reason='deadline' if time.monotonic()-start>=seconds else 'disk-floor';os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5);break
                time.sleep(.2)
        except BaseException:
            if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
            raise
    if proc.returncode or reason:
        if phase is not None:progress(phase,project,status='REFUSED',exit_code=proc.returncode,reason=reason or 'nonzero-exit')
        raise ValueError('owned public input command refused; private log retained')

def git_value(checkout,*argv):
    return subprocess.check_output(['git','-C',str(checkout),'-c','credential.helper=',*argv],stderr=subprocess.DEVNULL,timeout=60).decode().strip()

def exact_lfs(checkout,project,objects,env,logs):
    for index,obj in enumerate(objects):
        member=obj['path'];expected_sha=obj.get('object_sha256',obj.get('material_sha256'));size=obj.get('object_bytes',obj.get('bytes'));pointer_sha=obj.get('pointer_sha256',obj.get('committed_pointer_sha256'))
        progress('lfs-materialize',project['path'],member,status='BEGIN',declared_bytes=size)
        pointer=subprocess.check_output(['git','-C',str(checkout),'show',project['head']+':'+member],stderr=subprocess.DEVNULL,timeout=60)
        import re
        match=re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n',pointer)
        if not match or match[1].decode()!=expected_sha or int(match[2])!=size or hashlib.sha256(pointer).hexdigest()!=pointer_sha:raise ValueError('exact original committed LFS pointer/OID/size required')
        path=checkout/safe(member)
        if path.is_file() and not path.is_symlink() and path.stat().st_size==size and sha(path)==expected_sha:continue
        pending=logs/('LFS-'+str(index)+'.partial');log=logs/('LFS-'+str(index)+'.private.log');endpoint=project['url'].removesuffix('.git')+'.git/info/lfs';child_env=dict(env);child_env.pop('GIT_LFS_SKIP_SMUDGE',None);start=time.monotonic();reason=None
        with pending.open('xb') as output,log.open('xb') as stderr:
            proc=subprocess.Popen(['git','-C',str(checkout),'-c','credential.helper=','-c','lfs.url='+endpoint,'lfs','smudge','--',member],env=child_env,stdin=subprocess.PIPE,stdout=output,stderr=stderr,start_new_session=True);proc.stdin.write(pointer);proc.stdin.close()
            try:
                while proc.poll() is None:
                    if time.monotonic()-start>=600 or pending.stat().st_size>size or shutil.disk_usage(logs).free<FLOOR:
                        reason='deadline-size-or-disk';os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5);break
                    time.sleep(.2)
            except BaseException:
                if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
                raise
        if proc.returncode or reason or pending.stat().st_size!=size or sha(pending)!=expected_sha:
            progress('lfs-materialize',project['path'],member,status='REFUSED',exit_code=proc.returncode,reason=reason or 'body-size-sha',actual_bytes=pending.stat().st_size)
            raise ValueError('actual public LFS body byte readback refused')
        # Preserve the original checkout pointer; no source evidence deletion.
        backup=logs/('LFS-'+str(index)+'.original');shutil.copyfile(path,backup);pending.chmod(stat.S_IMODE(path.stat().st_mode));pending.replace(path)

def link_verified_source(checkout,source,row,alias_modes):
    relative=row['path'];local=dict(row,path=relative);mode=int(row['mode'],8);local.pop('mode',None);path=verify(checkout,local)
    if bool(path.stat().st_mode&0o111)!=bool(mode&0o111):raise ValueError('original Git executable bit differs')
    target=source/safe(row['full_path']);target.parent.mkdir(parents=True,exist_ok=True)
    key=(path.stat().st_dev,path.stat().st_ino)
    if key in alias_modes and alias_modes[key]!=mode:raise ValueError('hardlink source inode mode conflict')
    alias_modes[key]=mode;path.chmod(mode);os.link(path,target)
    if target.stat().st_dev!=path.stat().st_dev or target.stat().st_ino!=path.stat().st_ino:raise ValueError('source sanitized-lower hardlink not genuine')
    verify(source,{k:v for k,v in dict(row,path=row['full_path']).items() if k!='full_path'})

def acquire_full(lock,thin,dest):
    """Return original controller after actual source/tool/wheel byte verification."""
    thin,dest=Path(thin),Path(dest)
    if dest.exists() or dest.is_symlink():raise ValueError('fresh owned full public input directory required')
    registry_file=thin/safe(lock['registry_path'])
    if sha(registry_file)!=lock['registry_sha256']:raise ValueError('full expected registry hash differs')
    registry=json.loads(registry_file.read_text())
    if registry['schema']!='remeizu.canonical-full-phone-EXPECTED-source-registry.v1' or registry['actual_selected_count']!=366 or registry['actual_canonical_component_count']!=365 or registry['canonical_full_phone_source_bindings_verified'] is not True or registry['canonical_full_phone_source_closed'] is not False:raise ValueError('exact source-only expected canonical profile required')
    if shutil.disk_usage(dest.parent).free<source_disk_minimum(registry):raise ValueError('actual source plus separate LFS cache plus20GiB floor required before acquisition')
    index_file=registry_file.parent/'source-inventories/INDEX.json'
    if sha(index_file)!=registry['inventory_index_sha256']:raise ValueError('full inventory index hash differs')
    rows=shards.read_shards(index_file.parent,json.loads(index_file.read_text()));disk_floor(dest.parent);dest.mkdir();original=dest/'original';shutil.copytree(thin/'controller',original)
    base=json.loads((original/'GN_INPUTS.json').read_text())
    if sha(original/'GN_INPUTS.json')!=registry['baseline_gn_inputs_sha256']:raise ValueError('actual reviewed source/tool/patch baseline differs')
    source=original/'native-source-input';source.mkdir();checkouts=dest/'checkouts';checkouts.mkdir();logs=dest/'private-input-logs';logs.mkdir();downloads=dest/'downloads';downloads.mkdir()
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_LFS_SKIP_SMUDGE='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_CONFIG_COUNT='0')
    for key in list(env):
        if 'TOKEN' in key.upper() or key.startswith('GIT_CONFIG_KEY_') or key.startswith('GIT_CONFIG_VALUE_'):env.pop(key)
    parents=registry['public_projects'];projects=[]
    for parent in parents:
        projects.append(parent)
        for child in parent.get('resolved_child_layers',[]):projects.append(dict(child,url=child['remote']))
    checkout_map={};proofs=[]
    for position,project in enumerate(projects):
        disk_floor(dest);public_url(project['url']);target=checkouts/str(position);target.mkdir();project_logs=logs/str(position);project_logs.mkdir()
        for phase,argv in [('init',['git','init','-q',target]),('origin',['git','-C',target,'remote','add','origin',project['url']]),('fetch',['git','-C',target,'-c','credential.helper=','fetch','--depth=1','--no-tags','origin',project['head']]),('checkout',['git','-C',target,'checkout','--detach','--quiet','FETCH_HEAD'])]:
            progress(phase,project['path'],status='BEGIN')
            command(argv,env,project_logs/(phase+'.private.log'),project=project['path'],phase=phase)
        if git_value(target,'rev-parse','HEAD')!=project['head'] or git_value(target,'rev-parse','HEAD^{tree}')!=project['git_tree']:raise ValueError('actual anonymously fetched Git head/tree differs')
        exact_lfs(target,project,project.get('lfs_objects',[]),env,project_logs)
        checkout_map[project['path']]=target;proofs.append({'path':project['path'],'head':project['head'],'git_tree':project['git_tree']});print('FULL_PUBLIC_PROJECT_PIN_AND_LFS_PASS',position+1,len(projects),flush=True)
    owners=sorted(checkout_map,key=len,reverse=True);alias_modes={}
    for row in rows:
        if 'symlink' in row:continue
        owner=next((p for p in owners if row['path'].startswith(p+'/')),None)
        if owner is None:raise ValueError('full exact source owner missing')
        rel=row['path'][len(owner)+1:]
        try:link_verified_source(checkout_map[owner],source,dict(row,path=rel,full_path=row['path']),alias_modes)
        except Exception:
            progress('source-materialize',owner,row['path'],status='REFUSED',reason='row-byte-mode-link-guard')
            raise
    for row in rows:
        if 'symlink' not in row:continue
        owner=next((p for p in owners if row['path'].startswith(p+'/')),None)
        if owner is not None:
            origin=checkout_map[owner]/safe(row['path'][len(owner)+1:])
            if not origin.is_symlink() or os.readlink(origin)!=row['symlink']:raise ValueError('full original source symlink differs')
        elif row['path']!='.gn' or row['symlink']!='build/core/gn/dotfile.gn':raise ValueError('undeclared global source symlink')
        target=source/safe(row['path']);target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(row['symlink']);verify(source,row)
    for i,tool in enumerate(registry['official_tools']):
        progress('tool-download',status='BEGIN',index=i);disk_floor(dest);archive=downloads/('tool-'+str(i));download(tool,archive);extract_tool(archive,original/safe(tool['payload_root']),tool)
    wheels=original/'official-python-wheels';wheels.mkdir()
    for wheel in registry['official_wheels']:
        progress('wheel-download',member=wheel['path'],status='BEGIN');disk_floor(dest);download(wheel,wheels/safe(wheel['path']))
    base.update(source_files=rows,source_bytes=registry['source_bytes'],projects=registry['projects'],full_phone_profile_kind='canonical-full-gui-a2',canonical_full_phone_source_bindings_verified=True,actual_selected_parts=registry['actual_selected_parts'],original375_selected_parts=registry['original375_selected_parts'],original_dynamic_parts=registry['original_dynamic_parts'],full_phone_source_closed=False,uninitialized_gitlinks=registry['unresolved_original_gitlinks'])
    coverage=registry_file.parent/'CANONICAL_375_REQUEST_COVERAGE.a2.json';selector=registry_file.parent/'CANONICAL_FULL_PHONE_SELECTOR.a1.json'
    if sha(coverage)!=registry['canonical_375_request_coverage_sha256'] or sha(selector)!=registry['canonical_selector_sha256']:raise ValueError('exact canonical history/GUI selector differs')
    shutil.copyfile(coverage,original/'canonical_full_phone_coverage.json');shutil.copyfile(selector,original/'inputs/canonical-full-phone.json');base['overlay_files'].append({'path':'inputs/canonical-full-phone.json','target':'vendor/oniro/m5c/config.json','sha256':sha(selector)})
    shutil.copyfile(thin/'runtime_core_nonproduction_scope.json',original/'runtime_core_nonproduction_scope.json')
    from nonproduction_scope import validate
    validate(base,original)
    for pointer in base['uninitialized_gitlinks']:
        path=source/safe(pointer['path'])
        path.mkdir(parents=True,exist_ok=False)
        path.chmod(pointer.get('directory_mode',493))
    for row in rows:verify(source,row)
    for tool in base['tools']:
        for row in tool['members']:
            if 'sha256' in row or 'symlink' in row:verify(original/tool['payload_root'],row)
    for row in base['python_wheels']:verify(wheels,row)
    for project in projects:
        target=checkout_map[project['path']]
        if git_value(target,'rev-parse','HEAD')!=project['head'] or git_value(target,'rev-parse','HEAD^{tree}')!=project['git_tree']:raise ValueError('full source original Git identity drift')
    # Every actual production row was verified; the one source-proven unused
    # pointer stays honestly unmaterialized and is not all506 recursive closure.
    base['full_phone_source_closed']=True
    base['nonproduction_gitlink_scope_sha256']=sha(original/'runtime_core_nonproduction_scope.json')
    (original/'GN_INPUTS.json').write_text(json.dumps(base,sort_keys=True,indent=2)+'\n')
    (dest/'FULL_PUBLIC_ACQUISITION.json').write_text(json.dumps({'schema':'remeizu.full-phone-actual-public-input-acquisition.v1','all_rows_tools_wheels_verified':True,'full_phone_source_closed':base['full_phone_source_closed'],'uninitialized_gitlinks':base['uninitialized_gitlinks'],'projects':proofs,'source_files':len(rows),'source_bytes':registry['source_bytes'],'lower_inventory_sha256':registry['lower_inventory_sha256'],'actual_available_disk_bytes_once':shutil.disk_usage(dest).free,'raw_private_android_inputs':False,'GN_or_target_compilation':False,'images_built':False},indent=2)+'\n');disk_floor(dest)
    if not base['full_phone_source_closed']:raise ValueError('full source rows verified but production child-source scope remains unresolved')
    return original
