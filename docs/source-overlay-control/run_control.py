#!/usr/bin/env python3
"""Bounded standard public source-overlay control through unchanged Forge."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import ram_overlay_protocol as model
import resources

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FORGE=ROOT/'vendor/forge/forge_ephemeral_build.py'
DOCKERFILE=ROOT/'docs/free-hosted-route/controller/official-build-env/Dockerfile'
FORGE_SHA='9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8'
DOCKER_SHA='bdaa70b28298b269a8009335a9e90987fde0dd1ff08dad5369d133aeb0aadf3b'

def closed_containers(forge,actual,recipe_hash):
    """Independent source-control closure; never rewrite producer state."""
    records=[]
    for path in sorted((actual/forge.CONTAINER_METADATA_DIR).glob('*.json')):
        if path.is_symlink() or path.stat().st_size>16384:raise ValueError('bounded owned source-control receipt required')
        original=path.read_bytes();state=json.loads(original);inv=state.get('invocation','')
        expected='forge-eph-'+recipe_hash[:12]+'-'+inv[:12]
        if not re.fullmatch('[a-f0-9]{32}',inv) or path.name!=inv+'.json' or state.get('recipe_hash')!=recipe_hash or state.get('container_name')!=expected:raise ValueError('exact source-control invocation ownership required')
        cleanup=forge._cleanup_owned_container(state) if state.get('cleanup_needed',True) else {'cleanup_needed':False}
        if cleanup.get('cleanup_needed') is not False or state.get('client_reaped') is not True:raise ValueError('owned client or daemon closure unresolved')
        cid=state.get('container_id')
        if cid:
            if not re.fullmatch('[a-f0-9]{64}',cid):raise ValueError('exact full owned container ID required')
            response=subprocess.run(['docker','container','inspect',cid],capture_output=True,text=True,timeout=10)
            if response.returncode==0 or not any(x in response.stderr for x in ('No such object','No such container')):raise ValueError('exact owned container absence unresolved')
        elif state.get('create_issued') is not False:raise ValueError('possible late owned Docker creation unresolved')
        if path.read_bytes()!=original:raise ValueError('original source-control producer state changed')
        records.append({'invocation':inv,'known_container_absent':bool(cid),'owned_client_reaped':True,'owned_closed':True})
    return {'schema':'remeizu.source-control-owned-closure.v1','recipe_hash':recipe_hash,'all_owned_container_closure_pass':True,'owned_states':records,'producer_history_rewritten':False}

def freeze_git(control):
    names=['control_worker.py','ram_overlay_protocol.py','PLAN.json']
    for argv in (['git','init','--quiet',control],['git','-C',control,'add','--']+names,['git','-C',control,'-c','user.name=ReMeizu source control','-c','user.email=source-control@remeizu.invalid','commit','-qm','Freeze literal source overlay control']):
        subprocess.run([str(x) for x in argv],check=True,capture_output=True,timeout=30)
    if set(subprocess.check_output(['git','-C',str(control),'ls-files'],timeout=10).decode().splitlines())!=set(names):raise ValueError('exact three-file controller Git source required')
    return {'head':subprocess.check_output(['git','-C',str(control),'rev-parse','HEAD'],timeout=10).decode().strip(),'tree':subprocess.check_output(['git','-C',str(control),'rev-parse','HEAD^{tree}'],timeout=10).decode().strip()}

def failure_code(error):
    if isinstance(error,subprocess.TimeoutExpired):return 'OWNED_SOURCE_COMMAND_DEADLINE'
    if isinstance(error,KeyboardInterrupt):return 'OWNED_SOURCE_COMMAND_INTERRUPTED'
    if isinstance(error,subprocess.CalledProcessError):return 'OWNED_SOURCE_GIT_OR_MOUNT_NONZERO'
    return {'actual Forge source fixture failed; no native success inferred':'OFFICIAL_FORGE_SOURCE_CONTROL_NONZERO','actual lower readonly bind mount required':'LOWER_READONLY_BIND_REQUIRED','actual original source references changed':'ORIGINAL_SOURCE_REFERENCE_DRIFT','actual immutable image changed before Forge create':'IMAGE_BEFORE_CREATE_DRIFT','actual recursive non-root overlay/RAM witness required':'RECURSIVE_OVERLAY_OR_UID_WITNESS_REFUSED','owned source control command nonzero':'OWNED_SOURCE_SETUP_COMMAND_NONZERO'}.get(str(error),'UNCLASSIFIED_SOURCE_CONTROL_REFUSAL')

def bounded_log_reasons(paths):
    needles={b'not a git repository':'SOURCE_CONTROLLER_GIT_REQUIRED',b'Temporary failure resolving':'SDK_DNS_REFUSAL',b'Unable to locate package':'SDK_APT_PACKAGE_NOT_FOUND',b'NO_PUBKEY':'SDK_APT_SIGNATURE_REFUSAL',b'Could not handshake':'SDK_TLS_HANDSHAKE_REFUSAL',b'404 Not Found':'SDK_PUBLIC_OBJECT_NOT_FOUND',b'ValueError: actual lower readonly bind mount required':'LOWER_READONLY_BIND_REQUIRED',b'ValueError: actual recursively bound overlay/RAM directories required':'DOCKER_RECURSIVE_BIND_REQUIRED',b'ValueError: no unlisted executable or opaque source lower members admitted':'LOWER_UNLISTED_MEMBER_REFUSED',b'Permission denied':'OWNED_SOURCE_PATH_PERMISSION_REFUSED'}
    codes=set()
    for path in paths:
        if not path.is_file() or path.is_symlink():continue
        with path.open('rb') as source:
            source.seek(max(0,path.stat().st_size-131072));body=source.read(131072)
        codes.update(code for needle,code in needles.items() if needle in body)
    return sorted(codes)

def checked_job(env):
    if env.get('GITHUB_ACTIONS')!='true' or env.get('GITHUB_REPOSITORY')!='ReMeizu/build-infra' or env.get('GITHUB_REF')!='refs/heads/codex/source-overlay-control-20261010' or env.get('GITHUB_EVENT_NAME') not in ('push','workflow_dispatch') or env.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('exact first-attempt public control branch required')
    event=json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())
    if event['repository'].get('private') is not False or os.geteuid()==0 or env.get('RUNNER_ARCH')!='X64':raise ValueError('public non-root x64 standard runner required')
    if not re.fullmatch('[0-9]+',env.get('GITHUB_RUN_ID','')):raise ValueError('actual control run identity required')

def final_resources(result,paths):
    """Require the final counters without discarding actual filesystem evidence."""
    try:result['resources_after_control']=resources.snapshot(paths)
    except Exception as error:
        result.update(resources_after_control_refused=type(error).__name__,status='SOURCE_CONTROL_REFUSED',fixed_phase='resource-after-control',fixed_error_code='RUNNER_RESOURCE_MEASUREMENT_REFUSED')

def main():
    checked_job(os.environ)
    if model.sha(FORGE)!=FORGE_SHA or model.sha(DOCKERFILE)!=DOCKER_SHA:raise ValueError('byte-exact official source references required')
    job=Path(os.environ['RUNNER_TEMP'])/('source-overlay-control-'+os.environ['GITHUB_RUN_ID'])
    if job.exists():raise ValueError('fresh owned source fixture required')
    job.mkdir(mode=0o700);ram=job/'ram';ram.mkdir();disk=job/'literal-lower';disk.mkdir()
    uid,gid=os.getuid(),os.getgid();mounts=[];forge=None;actual=None;phase='RAM-mount';rows=None;inventory=None;git_identity=None;control=None
    result={'schema':'remeizu.standard-public-source-overlay-control.v1','run_id':os.environ['GITHUB_RUN_ID'],'target_compilation':False,'private_android_inputs':False,'full375_images':False,'full375_fit_proven':False,'Docker_recursive_visibility_proven':False}
    result['resources_before_environment']=resources.snapshot({'runner_temp':job,'workspace':ROOT})
    def command(argv,timeout=30):
        with (ram/(phase+'.stdout')).open('wb') as out,(ram/(phase+'.stderr')).open('wb') as err:
            p=subprocess.Popen([str(x) for x in argv],stdout=out,stderr=err,start_new_session=True)
            try:code=p.wait(timeout=timeout)
            except (subprocess.TimeoutExpired,KeyboardInterrupt):
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait(timeout=5);raise
        if code:
            result['actual_setup_exit_code']=code
            raise ValueError('owned source control command nonzero')
    try:
        # Own host-visible mounts: Docker daemon must see them before create.
        subprocess.run(['sudo','-n','mount','-t','tmpfs','-o','size=268435456,mode=0700,uid='+str(uid)+',gid='+str(gid),'tmpfs',str(ram)],check=True,capture_output=True,timeout=30);mounts.append(ram)
        if model.filesystem(ram)!='tmpfs':raise ValueError('actual source fixture RAM required')
        phase='official-Docker-build';tag='androidforge/build-source-overlay-'+result['run_id']+':android-9'
        command(['docker','build','-f',DOCKERFILE,'-t',tag,DOCKERFILE.parent],timeout=600)
        phase='official-image-inspect';command(['docker','image','inspect',tag,'--format','{{.Id}}'])
        image=(ram/(phase+'.stdout')).read_text().strip()
        if not re.fullmatch('sha256:[a-f0-9]{64}',image):raise ValueError('actual immutable source control image required')
        result['actual_image_id']=image
        result['resources_after_environment']=resources.snapshot({'runner_temp':job,'workspace':ROOT,'ram':ram})
        (disk/'source.txt').write_text('immutable literal source fixture\n');(disk/'source.txt').chmod(0o644);(disk/'.gn').symlink_to('source.txt')
        rows=[{'path':'source.txt','bytes':(disk/'source.txt').stat().st_size,'mode':'0o644','sha256':model.sha(disk/'source.txt')},{'path':'.gn','symlink':'source.txt'}]
        inventory=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for name in ('lower','upper','work','merged'):(ram/name).mkdir()
        phase='lower-bind';command(['sudo','-n','mount','--bind',disk,ram/'lower']);mounts.append(ram/'lower')
        phase='lower-readonly';command(['sudo','-n','mount','-o','remount,bind,ro',ram/'lower'])
        phase='source-overlay-mount';command(['sudo','-n','mount','-t','overlay','overlay','-o','lowerdir='+str(ram/'lower')+',upperdir='+str(ram/'upper')+',workdir='+str(ram/'work'),ram/'merged']);mounts.append(ram/'merged')
        lower_before=model.verify_lower(ram/'lower',rows,inventory)
        control=ram/'controller';control.mkdir()
        for name in ('control_worker.py','ram_overlay_protocol.py'):shutil.copyfile(HERE/name,control/name)
        recipe={'image_tag':tag,'build_env_key':'android-9','source_mount_path':str(control),'output_dir_in_container':'/workspace/out','command':['python3','-B','/workspace/src/control_worker.py'],'extra_mounts':[[str(ram),'/workspace/ram','rw']],'env':{'PYTHONDONTWRITEBYTECODE':'1'},'timeout_seconds':120,'idempotency_key':'source-overlay-control-'+result['run_id']}
        spec=importlib.util.spec_from_file_location('source_control_original_forge',FORGE);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
        frozen=forge.recipe_from_dict(recipe);rh=frozen.recipe_hash();actual=ram/'forge'/rh
        plan={'uid':uid,'gid':gid,'source_rows':rows,'source_inventory_sha256':inventory,'artifact_root_relative':'forge/'+rh}
        (control/'PLAN.json').write_text(json.dumps(plan,sort_keys=True,indent=2)+'\n')
        source_hashes={name:model.sha(control/name) for name in ('control_worker.py','ram_overlay_protocol.py','PLAN.json')}
        phase='controller-Git-freeze';git_identity=freeze_git(control)
        provenance=forge.current_source_provenance(control)
        result['actual_control_Git']=git_identity
        recipe_path=ram/'recipe.json';recipe_path.write_text(json.dumps(recipe,indent=2)+'\n')
        phase='prelaunch-image-inspect';command(['docker','image','inspect',tag,'--format','{{.Id}}'])
        if (ram/(phase+'.stdout')).read_text().strip()!=image:raise ValueError('actual immutable image changed before Forge create')
        phase='official-Forge-source-control'
        env=dict(os.environ,FORGE_EPHEMERAL_BASE=str(ram/'forge'))
        with (ram/'FORGE.stdout').open('xb') as out,(ram/'FORGE.stderr').open('xb') as err:
            p=subprocess.Popen([sys.executable,'-B',str(FORGE),'--recipe',str(recipe_path),'--no-resume'],env=env,stdout=out,stderr=err,start_new_session=True)
            result['official_Forge_submitted']=True
            try:code=p.wait(timeout=180)
            except (subprocess.TimeoutExpired,KeyboardInterrupt):
                p.send_signal(signal.SIGINT)
                try:p.wait(timeout=35)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
                raise
        result['actual_Forge_returncode']=code
        if code or (actual/'FAILURE').exists():raise ValueError('actual Forge source fixture failed; no native success inferred')
        marker=json.loads((actual/'SUCCESS').read_text());artifacts=json.loads((actual/'artifacts.json').read_text())
        if marker['recipe_hash']!=rh or marker['source_provenance']!=provenance or marker['artifacts_sha256']!=model.sha(actual/'artifacts.json') or marker['artifacts_count']!=2 or set(artifacts)!={'retained/probe.txt','SOURCE_WORKER_PROOF.json'}:raise ValueError('actual Forge two-artifact source binding required')
        for name,digest in artifacts.items():
            path=actual/name
            if path.is_symlink() or model.sha(path)!=digest:raise ValueError('actual source-control artifact full readback differs')
        worker=json.loads((actual/'SOURCE_WORKER_PROOF.json').read_text())
        if worker['actual_uid']!=uid or worker['actual_gid']!=gid or worker['actual_overlay_type']!='overlay' or worker['actual_upper_type']!='tmpfs' or worker['actual_work_type']!='tmpfs' or worker['target_compilation'] is not False:raise ValueError('actual recursive non-root overlay/RAM witness required')
        lower_after=model.verify_lower(ram/'lower',rows,inventory)
        if source_hashes!={name:model.sha(control/name) for name in source_hashes} or forge.current_source_provenance(control)!=provenance or model.sha(FORGE)!=FORGE_SHA or model.sha(DOCKERFILE)!=DOCKER_SHA:raise ValueError('actual original source references changed')
        result.update(status='ACTUAL_SOURCE_FILESYSTEM_CONTROL_PASS_NOT_FULL375',Docker_recursive_visibility_proven=True,lower_before=lower_before,lower_after=lower_after,worker=worker,recipe_hash=rh,official_Forge_sha256=model.sha(FORGE),official_Dockerfile_sha256=model.sha(DOCKERFILE),actual_artifact_manifest_sha256=model.sha(actual/'artifacts.json'),actual_artifacts=artifacts)
    except (Exception,KeyboardInterrupt) as error:
        result.update(status='SOURCE_CONTROL_REFUSED',fixed_phase=phase,error_type=type(error).__name__,fixed_error_code=failure_code(error))
        if isinstance(error,subprocess.CalledProcessError):result['actual_setup_exit_code']=error.returncode
    finally:
        final_resources(result,{'runner_temp':job,'workspace':ROOT,'ram':ram})
        # Preserve source-owned diagnosis before volatile RAM disappears.
        result['owned_RAM_log_witnesses']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':model.sha(p)} for p in sorted(ram.glob('*')) if p.is_file() and p.suffix in ('.stdout','.stderr')]
        logpaths=[p for p in ram.glob('*') if p.suffix in ('.stdout','.stderr')]
        if actual is not None:logpaths.append(actual/'run.log')
        result['fixed_bounded_log_reason_codes']=bounded_log_reasons(logpaths)
        closure_pass=True
        if forge is not None and actual is not None:
            try:
                closure=closed_containers(forge,actual,rh);closure_pass=closure['all_owned_container_closure_pass'];result['official_owned_closure']=closure
            except Exception as error:
                closure_pass=False;result.update(official_owned_cleanup_failed=True,closure_error_type=type(error).__name__,closure_error_code='OWNED_DOCKER_CLOSURE_UNRESOLVED',status='SOURCE_CONTROL_REFUSED',fixed_phase='owned-Docker-closure',fixed_error_code='OWNED_DOCKER_CLOSURE_UNRESOLVED')
        if rows is not None and inventory is not None and (ram/'lower') in mounts:
            try:result['independent_lower_after']=model.verify_lower(ram/'lower',rows,inventory)
            except Exception:result.update(independent_lower_after_failed=True,status='SOURCE_CONTROL_REFUSED',fixed_phase='independent-lower-after',fixed_error_code='LOWER_AFTER_SOURCE_IDENTITY_REFUSED')
        if closure_pass:
            for mount in reversed(mounts):
                try:subprocess.run(['sudo','-n','umount',str(mount)],check=True,capture_output=True,timeout=30)
                except Exception:result.update(owned_mount_cleanup_failed=True,status='SOURCE_CONTROL_REFUSED',fixed_phase='owned-mount-cleanup',fixed_error_code='OWNED_MOUNT_UNMOUNT_REFUSED')
        else:result['owned_mounts_preserved_until_VM_teardown']=True
        print(json.dumps(result,sort_keys=True),flush=True)
    return 0 if result.get('status')=='ACTUAL_SOURCE_FILESYSTEM_CONTROL_PASS_NOT_FULL375' and not result.get('owned_mount_cleanup_failed') and not result.get('official_owned_cleanup_failed') and not result.get('independent_lower_after_failed') else 1

if __name__=='__main__':raise SystemExit(main())
