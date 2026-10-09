#!/usr/bin/env python3
"""Retain only source-classified native producer outputs as ciphertext, once."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from acquire import sha
from encrypted_native_retention import seal, MAX_ASSET
from free_native_run import HERE, ROOT, RECIPIENT, PUBLIC_KEY_SHA, RETENTION_HELPER_SHA, APPROVED_LOCK_SHA, checked_public_job,consume_native_result
from finish_attempt import closed_containers,verify_inputs,atomic_json
from setup_commands import HEALTH_CODE
from make_j2_successor import FORGE_SHA
import importlib.util

REPO='ReMeizu/build-infra'
EVIDENCE=('SUCCESS','artifacts.json','FAILURE','run.log','GN_RESULT.json','GN_FAILURE.json','NATIVE_LIBRARIES_RESULT.json','OWNED_TERMINATION.json','build-env-contract.json',
          'native-gn.log','native-runtime-build.log','native-images-build.log','native-python-install.log',
          'NATIVE_HOST_RUNTIME.json','NATIVE_RUST_LAYOUT.json','FREE_HOSTED_RESOURCE.prepare.json',
          'FREE_HOSTED_RESOURCE.libraries.json','FREE_HOSTED_RESOURCE.images.json')
SETUP_PHASES=('docker-build','image-inspect','image-health','image-inspect-prelaunch')

def setup_commands(job,record,lock_sha):
    """Admit completed setup client evidence without constructing Forge identity."""
    if not (record.get('retention_scope')=='SETUP_FAILED' and record.get('status')=='SETUP_FAILED' and
            record.get('public_input_acquisition_verified') is True and record.get('retention_preflight_verified') is True and
            record.get('setup_commands_termination_verified') is True and record.get('actual_forge_submitted') is False and
            record.get('native_compile_executed') is False and record.get('native_four_images') is False and
            record.get('private_android_inputs') is False and record.get('full375_phone') is False and record.get('runtime') is False and
            record.get('source_lock_sha256')==lock_sha):
        raise ValueError('actual source-admitted terminated SETUP_FAILED scope required')
    root=job/'ram/setup-diagnostics';manifest=root/'SETUP_COMMANDS.json'
    if root.is_symlink() or not root.is_dir() or manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size>65536:
        raise ValueError('owned bounded setup command manifest required')
    if sha(manifest)!=record.get('setup_diagnostics_sha256'):raise ValueError('setup command manifest identity drift')
    data=json.loads(manifest.read_text())
    if data.get('schema')!='remeizu.free-native-setup-commands.v1' or data.get('run_id')!=record.get('run_id') or data.get('source_lock_sha256')!=lock_sha:
        raise ValueError('actual setup command run/source binding differs')
    rows=data.get('commands',[]);files=[{'path':'SETUP_COMMANDS.json','kind':'public-producer-evidence','bytes':manifest.stat().st_size,'sha256':sha(manifest)}]
    if not 1<=len(rows)<=len(SETUP_PHASES):raise ValueError('bounded actual setup commands required')
    phases=[];failed=[]
    tag='androidforge/build-free-native-'+record['run_id']+':android-9'
    context=job/'public-inputs/original/official-build-env'
    for row in rows:
        phase=row.get('phase');argv=row.get('argv')
        if phase not in SETUP_PHASES or phase in phases or not isinstance(argv,list) or not all(isinstance(a,str) for a in argv):
            raise ValueError('unknown or duplicate setup phase/argv rejected')
        if row.get('started') is not True or row.get('completed') is not True or row.get('owned_child_reaped') is not True or type(row.get('exit_code')) is not int:
            raise ValueError('actual completed reaped setup client required')
        if row.get('argv_sha256')!=hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest():
            raise ValueError('setup actual command binding differs')
        if phase=='docker-build':
            expected=['docker','build','-f',str(context/'Dockerfile'),'-t',tag,str(context)]
            if argv!=expected:raise ValueError('setup Docker build must use owned public source context')
        elif phase in ('image-inspect','image-inspect-prelaunch'):
            if argv!=['docker','image','inspect',tag,'--format','{{.Id}}']:raise ValueError('setup image inspect scope differs')
        elif (len(argv)!=12 or argv[:5]!=['docker','run','--rm','--network=none','--user'] or
              argv[5]!=str(os.getuid())+':'+str(os.getgid()) or argv[6]!='--mount' or
              argv[7]!='type=bind,src='+str(job/'ram')+',dst=/workspace/out' or
              not re.fullmatch('sha256:[a-f0-9]{64}',argv[8]) or argv[9:11]!=['python3','-c'] or argv[11]!=HEALTH_CODE):
            raise ValueError('setup health command scope differs')
        phases.append(phase)
        if type(row.get('timed_out',False)) is not bool:raise ValueError('actual setup timeout status required')
        if type(row.get('interrupted_signal',0)) is not int or row.get('interrupted_signal',0) not in (0,2,15):
            raise ValueError('actual setup signal status required')
        if row['exit_code']!=0 or row.get('timed_out') is True or row.get('interrupted_signal',0):failed.append(phase)
        for stream in ('stdout','stderr'):
            witness=row.get(stream,{})
            name=phase+'.'+stream
            if witness.get('path')!=name:raise ValueError('unlisted setup evidence path rejected')
            path=root/name
            if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file() or path.stat().st_size!=witness.get('bytes') or sha(path)!=witness.get('sha256'):
                raise ValueError('actual setup log identity differs')
            files.append({'path':name,'kind':'public-producer-evidence','bytes':path.stat().st_size,'sha256':sha(path)})
    if phases!=list(SETUP_PHASES[:len(phases)]) or failed!=[record.get('setup_failure_phase')] or failed[-1]!=phases[-1]:
        raise ValueError('actual failed setup phase/order differs')
    if type(record.get('setup_exit_code')) is not int or record['setup_exit_code']!=rows[-1]['exit_code']:
        raise ValueError('actual setup failure exit binding differs')
    return root,files

def setup_policy(job,record,lock_sha,lock):
    root,files=setup_commands(job,record,lock_sha)
    after=job/'ram/PUBLIC_INPUTS_AFTER.json'
    if (record.get('all_public_source_tool_wheel_before_after_verified') is not True or after.is_symlink() or
            not after.is_file() or after.stat().st_size>65536 or sha(after)!=record.get('independent_after_witness_sha256')):
        raise ValueError('actual setup source after-witness required')
    proof=json.loads(after.read_text())
    if proof.get('all_source_tool_wheel_inventory_pass') is not True or proof.get('gn_inputs_sha256')!=lock['gn_inputs_sha256']:
        raise ValueError('setup readonly input after-witness differs from reviewed inventory')
    for name in ('SETUP_FAILED_SOURCE_AFTER.json',):
        body={'schema':'remeizu.source-admitted-setup-failure-retention.v1','run_id':record['run_id'],
              'source_lock_sha256':lock_sha,'independent_after_witness_sha256':sha(after),
              'setup_commands_manifest_sha256':record['setup_diagnostics_sha256'],'setup_failure_phase':record['setup_failure_phase'],
              'actual_forge_submitted':False,'native_compile_executed':False,'native_four_images':False,
              'forge_identity_fabricated':False,'runtime':False,'full375_phone':False}
        path=root/name
        if path.exists():
            if path.is_symlink() or json.loads(path.read_text())!=body:raise ValueError('original setup retention witness differs')
        else:atomic_json(path,body)
        files.append({'path':name,'kind':'public-producer-evidence','bytes':path.stat().st_size,'sha256':sha(path)})
    return root,{'schema':'remeizu.public-native-output-policy.v1','plaintext_scope':'public-source-native-build-only',
        'private_inputs_admitted':False,'source_lock_sha256':lock_sha,'retention_scope':'SETUP_FAILED','outputs':files}

def command(argv,**kwargs):
    return subprocess.run(argv,check=True,capture_output=True,timeout=kwargs.pop('timeout',120),**kwargs)

def actual_policy(job,record,lock_sha):
    if not (record.get('public_input_acquisition_verified') is True and record.get('retention_preflight_verified') is True and
            record.get('all_public_source_tool_wheel_before_after_verified') is True and record.get('actual_forge_submitted') is True and
            record.get('compiler_termination_verified') is True and record.get('private_android_inputs') is False and record.get('full375_phone') is False and record.get('source_lock_sha256')==lock_sha):
        raise ValueError('actual verified public-source native producer required before retention')
    rh=record['recipe_hash']
    if not re.fullmatch('[a-f0-9]{64}',rh):raise ValueError('actual recipe hash missing')
    root=job/'ram/forge'/rh
    if not root.is_dir() or root.is_symlink():raise ValueError('actual producer RAM output missing')
    files=[]; seen=set()
    def add(name,kind,expected=None):
        path=root/name
        path.resolve().relative_to(root.resolve())
        if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file():raise ValueError('actual regular output required')
        digest=sha(path)
        if expected and (expected['sha256']!=digest or expected['bytes']!=path.stat().st_size):raise ValueError('native output identity drift')
        if name in seen:raise ValueError('duplicate explicit native output')
        seen.add(name);files.append({'path':name,'kind':kind,'bytes':path.stat().st_size,'sha256':digest})
    for name in EVIDENCE:
        if (root/name).is_file():add(name,'public-producer-evidence')
    result_path=root/record.get('native_result_name','GN_RESULT.json')
    if result_path.name not in ('GN_RESULT.json','NATIVE_LIBRARIES_RESULT.json'):
        raise ValueError('unknown actual native producer result')
    if result_path.is_file():
        result=json.loads(result_path.read_text())
        if result.get('source_inventory_sha256')!=record['j2_source_successor']['gn_inputs_sha256']:
            raise ValueError('actual native producer source identity differs')
        if result.get('runtime') or result.get('complete_gui_phone') or result.get('whole_image_producer_admission'):
            raise ValueError('native intermediate cannot claim whole image or runtime')
        for row in result.get('native_libraries',[]):
            name=row['path']
            if not name.startswith('native-source/out/') or any(p in name for p in ('android-overlay','android-system','android-vendor','.private')):
                raise ValueError('unknown/private Android binary scope rejected')
            if record.get('native_compile_executed') is not True:raise ValueError('linked native compilation identity not verified')
            add(name,'native-elf',row)
        for row in result.get('native_images',[]):
            name=row['path'];partition=row.get('partition')
            if partition not in ('system','vendor','sys_prod','chip_prod') or not name.startswith('native-source/out/') or not name.endswith('/images/'+partition+'.img'):
                raise ValueError('unknown/private image scope rejected')
            add(name,'native-image',row)
    if not files:raise ValueError('no actual explicit producer evidence retained')
    return root,{'schema':'remeizu.public-native-output-policy.v1','plaintext_scope':'public-source-native-build-only',
        'private_inputs_admitted':False,'source_lock_sha256':lock_sha,'outputs':files}

def cipher_upper_bound(policy):
    # Full tar framing/padding plus a conservative 2% gzip/OpenPGP overhead and
    # 16MiB crypto/keyring/manifest margin. No unknown compression ratio is
    # counted as available capacity; all parts remain in owned RAM.
    sizes=[r['bytes'] for r in policy['outputs']]+[len(json.dumps(policy,sort_keys=True,indent=2).encode())+1]
    tar_bytes=sum(512+((n+511)//512)*512 for n in sizes)+10240
    return tar_bytes+(tar_bytes+49)//50+16*1024**2

def recover_after_witness(job,record,lock):
    if record.get('retention_scope')=='SETUP_FAILED':
        setup_commands(job,record,sha(HERE/'public_inputs.lock.json'))
        if record.get('all_public_source_tool_wheel_before_after_verified') is True:return record
        after=verify_inputs(job/'public-inputs/original',lock['gn_inputs_sha256'],job/'ram',timeout=300)
        recovered=dict(record,all_public_source_tool_wheel_before_after_verified=after['all_source_tool_wheel_inventory_pass'],
            independent_after_witness_sha256=sha(job/'ram/PUBLIC_INPUTS_AFTER.json'),recovered_setup_after_witness=True)
        atomic_json(job/'RETENTION_SETUP_ADMISSION.json',recovered)
        return recovered
    if record.get('compiler_termination_verified') and record.get('all_public_source_tool_wheel_before_after_verified'):
        return record
    if not record.get('actual_forge_submitted') or not record.get('public_input_acquisition_verified') or record.get('source_lock_sha256')!=sha(HERE/'public_inputs.lock.json'):
        raise ValueError('no actual source-admitted in-flight compiler attempt to recover')
    rh=record['recipe_hash']
    if not re.fullmatch('[a-f0-9]{64}',rh):raise ValueError('recovery actual recipe hash missing')
    launcher=ROOT/'vendor/forge/forge_ephemeral_build.py'
    if sha(launcher)!=FORGE_SHA:raise ValueError('recovery official ownership guard bytes differ')
    spec=importlib.util.spec_from_file_location('retention_recovery_official_forge',launcher)
    forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
    actual=job/'ram/forge'/rh
    closure=closed_containers(forge,actual,rh)
    after=verify_inputs(job/'public-inputs/original',lock['gn_inputs_sha256'],job/'ram',timeout=300)
    recovered=dict(record,compiler_termination_verified=closure['all_owned_container_closure_pass'],
        all_public_source_tool_wheel_before_after_verified=after['all_source_tool_wheel_inventory_pass'],
        recovered_independent_after_witness=True,independent_after_witness_sha256=sha(job/'ram/PUBLIC_INPUTS_AFTER.json'))
    consume_native_result(actual,recovered)
    atomic_json(job/'RETENTION_ADMISSION.json',recovered)
    return recovered

def complete_snapshot(candidates,run,lock_sha):
    for path in candidates:
        if not path.is_file() or path.is_symlink() or path.stat().st_size>65536:continue
        try:record=json.loads(path.read_text())
        except (OSError,ValueError):continue
        if isinstance(record,dict) and record.get('schema')=='remeizu.free-hosted-native-run.v1' and record.get('run_id')==run and record.get('source_lock_sha256')==lock_sha and record.get('full375_phone') is False and record.get('private_android_inputs') is False:
            return path,record
    raise ValueError('no complete actual source-bound attempt snapshot')

def remote_media_sha(tag,name,env):
    proc=subprocess.Popen(['gh','release','download',tag,'--repo',REPO,'--pattern',name,'--output','-'],
                          env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    timer=threading.Timer(900,proc.kill);timer.start()
    h=hashlib.sha256();count=0
    try:
        for data in iter(lambda:proc.stdout.read(4*1024**2),b''):h.update(data);count+=len(data)
        stderr=proc.stderr.read()
        if proc.wait(timeout=20)!=0 or len(stderr)>65536:raise ValueError('complete remote ciphertext readback failed')
        return count,h.hexdigest()
    finally:
        timer.cancel();proc.stdout.close();proc.stderr.close()

def publish_cipher(output,manifest,tag,env):
    if not re.fullmatch('native-public-[1-9][0-9]{0,19}',tag):raise ValueError('owned actual run release tag required')
    commit=env.get('GITHUB_SHA','')
    if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('actual reviewed workflow commit required')
    for row in manifest['parts']:
        path=output/row['name']
        if not 0<row['bytes']<MAX_ASSET or sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:
            raise ValueError('ciphertext release asset body differs')
    # Never overwrite an existing release or asset; interrupted uploads remain
    # concrete partial evidence, with no retry being reported as success.
    existing=subprocess.run(['gh','release','view',tag,'--repo',REPO],env=env,capture_output=True,timeout=60)
    if existing.returncode==0:raise ValueError('owned run release already exists; no overwrite')
    command(['gh','release','create',tag,'--repo',REPO,'--target',commit,'--prerelease',
        '--title','Encrypted public native attempt '+env['GITHUB_RUN_ID'],
        '--notes','Public-source native intermediate, encrypted to the local task recipient. Full375 and hardware runtime remain unverified. Source lock '+manifest['source_lock_sha256']],env=env)
    paths=[str(output/row['name']) for row in manifest['parts']]+[str(output/'CIPHERTEXT_MANIFEST.json')]
    command(['gh','release','upload',tag,'--repo',REPO,*paths],env=env,timeout=1200)
    meta=json.loads(command(['gh','api','repos/'+REPO+'/releases/tags/'+tag],env=env).stdout)
    assets={a['name']:a for a in meta['assets']}
    expected=[dict(row) for row in manifest['parts']]+[{'name':'CIPHERTEXT_MANIFEST.json','bytes':(output/'CIPHERTEXT_MANIFEST.json').stat().st_size,'sha256':sha(output/'CIPHERTEXT_MANIFEST.json')}]
    checks=[];combined=hashlib.sha256()
    for row in expected:
        if row['name'] not in assets or assets[row['name']]['size']!=row['bytes']:raise ValueError('actual release ciphertext asset size differs')
        digest=assets[row['name']].get('digest')
        if digest!='sha256:'+row['sha256']:raise ValueError('actual GitHub ciphertext asset digest absent or differs')
        count,actual=remote_media_sha(tag,row['name'],env)
        if count!=row['bytes'] or actual!=row['sha256']:raise ValueError('remote full ciphertext media readback differs')
        checks.append({'name':row['name'],'bytes':count,'sha256':actual,'provider_digest':digest,'full_media_readback_pass':True})
    for row in manifest['parts']:
        with (output/row['name']).open('rb') as f:
            for data in iter(lambda:f.read(4*1024**2),b''):combined.update(data)
    if combined.hexdigest()!=manifest['ciphertext_sha256']:raise ValueError('all ciphertext parts concatenated SHA differs')
    return {'schema':'remeizu.free-hosted-native-ciphertext-release.v1','release_url':meta['html_url'],
        'actual_workflow_commit':commit,'source_lock_sha256':manifest['source_lock_sha256'],'ciphertext_manifest_sha256':sha(output/'CIPHERTEXT_MANIFEST.json'),
        'uploads_performed':True,'all_remote_ciphertext_sha_size_pass':True,'all_provider_digests_present':all(c['provider_digest'] for c in checks),
        'ciphertext_sha256':manifest['ciphertext_sha256'],'assets':checks,'plaintext_uploaded':False,
        'authenticated_local_decryption_required_before_extract':True,'full375_phone':False,'runtime':False}

def main():
    checked_public_job(os.environ)
    if not os.environ.get('GH_TOKEN'):raise ValueError('built-in upload-step token required')
    run=os.environ['GITHUB_RUN_ID'];job=Path(os.environ['RUNNER_TEMP'])/('native-public-'+run)
    candidates=[job/name for name in ('PUBLIC_RESULT.json','ATTEMPT_BEFORE_FINALIZATION.json','INFLIGHT_PUBLIC_RESULT.json')]
    source_lock=HERE/'public_inputs.lock.json';lock_sha=sha(source_lock)
    if lock_sha!=APPROVED_LOCK_SHA:raise ValueError('exact reviewed production source lock differs before retention')
    original_record,record=complete_snapshot(candidates,run,lock_sha)
    original_record_sha=sha(original_record)
    record=recover_after_witness(job,record,json.loads(source_lock.read_text()))
    if sha(original_record)!=original_record_sha:raise ValueError('original failed attempt record changed during retention recovery')
    lock=json.loads(source_lock.read_text())
    root,policy=(setup_policy(job,record,lock_sha,lock) if record.get('retention_scope')=='SETUP_FAILED' else actual_policy(job,record,lock_sha))
    output=job/'ram/ciphertext';output.mkdir()
    bound=cipher_upper_bound(policy)
    if shutil.disk_usage(output).free<bound:raise ValueError('actual RAM cannot retain worst-case complete ciphertext; no upload attempted')
    policy_file=job/'ram/NATIVE_OUTPUT_POLICY.json';policy_file.write_text(json.dumps(policy,sort_keys=True,indent=2)+'\n')
    if sha(HERE/'encrypted_native_retention.py')!=RETENTION_HELPER_SHA or sha(HERE/'native-retention-recipient.public.asc')!=PUBLIC_KEY_SHA:
        raise ValueError('reviewed crypto source/key identity differs')
    manifest=seal(root,policy_file,sha(policy_file),HERE/'native-retention-recipient.public.asc',RECIPIENT,output,512*1024**2)
    env=dict(os.environ,GH_HOST='github.com')
    receipt=publish_cipher(output,manifest,'native-public-'+run,env)
    receipt['retention_scope']=record.get('retention_scope','NATIVE_FORGE')
    if receipt['retention_scope']=='SETUP_FAILED':
        receipt.update(actual_forge_submitted=False,native_compile_executed=False,native_four_images=False,forge_identity_fabricated=False)
    atomic_json(job/'RELEASE_RETENTION.json',receipt)
    print(json.dumps(receipt,sort_keys=True),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
