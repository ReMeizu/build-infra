#!/usr/bin/env python3
"""Execute only reviewed anonymous public native inputs through byte-exact Forge."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import struct
import sys
import time
from acquire import acquire, sha, verify_all
from make_j2_successor import FORGE_SHA, prepare
from resource import GIB, RAM_BYTES, admit_values, snapshot
from encrypted_native_retention import keyring
from finish_attempt import run_owned,closed_containers,verify_inputs,atomic_json
from diagnostics import diagnostic

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DOCKER_SHA='bdaa70b28298b269a8009335a9e90987fde0dd1ff08dad5369d133aeb0aadf3b'
RECIPIENT='959CA39B8C9D913EF17718CAE1615C4DD15366ED'
PUBLIC_KEY_SHA='281c6c5992653a27b00592b33aeececcf2affd5d108f46db8f8199a3124730c5'
RETENTION_HELPER_SHA='aff04c7b6ac6e5b98ecfceb0843cbc5bc30ffc33a198ff37617ac66e66d8fd3e'
APPROVED_LOCK_SHA='cd0fd17d93ddf0c7f4cd2da211fafb746cca9aaf8e16e8a9f4867e9700cce4c0'

def command(argv,**kwargs):
    return subprocess.run([str(x) for x in argv],check=True,capture_output=True,timeout=kwargs.pop('timeout',1200),**kwargs)

def checked_public_job(env):
    if env.get('GITHUB_REPOSITORY')!='ReMeizu/build-infra' or env.get('GITHUB_ACTIONS')!='true' or env.get('GITHUB_EVENT_NAME') not in ('push','workflow_dispatch') or env.get('GITHUB_RUN_ATTEMPT')!='1' or env.get('GITHUB_REF')!='refs/heads/codex/free-native-20261009':
        raise ValueError('first-attempt exact owned free-native branch Actions execution required')
    event=json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())
    if event['repository'].get('private') is not False:raise ValueError('free standard route requires actual public repository')
    if env.get('RUNNER_ARCH')!='X64' or os.geteuid()==0:raise ValueError('actual non-root x64 standard runner required')
    if len(os.sched_getaffinity(0))<4:raise ValueError('actual public 4CPU standard runner required')

def consume_native_result(actual,record):
    result_path=actual/'GN_RESULT.json'
    if not result_path.is_file():result_path=actual/'NATIVE_LIBRARIES_RESULT.json'
    if not result_path.is_file():return
    result=json.loads(result_path.read_text())
    if result['source_inventory_sha256']!=record['j2_source_successor']['gn_inputs_sha256']:
        raise ValueError('actual native producer source inventory differs')
    record.update(native_gn_completed=result['native_gn_completed'],native_four_images=result['native_image_built'],
                  native_library_count=len(result['native_libraries']),native_result_sha256=sha(result_path),native_result_name=result_path.name)
    phases=result.get('build_phases',[])
    if result['native_libraries'] and any(x['phase']=='libc-utils-loader' and x['exit_code']==0 for x in phases):
        for row in result['native_libraries']:
            path=actual/row['path'];path.resolve().relative_to(actual.resolve())
            with path.open('rb') as f:header=f.read(64)
            if path.is_symlink() or sha(path)!=row['sha256'] or header[:4]!=b'\x7fELF' or len(header)!=64 or header[4:6]!=b'\x02\x01' or struct.unpack_from('<H',header,18)[0]!=183 or struct.unpack_from('<H',header,16)[0] not in (2,3):
                raise ValueError('actual native target output is not admitted AArch64 linked ELF')
        record['native_compile_executed']=True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock',type=Path,default=HERE/'public_inputs.lock.json')
    args=parser.parse_args()
    checked_public_job(os.environ)
    started=time.monotonic()
    if sha(args.lock)!=APPROVED_LOCK_SHA:raise ValueError('exact reviewed production source lock differs')
    lock=json.loads(args.lock.read_text())
    thin=ROOT/lock['controller_path']
    thin.resolve().relative_to(ROOT.resolve())
    if not thin.is_dir() or thin.is_symlink():raise ValueError('reviewed thin controller missing')
    run=os.environ['GITHUB_RUN_ID']
    if not run.isdigit():raise ValueError('invalid actual run ID')
    job=Path(os.environ['RUNNER_TEMP'])/('native-public-'+run)
    if job.exists():raise ValueError('fresh job input/output required')
    job.mkdir()
    ram=job/'ram';ram.mkdir()
    record={'schema':'remeizu.free-hosted-native-run.v1','run_id':run,
            'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_lock_sha256':sha(args.lock),'full375_phone':False,'runtime':False,
            'private_android_inputs':False,'public_plaintext_outputs_uploaded':False,
            'native_compile_executed':False,'native_four_images':False}
    original=forge=actual=None
    cancelled=[0]
    handlers={sig:signal.signal(sig,lambda value,_frame:cancelled.__setitem__(0,value)) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        mem=snapshot(job)
        # CPU/memory floor is measured before input acquisition. tmpfs is new;
        # this pre-mount check uses requested logical capacity rather than disk.
        admit_values(dict(mem,tmpfs_free_bytes=RAM_BYTES),'prepare',lock['source_bytes'],lock['rust_layout_bytes'])
        command(['sudo','-n','mount','-t','tmpfs','-o','size='+str(RAM_BYTES)+',mode=0700,uid='+str(os.getuid())+',gid='+str(os.getgid()),'tmpfs',ram])
        if command(['stat','-f','-c','%T',ram]).stdout.strip()!=b'tmpfs':raise ValueError('actual tmpfs mount admission failed')
        public_key=HERE/'native-retention-recipient.public.asc'
        if sha(public_key)!=PUBLIC_KEY_SHA or sha(HERE/'encrypted_native_retention.py')!=RETENTION_HELPER_SHA or b'PRIVATE KEY' in public_key.read_bytes():
            raise ValueError('reviewed task public recipient or tested crypto helper differs')
        command(['gpg','--version'],timeout=10)
        keycheck=ram/'retention-preflight';keycheck.mkdir()
        _,fingerprint=keyring(keycheck,public_key)
        if fingerprint!=RECIPIENT:raise ValueError('actual task GPG recipient differs')
        record['retention_preflight_verified']=True
        print('FREE_NATIVE_PHASE actual-RAM-and-task-GPG-preflight-pass',flush=True)
        original=acquire(lock,thin,job/'public-inputs')
        record['public_input_acquisition_verified']=True
        print('FREE_NATIVE_PHASE actual-anonymous-source-inputs-pass',flush=True)
        dockerfile=original/'official-build-env/Dockerfile'
        if sha(dockerfile)!=DOCKER_SHA:raise ValueError('official Android9 Dockerfile bytes differ')
        launcher=ROOT/'vendor/forge/forge_ephemeral_build.py'
        if sha(launcher)!=FORGE_SHA:raise ValueError('official Forge launcher bytes differ')
        tag='androidforge/build-free-native-'+run+':android-9'
        command(['docker','build','-f',dockerfile,'-t',tag,dockerfile.parent],timeout=1800)
        image=command(['docker','image','inspect',tag,'--format','{{.Id}}']).stdout.decode().strip()
        if not image.startswith('sha256:') or len(image)!=71:raise ValueError('actual immutable image ID missing')
        health=command(['docker','run','--rm','--network=none','--user',str(os.getuid())+':'+str(os.getgid()),
            '--mount','type=bind,src='+str(ram)+',dst=/workspace/out',image,'python3','-c',
            "import json,os,pathlib; p=pathlib.Path('/workspace/out/health');p.write_text('actual writable RAM');print(json.dumps({'uid':os.getuid(),'glibc':os.confstr('CS_GNU_LIBC_VERSION'),'writable_ram':p.read_text()=='actual writable RAM'}))"],timeout=60)
        h=json.loads(health.stdout)
        if h['uid']!=os.getuid() or not h['writable_ram']:raise ValueError('actual container non-root/writable output health failed')
        record.update(image_id=image,official_launcher_sha256=sha(launcher),dockerfile_sha256=sha(dockerfile),container_health=h)
        print('FREE_NATIVE_PHASE actual-official-image-health-pass',flush=True)
        remaining=int(260*60-(time.monotonic()-started)-10*60)
        if remaining<600:raise ValueError('source acquisition left no bounded compiler window')
        controller=job/'j2-controller'
        fresh_lock=dict(lock,execution_seconds=min(285*60,remaining))
        successor=prepare(original,controller,fresh_lock)
        record['j2_source_successor']=successor
        model_spec=importlib.util.spec_from_file_location('free_native_official_forge',launcher)
        forge=importlib.util.module_from_spec(model_spec);sys.modules[model_spec.name]=forge;model_spec.loader.exec_module(forge)
        recipe={'image_tag':tag,'build_env_key':'android-9','source_mount_path':str(controller),
                'output_dir_in_container':'/workspace/out','command':['bash','/workspace/src/worker.sh'],
                'extra_mounts':[[str(original/name),'/workspace/src/'+name,'ro'] for name in ('native-source-input','tools','official-python-wheels')],
                'env':{'GN_INPUTS_SHA256':sha(controller/'GN_INPUTS.json'),'PYTHONDONTWRITEBYTECODE':'1',
                       'CCACHE_BASE':'/workspace/out','CCACHE_LOCAL_DIR':'native-ccache','CCACHE_TEMPDIR':'/workspace/out/native-tmp','CCACHE_MAXSIZE':'256M'},
                'timeout_seconds':fresh_lock['execution_seconds']+120,
                'idempotency_key':'public-native'+str(lock['selected_part_count'])+'-'+run+'-'+successor['worker_sha256'][:16]}
        model=forge.recipe_from_dict(recipe)
        recipe_path=job/'recipe.json';recipe_path.write_text(json.dumps(recipe,indent=2)+'\n')
        record['recipe_hash']=model.recipe_hash()
        # Freeze and recheck the actual image immediately before compiler launch.
        if command(['docker','image','inspect',tag,'--format','{{.Id}}']).stdout.decode().strip()!=image:
            raise ValueError('actual Docker image changed after freeze')
        actual=ram/'forge'/model.recipe_hash()
        def started_callback():
            record['actual_forge_submitted']=True
            atomic_json(job/'INFLIGHT_PUBLIC_RESULT.json',record)
            print('FREE_NATIVE_PHASE actual-j2-official-Forge-submitted',flush=True)
        owned=run_owned([sys.executable,'-B',str(launcher),'--recipe',str(recipe_path),'--no-resume'],
             dict(os.environ,FORGE_EPHEMERAL_BASE=str(ram/'forge')),remaining+120,ram,cancelled,started_callback)
        record.update(forge_exit_code=owned['returncode'],owned_launcher_reaped=owned['owned_launcher_reaped'],termination_reason=owned['termination_reason'])
        if owned['returncode']!=0 or owned['termination_reason']:raise ValueError('actual native Forge attempt failed; private RAM logs retained')
        marker=json.loads((actual/'SUCCESS').read_text());manifest=json.loads((actual/'artifacts.json').read_text())
        if (actual/'FAILURE').exists() or marker['recipe_hash']!=model.recipe_hash() or marker['artifacts_sha256']!=sha(actual/'artifacts.json') or marker['artifacts_count']!=len(manifest):
            raise ValueError('actual Forge output binding failed')
        for name,digest in manifest.items():
            path=actual/name;path.resolve().relative_to(actual.resolve())
            if path.is_symlink() or not path.is_file() or sha(path)!=digest:raise ValueError('actual Forge artifact full readback failed')
        record.update(status='ACTUAL_NATIVE_INTERMEDIATE_FORGE_PASS_NOT_FULL375',forge_success_sha256=sha(actual/'SUCCESS'),
                      artifact_manifest_sha256=sha(actual/'artifacts.json'),verified_artifact_count=len(manifest))
    except (Exception,KeyboardInterrupt) as error:
        record.update(status='REFUSED_OR_FAILED_NATIVE_INTERMEDIATE',**diagnostic(error))
        # Avoid dumping fetched stderr, arbitrary exception bodies or output paths.
    finally:
        atomic_json(job/'ATTEMPT_BEFORE_FINALIZATION.json',record)
        if original is not None and forge is not None and actual is not None and record.get('actual_forge_submitted'):
            try:
                closure=closed_containers(forge,actual,record['recipe_hash'])
                record['compiler_termination_verified']=closure['all_owned_container_closure_pass']
                after=verify_inputs(original,lock['gn_inputs_sha256'],ram,timeout=300)
                record['all_public_source_tool_wheel_before_after_verified']=after['all_source_tool_wheel_inventory_pass']
                record['independent_after_witness_sha256']=sha(ram/'PUBLIC_INPUTS_AFTER.json')
                consume_native_result(actual,record)
            except Exception as error:
                record.update(status='REFUSED_POST_ATTEMPT_WITNESS',post_witness_error_type=type(error).__name__)
        for sig,handler in handlers.items():signal.signal(sig,handler)
        atomic_json(job/'PUBLIC_RESULT.json',record)
        print(json.dumps(record,sort_keys=True),flush=True)
    return 0 if record.get('status')=='ACTUAL_NATIVE_INTERMEDIATE_FORGE_PASS_NOT_FULL375' and record.get('all_public_source_tool_wheel_before_after_verified') and record.get('compiler_termination_verified') else 1

if __name__=='__main__':raise SystemExit(main())
