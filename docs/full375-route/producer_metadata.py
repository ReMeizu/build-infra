"""Preserve actual owned public producer inputs/identity inside ciphertext."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from finish_attempt import atomic_json

PREFIX='FULL_PHONE_METADATA'
TAG_SCHEMA='remeizu.full-phone-actual-image-tag-bindings.v1'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024**2),b''):h.update(block)
    return h.hexdigest()

def stream(path):return {'path':path.name,'bytes':path.stat().st_size,'sha256':sha(path)}

def before_launch(job,forge,model,controller,image_id):
    folder=job/'ram/producer-identity';folder.mkdir(exist_ok=False)
    (folder/'FORGE_NORMALIZED_RECIPE.json').write_text(model.canonical_json()+'\n')
    atomic_json(folder/'CONTROLLER_PROVENANCE.json',forge.current_source_provenance(controller))
    setup=json.loads((job/'ram/setup-diagnostics/SETUP_COMMANDS.json').read_text())
    row=setup['commands'][-1]
    if row['phase']!='image-inspect-prelaunch' or row['exit_code']!=0 or row['owned_child_reaped'] is not True:raise ValueError('actual prelaunch image inspection required')
    stdout=job/'ram/setup-diagnostics'/row['stdout']['path']
    if sha(stdout)!=row['stdout']['sha256'] or stdout.read_text().strip()!=image_id:raise ValueError('prelaunch raw image ID differs')
    atomic_json(folder/'IMAGE_TAG_BINDINGS.json',{'schema':TAG_SCHEMA,'expected_tag':model.image_tag,'expected_image_id':image_id,'prelaunch':dict(row,actual_image_id=image_id)})

def after_launch(job,tag,image_id):
    folder=job/'ram/producer-identity';argv=['docker','image','inspect',tag,'--format','{{.Id}}']
    out=folder/'image-inspect-postlaunch.stdout';err=folder/'image-inspect-postlaunch.stderr'
    with out.open('xb') as stdout,err.open('xb') as stderr:
        result=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=10)
    row={'phase':'image-inspect-postlaunch','argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),
         'started':True,'completed':True,'owned_child_reaped':True,'exit_code':result.returncode,'timed_out':False,'interrupted_signal':0,
         'stdout':stream(out),'stderr':stream(err),'actual_image_id':out.read_text().strip()}
    path=folder/'IMAGE_TAG_BINDINGS.json';data=json.loads(path.read_text());data['postlaunch']=row;atomic_json(path,data)
    if result.returncode!=0 or row['actual_image_id']!=image_id or data['expected_image_id']!=image_id or data['expected_tag']!=tag:raise ValueError('actual postlaunch image tag binding differs')
    return data

def preserve(job,actual,record):
    """Copy only fixed actual records; absent records remain explicitly absent."""
    original=job/'public-inputs/original';controller=job/'controller';identity=job/'ram/producer-identity'
    sources={
        'PUBLIC_RESULT.json':job/'PUBLIC_RESULT.json',
        'INFLIGHT_RESULT.json':job/'INFLIGHT_FULL_RESULT.json',
        'RETENTION_ADMISSION.json':job/'FULL_RETENTION_ADMISSION.json',
        'RECIPE.json':job/'recipe.json',
        'ACQUIRED_GN_INPUTS.json':original/'GN_INPUTS.json',
        'RUNTIME_GN_INPUTS.json':controller/'GN_INPUTS.json',
        'WORKER.py':controller/'native_gn_worker.py',
        'CANONICAL_COVERAGE.json':original/'canonical_full_phone_coverage.json',
        'RUNTIME_CORE_NONPRODUCTION_SCOPE.json':original/'runtime_core_nonproduction_scope.json',
        'CANONICAL_SELECTOR.json':original/'inputs/canonical-full-phone.json',
        'PUBLIC_INPUTS_AFTER.json':job/'ram/PUBLIC_INPUTS_AFTER.json',
        'SETUP_COMMANDS.json':job/'ram/setup-diagnostics/SETUP_COMMANDS.json',
    }
    for name in ('FORGE_NORMALIZED_RECIPE.json','CONTROLLER_PROVENANCE.json','IMAGE_TAG_BINDINGS.json'):
        sources[name]=identity/name
    setup=sources['SETUP_COMMANDS.json']
    if setup.is_file():
        for row in json.loads(setup.read_text())['commands']:
            if row['phase'] not in ('docker-build','image-inspect','image-health','image-inspect-prelaunch'):raise ValueError('only original actual setup phases admitted')
            for kind in ('stdout','stderr'):
                name=row['phase']+'.'+kind
                if row[kind]['path']!=name:raise ValueError('fixed actual setup log names required')
                path=job/'ram/setup-diagnostics'/name
                if sha(path)!=row[kind]['sha256'] or path.stat().st_size!=row[kind]['bytes']:raise ValueError('actual setup log body drift')
                sources[name]=path
    for kind in ('stdout','stderr'):
        name='image-inspect-postlaunch.'+kind;sources[name]=identity/name
    available={name:path for name,path in sources.items() if path.is_file()}
    needed=sum(path.stat().st_size for path in available.values())+16*1024**2
    if shutil.disk_usage(actual).free<needed:raise ValueError('actual RAM reserve for complete owned metadata refused')
    target=actual/PREFIX
    if target.is_symlink():raise ValueError('owned real metadata directory required')
    target.mkdir(exist_ok=True);outputs=[]
    for name,path in sorted(available.items()):
        path.resolve().relative_to(job.resolve())
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('actual owned regular metadata and ancestors required')
        digest=sha(path);dest=target/name
        if dest.exists():
            if dest.is_symlink() or sha(dest)!=digest or dest.stat().st_size!=path.stat().st_size:raise ValueError('original preserved metadata identity differs')
        else:
            with path.open('rb') as source,dest.open('xb') as output:shutil.copyfileobj(source,output,1024**2)
        if sha(dest)!=digest:raise ValueError('actual metadata full copy readback differs')
        outputs.append({'path':PREFIX+'/'+name,'bytes':dest.stat().st_size,'sha256':digest})
    manifest={'schema':'remeizu.full-phone-sealed-actual-metadata.v1','run_id':record['run_id'],'source_lock_sha256':record['source_lock_sha256'],
              'retention_scope':record.get('retention_scope','NATIVE_FORGE'),'outputs':outputs,'missing_actual_records':sorted(set(sources)-set(available)),
              'metadata_created_from_actual_owned_files_only':True,'runtime':False}
    atomic_json(target/'MANIFEST.json',manifest)
    outputs.append({'path':PREFIX+'/MANIFEST.json','bytes':(target/'MANIFEST.json').stat().st_size,'sha256':sha(target/'MANIFEST.json')})
    return outputs
