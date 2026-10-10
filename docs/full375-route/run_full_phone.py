"""Full canonical public producer: disk inputs, RAM outputs, unchanged Forge."""
import datetime
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FREE=HERE.parent/'free-hosted-route'
sys.path.insert(1,str(FREE))
from acquire_full_phone import acquire_full
from acquire import verify_all
from finish_attempt import run_owned,closed_containers,atomic_json
from encrypted_native_retention import keyring
from setup_commands import execute as setup_command,HEALTH_CODE,SetupCommandError
from make_overlay_worker import transformed_worker
from full_profile import require_profile
from original_resource_snapshot import snapshot
from container_image_witness import ImageObserver
from producer_metadata import before_launch,after_launch

FORGE_SHA='9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8'
DOCKER_SHA='bdaa70b28298b269a8009335a9e90987fde0dd1ff08dad5369d133aeb0aadf3b'
RECIPIENT='959CA39B8C9D913EF17718CAE1615C4DD15366ED'
RAM_BYTES=10*1024**3
APPROVED_LOCK_SHA='c2c9fd52665ca5fad3778f61d0a429e5dd55430a4228e05cb2003d7cd5e06474'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024**2),b''):h.update(block)
    return h.hexdigest()

def checked_job(env):
    if env.get('GITHUB_ACTIONS')!='true' or env.get('GITHUB_EVENT_NAME') not in ('push','workflow_dispatch') or env.get('GITHUB_REPOSITORY')!='ReMeizu/build-infra' or env.get('GITHUB_REF')!='refs/heads/codex/free-full375-20261010' or env.get('GITHUB_RUN_ATTEMPT')!='1':
        raise ValueError('exact first-attempt public full producer required')
    event=json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())
    if event['repository'].get('private') is not False or os.geteuid()==0 or env.get('RUNNER_ARCH')!='X64':
        raise ValueError('public non-root standard x64 runner required')
    if not re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')):raise ValueError('actual run ID required')

def cancellation_handler(cancelled,acquiring):
    def cancel(value,_frame):
        cancelled[0]=value
        if acquiring[0]:raise KeyboardInterrupt
    return cancel

def prepare_controller(original,target,ram,seconds):
    if target.exists():raise ValueError('fresh full controller required')
    shutil.copytree(original,target,ignore=shutil.ignore_patterns('native-source-input','tools','official-python-wheels'))
    inputs=json.loads((target/'GN_INPUTS.json').read_text());require_profile(inputs,original)
    worker=transformed_worker((original/'native_gn_worker.py').read_bytes())
    (target/'native_gn_worker.py').write_text(worker)
    for name in ('overlay_io.py','full_profile.py','nonproduction_scope.py','full_overlay_protocol.py','original_resource_snapshot.py','native_target_witness.py'):
        shutil.copyfile(HERE/name,target/name)
        inputs['successor_evidence'][name]=sha(target/name)
    inputs['successor_evidence']['canonical_full_phone_coverage.json']=sha(target/'canonical_full_phone_coverage.json')
    inputs['successor_evidence']['runtime_core_nonproduction_scope.json']=sha(target/'runtime_core_nonproduction_scope.json')
    modified=set()
    for patch in inputs['patches']:
        for line in (original/patch['path']).read_text().splitlines():
            if line.startswith('+++ b/'):
                modified.add(str(Path(patch['target'])/line[6:]))
    copy_up=sum(row.get('bytes',0) for row in inputs['source_files'] if row['path'] in modified)
    copy_up+=sum((original/row['path']).stat().st_size for row in inputs['patches']+inputs['overlay_files'])
    sys.path.insert(0,str(original))
    try:
        from layout_native_rust import project_manifest
        projection={}
        for tool in inputs['tools']:
            if tool.get('layout')=='rust-components':
                _,rows=project_manifest(original/tool['payload_root'],tool['subdir'],tool['members'])
                for row in rows:
                    value=(row['sha256'],(original/tool['payload_root']/row['path']).stat().st_size)
                    if row['destination'] in projection and projection[row['destination']]!=value:raise ValueError('original Rust projection conflict')
                    projection[row['destination']]=value
    finally:sys.path.pop(0)
    inputs.update(worker_sha256=sha(target/'native_gn_worker.py'),execution_deadline_seconds=seconds,
                  free_hosted_rust_layout_bytes=sum(row[1] for row in projection.values()),planned_copy_up_bytes=copy_up,
                  lower_inventory_sha256=hashlib.sha256(json.dumps(inputs['source_files'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                  overlay_host_paths={name:str(ram/name) for name in ('lower','upper','work')})
    (target/'GN_INPUTS.json').write_text(json.dumps(inputs,sort_keys=True,indent=2)+'\n')
    for name in ('native-source-input','tools','official-python-wheels'):
        (target/name).mkdir();(target/name/'.mount-target').write_text('readonly public input mount\n')
    names=[str(path.relative_to(target)) for path in target.rglob('*') if path.is_file() or path.is_symlink()]
    for argv in (['git','init','-q',str(target)],['git','-C',str(target),'add','--',*names],
                 ['git','-C',str(target),'-c','user.name=ReMeizu','-c','user.email=build@remeizu.invalid','commit','-qm','Freeze actual canonical full phone controller']):
        subprocess.run(argv,check=True,capture_output=True,timeout=120)
    return inputs

def make_recipe(controller,original,ram,image,run,inputs_sha,seconds,worker_sha):
    if image!='androidforge/build-full-phone-'+run+':android-9':raise ValueError('exact official per-run Android9 versioned tag required')
    if not 600<=seconds<=260*60 or not re.fullmatch('[a-f0-9]{64}',inputs_sha) or not re.fullmatch('[a-f0-9]{64}',worker_sha):raise ValueError('bounded actual controller/worker identity required')
    return {'image_tag':image,'build_env_key':'android-9','source_mount_path':str(controller),
            'output_dir_in_container':'/workspace/out','command':['bash','/workspace/src/worker.sh'],
            'extra_mounts':[[str(ram),'/workspace/ram','rw'],[str(ram/'lower'),'/workspace/src/native-source-input','ro'],
                            [str(original/'tools'),'/workspace/src/tools','ro'],[str(original/'official-python-wheels'),'/workspace/src/official-python-wheels','ro']],
            'env':{'GN_INPUTS_SHA256':inputs_sha,'PYTHONDONTWRITEBYTECODE':'1','CCACHE_BASE':'/workspace/out',
                   'CCACHE_LOCAL_DIR':'native-ccache','CCACHE_TEMPDIR':'/workspace/out/native-tmp','CCACHE_MAXSIZE':'256M'},
            'timeout_seconds':seconds+120,'idempotency_key':'canonical-full-phone-'+run+'-'+worker_sha[:16]}

def verify_full_inputs(original,gn_sha,ram,timeout=600,cancelled=None):
    """Bounded owned readonly witness; cancelled outer jobs leave no reader."""
    output=ram/'PUBLIC_INPUTS_AFTER.json'
    log=ram/('full-source-after.'+str(os.getpid())+'.private.stderr')
    with log.open('ab') as stderr:
        proc=subprocess.Popen([sys.executable,'-B',str(FREE/'verify_inputs_after.py'),'--root',str(original),'--gn-sha256',gn_sha,'--output',str(output)],stdout=subprocess.DEVNULL,stderr=stderr,start_new_session=True)
        deadline=time.monotonic()+timeout
        try:
            while proc.poll() is None:
                if (cancelled and cancelled[0]) or time.monotonic()>=deadline:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
                    raise ValueError('owned source-after witness cancelled or deadline exceeded')
                time.sleep(.1)
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
            raise
    if proc.returncode or output.is_symlink() or not output.is_file() or output.stat().st_size>65536:raise ValueError('actual bounded readonly input witness failed')
    proof=json.loads(output.read_text())
    if proof.get('all_source_tool_wheel_inventory_pass') is not True or proof.get('gn_inputs_sha256')!=gn_sha:raise ValueError('actual input witness identity differs')
    return proof


def verify_forge_success(forge,actual,record):
    for name in ('SUCCESS','artifacts.json'):
        path=actual/name
        if path.is_symlink() or not path.is_file():raise ValueError('actual original Forge success files required')
    if (actual/'FAILURE').exists():raise ValueError('original Forge failure cannot become success')
    marker=forge.read_success_marker(actual)
    artifacts=forge.read_cached_artifacts(actual)
    if marker.get('recipe_hash')!=record['recipe_hash'] or marker.get('artifacts_sha256')!=sha(actual/'artifacts.json') or marker.get('artifacts_count')!=len(artifacts) or not artifacts:
        raise ValueError('actual Forge success recipe/artifact binding differs')
    record.update(forge_success_sha256=sha(actual/'SUCCESS'),artifact_manifest_sha256=sha(actual/'artifacts.json'),verified_artifact_count=len(artifacts),forge_success_readback_verified=True)


def main():
    checked_job(os.environ);start=time.monotonic();run=os.environ['GITHUB_RUN_ID']
    lock_path=HERE/'full_phone_public_inputs.lock.a1.json';lock=json.loads(lock_path.read_text())
    if sha(lock_path)!=APPROVED_LOCK_SHA:raise ValueError('exact reviewed expected full source lock required')
    job=Path(os.environ['RUNNER_TEMP'])/('full-phone-public-'+run)
    if job.exists():raise ValueError('fresh full public job required')
    job.mkdir();ram=job/'ram';ram.mkdir();cancelled=[0]
    acquiring=[False]
    # Acquisition owns Git/LFS groups and catches BaseException to reap them.
    # Do not suppress cancellation until its 900s network deadline.
    cancel=cancellation_handler(cancelled,acquiring)
    handlers={sig:signal.signal(sig,cancel) for sig in (signal.SIGINT,signal.SIGTERM)}
    record={'schema':'remeizu.canonical-full-phone-public-run.v1','run_id':run,'source_lock_sha256':sha(lock_path),
            'profile_kind':'canonical-full-gui-a2','original_requests':375,'actual_selected_parts':366,
            'private_android_inputs':False,'actual_forge_submitted':False,'native_four_images':False,'native_compile_executed':False,
            'complete_gui_phone':False,'full375_phone':False,'runtime':False,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    forge=original=actual=inputs=None;mounts=[]
    try:
        resource=snapshot(job)
        if resource['cpu_affinity']<4 or resource['available_bytes']<12*1024**3:raise ValueError('actual standard-runner preparation capacity required')
        subprocess.run(['sudo','-n','mount','-t','tmpfs','-o','size='+str(RAM_BYTES)+',mode=0700,uid='+str(os.getuid())+',gid='+str(os.getgid()),'tmpfs',str(ram)],check=True,capture_output=True,timeout=30);mounts.append(ram)
        (ram/'retention-preflight').mkdir()
        _,fingerprint=keyring(ram/'retention-preflight',FREE/'native-retention-recipient.public.asc')
        if fingerprint!=RECIPIENT:raise ValueError('actual task recipient differs')
        record['retention_preflight_verified']=True
        acquiring[0]=True
        try:original=acquire_full(lock,HERE,job/'public-inputs')
        finally:acquiring[0]=False
        record.update(public_input_acquisition_verified=True,original_gn_inputs_sha256=sha(original/'GN_INPUTS.json'))
        atomic_json(job/'INFLIGHT_FULL_RESULT.json',record)
        print('FULL_PHONE_PHASE all-actual-public-inputs-verified',flush=True)
        dockerfile=original/'official-build-env/Dockerfile';launcher=ROOT/'vendor/forge/forge_ephemeral_build.py'
        if sha(dockerfile)!=DOCKER_SHA or sha(launcher)!=FORGE_SHA:raise ValueError('unchanged official environment/Forge required')
        tag='androidforge/build-full-phone-'+run+':android-9'
        setup_command('docker-build',['docker','build','-f',dockerfile,'-t',tag,dockerfile.parent],ram,record,timeout=1800,cancelled=cancelled)
        image=setup_command('image-inspect',['docker','image','inspect',tag,'--format','{{.Id}}'],ram,record,cancelled=cancelled).stdout.decode().strip()
        record['image_id']=image
        health=setup_command('image-health',['docker','run','--rm','--network=none','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(ram)+',dst=/workspace/out',image,'python3','-c',HEALTH_CODE],ram,record,timeout=60,cancelled=cancelled)
        record['container_health']=json.loads(health.stdout)
        if record['container_health']['uid']!=os.getuid() or not record['container_health']['writable_ram']:raise ValueError('actual non-root writable RAM health required')
        for name in ('lower','upper','work','merged'):(ram/name).mkdir()
        subprocess.run(['sudo','-n','mount','--bind',str(original/'native-source-input'),str(ram/'lower')],check=True,capture_output=True,timeout=30);mounts.append(ram/'lower')
        subprocess.run(['sudo','-n','mount','-o','remount,bind,ro',str(ram/'lower')],check=True,capture_output=True,timeout=30)
        subprocess.run(['sudo','-n','mount','-t','overlay','overlay','-o','lowerdir='+str(ram/'lower')+',upperdir='+str(ram/'upper')+',workdir='+str(ram/'work'),str(ram/'merged')],check=True,capture_output=True,timeout=30);mounts.append(ram/'merged')
        remaining=int(260*60-(time.monotonic()-start)-10*60)
        if cancelled[0]:raise KeyboardInterrupt
        if remaining<600:raise ValueError('acquisition left no real compiler window')
        controller=job/'controller';inputs=prepare_controller(original,controller,ram,remaining)
        spec=importlib.util.spec_from_file_location('full_phone_official_forge',launcher);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
        inspected=setup_command('image-inspect-prelaunch',['docker','image','inspect',tag,'--format','{{.Id}}'],ram,record,cancelled=cancelled).stdout.decode().strip()
        if inspected!=image:raise ValueError('actual official image changed after health')
        recipe=make_recipe(controller,original,ram,tag,run,sha(controller/'GN_INPUTS.json'),remaining,inputs['worker_sha256'])
        model=forge.recipe_from_dict(recipe);record.update(recipe_hash=model.recipe_hash(),worker_sha256=inputs['worker_sha256'],actual_gn_inputs_sha256=sha(controller/'GN_INPUTS.json'),official_forge_sha256=sha(launcher),dockerfile_sha256=sha(dockerfile))
        if cancelled[0]:raise KeyboardInterrupt
        recipe_path=job/'recipe.json';recipe_path.write_text(json.dumps(recipe,indent=2)+'\n');actual=ram/'forge'/model.recipe_hash()
        before_launch(job,forge,model,controller,image)
        def started_callback():record['actual_forge_submitted']=True;atomic_json(job/'INFLIGHT_FULL_RESULT.json',record);print('FULL_PHONE_PHASE actual-full-GN-link-images-Forge-submitted',flush=True)
        observer=ImageObserver(forge,actual,model.recipe_hash(),image,tag,cancelled);observer.start()
        try:
            result=run_owned([sys.executable,'-B',str(launcher),'--recipe',str(recipe_path),'--no-resume'],dict(os.environ,FORGE_EPHEMERAL_BASE=str(ram/'forge')),remaining+120,ram,cancelled,started_callback)
        finally:
            observed=observer.finish();record['owned_container_image_verified']=observed['all_observed_owned_images_verified']
            after_launch(job,tag,image);record['image_tag_after_verified']=True
        record.update(forge_exit_code=result['returncode'],termination_reason=result['termination_reason'],owned_launcher_reaped=result['owned_launcher_reaped'])
        record['status']='ACTUAL_FULL_NATIVE_PRODUCER_RETURNED' if result['returncode']==0 and not result['termination_reason'] else 'FULL_NATIVE_FAILED'
        if record['status']=='ACTUAL_FULL_NATIVE_PRODUCER_RETURNED':verify_forge_success(forge,actual,record)
    except (Exception,KeyboardInterrupt) as error:
        record.update(status='FULL_NATIVE_REFUSED_OR_FAILED',error_type=type(error).__name__)
        if isinstance(error,SetupCommandError):record.update(status='SETUP_FAILED',retention_scope='SETUP_FAILED',setup_exit_code=error.exit_code)
        # Recovery must retain the actual failed attempt even if the bounded
        # independent witness is interrupted by the outer job deadline.
        atomic_json(job/'INFLIGHT_FULL_RESULT.json',record)
    finally:
        if actual is not None and forge is not None and record.get('actual_forge_submitted'):
            try:
                proof=closed_containers(forge,actual,record['recipe_hash'])
                record['compiler_termination_verified']=proof['all_owned_container_closure_pass']
            except Exception as error:record.update(compiler_termination_verified=False,closure_error_type=type(error).__name__)
        # Closure and readonly witness are independent obligations. A failed
        # witness must never skip reconciliation of already submitted Docker.
        if original is not None and record.get('public_input_acquisition_verified'):
            try:
                after=verify_full_inputs(original,record['original_gn_inputs_sha256'],ram,timeout=600,cancelled=cancelled)
                record.update(all_public_source_tool_wheel_before_after_verified=after['all_source_tool_wheel_inventory_pass'],independent_after_witness_sha256=sha(ram/'PUBLIC_INPUTS_AFTER.json'))
            except Exception as error:record.update(post_witness_status='REFUSED',post_witness_error_type=type(error).__name__,all_public_source_tool_wheel_before_after_verified=False)
        if record.get('actual_forge_submitted'):
            record['retention_scope']='NATIVE_FORGE'
            try:
                result_file=actual/'GN_RESULT.json'
                if not result_file.is_file():result_file=actual/'NATIVE_LIBRARIES_RESULT.json'
                if result_file.is_file():
                    result=json.loads(result_file.read_text())
                    if result['source_inventory_sha256']!=record['actual_gn_inputs_sha256']:raise ValueError('actual full producer inventory differs')
                    record.update(native_gn_completed=result['native_gn_completed'],native_four_images=result['native_image_built'],native_result_sha256=sha(result_file),native_result_name=result_file.name)
                compiled=bool(result.get('native_libraries')) and any(row.get('phase')=='libc-utils-loader' and row.get('exit_code')==0 for row in result.get('build_phases',[])) if result_file.is_file() else False
                if compiled or record.get('native_four_images'):
                    from retain_full_phone import actual_policy
                    if record.get('owned_container_image_verified') is not True or record.get('image_tag_after_verified') is not True:raise ValueError('actual owned image and postlaunch ID required')
                    actual_policy(job,record,record['source_lock_sha256'])
                    record['native_compile_executed']=compiled
            except Exception as error:record.update(native_four_images=False,result_admission_error_type=type(error).__name__)
        atomic_json(job/'PUBLIC_RESULT.json',record);print(json.dumps(record,sort_keys=True),flush=True)
        for sig,handler in handlers.items():signal.signal(sig,handler)
        # Mounts must survive encrypted retention. The hosted VM owns teardown;
        # an unresolved client never triggers a premature source unmount.
    return 0 if record.get('status')=='ACTUAL_FULL_NATIVE_PRODUCER_RETURNED' and record.get('forge_success_readback_verified') and record.get('native_four_images') and record.get('compiler_termination_verified') and record.get('all_public_source_tool_wheel_before_after_verified') else 1

if __name__=='__main__':raise SystemExit(main())
