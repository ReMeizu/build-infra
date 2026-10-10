"""Seal explicit genuine public outputs; never export source or Android donors."""
import json
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import struct
import sys

HERE=Path(__file__).resolve().parent
FREE=HERE.parent/'free-hosted-route'
sys.path.insert(1,str(FREE))
from encrypted_native_retention import seal,sha
from retain_release import cipher_upper_bound,publish_cipher
from finish_attempt import atomic_json,closed_containers
from setup_commands import HEALTH_CODE

RECIPIENT='959CA39B8C9D913EF17718CAE1615C4DD15366ED'
HELPER_SHA='aff04c7b6ac6e5b98ecfceb0843cbc5bc30ffc33a198ff37617ac66e66d8fd3e'
EVIDENCE=('SUCCESS','FAILURE','artifacts.json','GN_RESULT.json','GN_FAILURE.json','NATIVE_LIBRARIES_RESULT.json',
          'NATIVE_WORKER_RESOURCE.json','NATIVE_RUST_LAYOUT.json','NATIVE_HOST_RUNTIME.json','OWNED_TERMINATION.json',
          'native-gn.log','native-runtime-build.log','native-images-build.log','native-python-install.log',
          'FULL_OVERLAY_SOURCE_BEFORE.json','FULL_OVERLAY_SOURCE_AFTER.json',
          'FULL_OVERLAY_RESOURCE.prepare.json','FULL_OVERLAY_RESOURCE.libraries.json','FULL_OVERLAY_RESOURCE.images.json',
          'NATIVE_GN_TARGET_OUTPUTS.json','NATIVE_GN_TARGET_DECLARATIONS.json','OWNED_CONTAINER_IMAGE.json',
          'native-gn-desc-0.json','native-gn-desc-1.json','native-gn-desc-2.json','native-gn-desc-3.json')

SETUP_PHASES=('docker-build','image-inspect','image-health','image-inspect-prelaunch')
APPROVED_LOCK_SHA='c2c9fd52665ca5fad3778f61d0a429e5dd55430a4228e05cb2003d7cd5e06474'

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
    tag='androidforge/build-full-phone-'+record['run_id']+':android-9'
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


def setup_policy(job,record,lock_sha):
    if record.get('profile_kind')!='canonical-full-gui-a2':raise ValueError('exact full setup profile required')
    root,files=setup_commands(job,record,lock_sha)
    after=job/'ram/PUBLIC_INPUTS_AFTER.json'
    if after.is_symlink() or not after.is_file() or after.stat().st_size>65536 or sha(after)!=record.get('independent_after_witness_sha256'):
        raise ValueError('actual source after-witness required')
    proof=json.loads(after.read_text())
    if record.get('all_public_source_tool_wheel_before_after_verified') is not True or proof.get('all_source_tool_wheel_inventory_pass') is not True or proof.get('gn_inputs_sha256')!=record.get('original_gn_inputs_sha256'):
        raise ValueError('full setup source after-witness differs')
    body={'schema':'remeizu.full-phone-source-admitted-setup-failure.v1','run_id':record['run_id'],
          'source_lock_sha256':lock_sha,'independent_after_witness_sha256':sha(after),
          'actual_forge_submitted':False,'native_compile_executed':False,'native_four_images':False,'runtime':False}
    path=root/'SETUP_FAILED_SOURCE_AFTER.json'
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text())!=body:raise ValueError('original setup witness differs')
    else:atomic_json(path,body)
    files.append({'path':path.name,'kind':'public-producer-evidence','bytes':path.stat().st_size,'sha256':sha(path)})
    return root,{'schema':'remeizu.public-native-output-policy.v1','plaintext_scope':'public-source-native-build-only',
                'private_inputs_admitted':False,'source_lock_sha256':lock_sha,'outputs':files,'retention_scope':'SETUP_FAILED'}


def recover_admission(job,record,lock_sha):
    if record.get('source_lock_sha256')!=lock_sha or record.get('public_input_acquisition_verified') is not True:
        raise ValueError('actual source-acquired full attempt required')
    original=job/'public-inputs/original'
    if sha(original/'GN_INPUTS.json')!=record.get('original_gn_inputs_sha256'):raise ValueError('actual original full inventory drift')
    from full_profile import require_profile
    require_profile(json.loads((original/'GN_INPUTS.json').read_text()),original)
    result=dict(record)
    if record.get('retention_scope')=='SETUP_FAILED':
        setup_commands(job,record,lock_sha)
    elif record.get('actual_forge_submitted') is True:
        rh=record.get('recipe_hash','')
        if not re.fullmatch('[a-f0-9]{64}',rh):raise ValueError('actual recovery recipe required')
        from run_full_phone import FORGE_SHA,ROOT
        launcher=ROOT/'vendor/forge/forge_ephemeral_build.py'
        if sha(launcher)!=FORGE_SHA:raise ValueError('actual official Forge identity differs')
        spec=importlib.util.spec_from_file_location('full_retention_official_forge',launcher)
        forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
        closure=closed_containers(forge,job/'ram/forge'/rh,rh)
        result['compiler_termination_verified']=closure['all_owned_container_closure_pass']
    else:raise ValueError('no actual setup failure or Forge submission')
    after_file=job/'ram/PUBLIC_INPUTS_AFTER.json'
    if record.get('all_public_source_tool_wheel_before_after_verified') is True:
        if after_file.is_symlink() or not after_file.is_file() or after_file.stat().st_size>65536 or sha(after_file)!=record.get('independent_after_witness_sha256'):raise ValueError('actual completed after-witness identity differs')
        after=json.loads(after_file.read_text())
        if after.get('all_source_tool_wheel_inventory_pass') is not True or after.get('gn_inputs_sha256')!=record['original_gn_inputs_sha256']:raise ValueError('actual completed after-witness inventory differs')
    else:
        from run_full_phone import verify_full_inputs
        after=verify_full_inputs(original,record['original_gn_inputs_sha256'],job/'ram',timeout=600)
        result.update(all_public_source_tool_wheel_before_after_verified=after['all_source_tool_wheel_inventory_pass'],
                      independent_after_witness_sha256=sha(after_file))
    atomic_json(job/'FULL_RETENTION_ADMISSION.json',result)
    return result


def actual_policy(job,record,lock_sha):
    if record.get('source_lock_sha256')!=lock_sha or record.get('profile_kind')!='canonical-full-gui-a2' or record.get('private_android_inputs') is not False:
        raise ValueError('exact reviewed public full producer source scope required')
    for key in ('public_input_acquisition_verified','retention_preflight_verified','all_public_source_tool_wheel_before_after_verified','actual_forge_submitted','compiler_termination_verified'):
        if record.get(key) is not True:raise ValueError('actual source/producer/ownership evidence required')
    rh=record.get('recipe_hash','')
    if not re.fullmatch('[a-f0-9]{64}',rh):raise ValueError('actual full producer recipe required')
    root=job/'ram/forge'/rh
    if root.is_symlink() or not root.is_dir():raise ValueError('real owned producer output required')
    outputs=[];seen=set()
    def native_path(name):
        if not isinstance(name,str) or not name.startswith('native-artifacts/out/') or any(x in ('','.', '..') for x in name.split('/')) or any(x in name for x in ('android-overlay','android-system','android-vendor','.private')):raise ValueError('canonical explicit public native path required')
        path=root/name
        path.resolve().relative_to(root.resolve())
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('native output aliases refused')
        return path
    def add(name,kind,expected=None):
        path=root/name;path.resolve().relative_to(root.resolve())
        if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents):raise ValueError('regular real output and ancestor paths required')
        row={'path':name,'kind':kind,'bytes':path.stat().st_size,'sha256':sha(path)}
        if expected is not None and (row['sha256']!=expected['sha256'] or row['bytes']!=expected['bytes']):raise ValueError('actual native output identity drift')
        if name in seen:raise ValueError('duplicate explicit native output')
        seen.add(name);outputs.append(row)
    for name in EVIDENCE:
        if (root/name).is_file():add(name,'public-producer-evidence')
    image_witness=root/'OWNED_CONTAINER_IMAGE.json'
    if image_witness.is_file():
        for row in json.loads(image_witness.read_text()).get('owned_container_images',[]):
            name=row['raw_inspect']['path']
            if not re.fullmatch('owned-container-image-[a-f0-9]{32}\.json',name):raise ValueError('actual owned Docker inspect filename required')
            add(name,'public-producer-evidence',row['raw_inspect'])
    metadata=root/'FULL_PHONE_METADATA/MANIFEST.json'
    if metadata.is_file():
        add('FULL_PHONE_METADATA/MANIFEST.json','public-producer-evidence')
        for row in json.loads(metadata.read_text())['outputs']:
            if not row['path'].startswith('FULL_PHONE_METADATA/') or len(row['path'].split('/'))!=2:raise ValueError('fixed actual metadata layout required')
            add(row['path'],'public-producer-evidence',row)
    result_path=root/'GN_RESULT.json'
    if not result_path.is_file():result_path=root/'NATIVE_LIBRARIES_RESULT.json'
    if result_path.is_file():
        result=json.loads(result_path.read_text())
        if result.get('source_inventory_sha256')!=record.get('actual_gn_inputs_sha256') or result.get('runtime') or result.get('whole_image_producer_admission') or result.get('complete_gui_phone'):
            raise ValueError('real source-bound native result without invented whole-phone acceptance required')
        phases=result.get('build_phases',[])
        compiled=any(p.get('phase')=='libc-utils-loader' and p.get('exit_code')==0 for p in phases)
        for row in result.get('native_libraries',[]):
            name=row['path']
            if not compiled or not name.startswith('native-artifacts/out/') or any(part in name for part in ('android-overlay','android-system','android-vendor','.private')):
                raise ValueError('genuine public native target phase and scope required')
            path=native_path(name)
            with path.open('rb') as source:header=source.read(64)
            if len(header)!=64 or header[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',header,18)[0]!=183 or struct.unpack_from('<H',header,16)[0] not in (2,3):
                raise ValueError('actual linked AArch64 ELF required')
            add(name,'native-elf',row)
        images=result.get('native_images',[])
        if len({row.get('partition') for row in images})!=len(images):raise ValueError('duplicate native image partitions refused')
        if result.get('native_image_built') is True and {row.get('partition') for row in images}!={'system','vendor','sys_prod','chip_prod'}:raise ValueError('claimed four images require actual four partitions')
        for row in images:
            name=row['path'];partition=row.get('partition')
            if partition not in ('system','vendor','sys_prod','chip_prod') or not name.startswith('native-artifacts/out/') or not name.endswith('/images/'+partition+'.img'):
                raise ValueError('explicit four public native image names required')
            if not any(p.get('phase')=='native-images' and p.get('exit_code')==0 for p in phases):raise ValueError('genuine successful native images phase required')
            with native_path(name).open('rb') as image:image.seek(1080);magic=image.read(2)
            if magic!=b'\x53\xef':raise ValueError('actual native ext4 image required')
            add(name,'native-image',row)
    if not outputs:raise ValueError('no actual explicit evidence to retain')
    return root,{'schema':'remeizu.public-native-output-policy.v1','plaintext_scope':'public-source-native-build-only',
                 'private_inputs_admitted':False,'source_lock_sha256':lock_sha,'outputs':outputs,
                 'profile_kind':'canonical-full-gui-a2','original_requested_parts':375,'actual_selected_parts':366,
                 'whole_phone_or_runtime_claimed':False}

def main():
    from run_full_phone import checked_job
    checked_job(os.environ)
    if os.environ.get('GITHUB_REF')!='refs/heads/codex/free-full375-20261010' or os.environ.get('GITHUB_REPOSITORY')!='ReMeizu/build-infra' or os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise ValueError('exact public full producer retention branch required')
    run=os.environ['GITHUB_RUN_ID'];job=Path(os.environ['RUNNER_TEMP'])/('full-phone-public-'+run)
    lock_sha=sha(HERE/'full_phone_public_inputs.lock.a1.json')
    if lock_sha!=APPROVED_LOCK_SHA:raise ValueError('exact reviewed full lock required')
    record=None
    for path in (job/'PUBLIC_RESULT.json',job/'INFLIGHT_FULL_RESULT.json'):
        if path.is_symlink() or not path.is_file() or path.stat().st_size>65536:continue
        try:candidate=json.loads(path.read_text())
        except (ValueError,OSError):continue
        if candidate.get('schema')=='remeizu.canonical-full-phone-public-run.v1' and candidate.get('run_id')==run and candidate.get('source_lock_sha256')==lock_sha:record=candidate;break
    if record is None:raise ValueError('complete bound full attempt snapshot required')
    if record['run_id']!=run:raise ValueError('actual run retention binding required')
    if sha(FREE/'encrypted_native_retention.py')!=HELPER_SHA:raise ValueError('exact tested crypto helper required')
    record=recover_admission(job,record,lock_sha)
    if record.get('actual_forge_submitted'):
        from producer_metadata import preserve
        preserve(job,job/'ram/forge'/record['recipe_hash'],record)
    root,policy=(setup_policy(job,record,lock_sha) if record.get('retention_scope')=='SETUP_FAILED' else actual_policy(job,record,lock_sha))
    from original_resource_snapshot import snapshot
    resources=snapshot(job/'ram')
    if resources['available_bytes']<2*1024**3 or resources['tmpfs_free_bytes']<cipher_upper_bound(policy):raise ValueError('actual complete cipher/keyring/manifest capacity required')
    policy_file=job/'ram/FULL_NATIVE_OUTPUT_POLICY.json';policy_file.write_text(json.dumps(policy,sort_keys=True,indent=2)+'\n')
    output=job/'ram/retention';output.mkdir()
    manifest=seal(root,policy_file,sha(policy_file),FREE/'native-retention-recipient.public.asc',RECIPIENT,output,512*1024**2)
    receipt=publish_cipher(output,manifest,'native-public-'+run,dict(os.environ,GH_REPO='ReMeizu/build-infra'))
    receipt.update(profile_kind='canonical-full-gui-a2',original_requested_parts=375,actual_selected_parts=366,whole_phone_or_runtime_claimed=False)
    (job/'FULL_CIPHER_RETENTION.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,sort_keys=True),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
