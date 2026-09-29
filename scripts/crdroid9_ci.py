#!/usr/bin/env python3
"""One bounded CI attempt. Publish authenticated ciphertext, never vendor plaintext."""
import base64,hashlib,io,json,os,shutil,signal,subprocess,sys,time,traceback,urllib.request
from pathlib import Path
from crdroid9_checkpoint import encrypt

here=Path(__file__).resolve().parents[1]
private=Path('/home/circleci/m6-private')
mount=Path('/mnt/forge-circle-m6')
artifacts=here/'artifacts'
artifacts.mkdir(exist_ok=True)
status={'rom_complete':False,'checkpoint_saved':False,'build_exit':1}
control=json.loads((private/'control.json').read_text())
key=bytes.fromhex(control['checkpoint_key'])
assert len(key)==32
os.environ['GIT_OPTIONAL_LOCKS']='0'
log_path=private/'build.log'
with log_path.open('w') as log:
    try:
        url=control['input_url']
        assert url.startswith('https://release-assets.githubusercontent.com/')
        archive=private/'inputs.tar.gz'
        urllib.request.urlretrieve(url,archive)
        expected='5b28402383ac9255fb2809b094fa8c837a18ae53db2efd2cca98dc0d367594e8'
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
        subprocess.run([sys.executable,str(here/'scripts/crdroid9_prepare.py'),str(archive),expected],check=True,stdout=log,stderr=subprocess.STDOUT)
        subprocess.run(['sudo','mkdir','-p',str(mount)],check=True)
        disk=Path('/home/circleci/forge-circle-m6.ext4')
        assert not disk.exists()
        subprocess.run(['truncate','-s','50G',str(disk)],check=True)
        subprocess.run(['mkfs.ext4','-F','-m','0',str(disk)],check=True,stdout=log,stderr=subprocess.STDOUT)
        subprocess.run(['sudo','mount','-o','loop',str(disk),str(mount)],check=True)
        subprocess.run(['sudo','chown','circleci:circleci',str(mount)],check=True)
        image_id=subprocess.check_output(['docker','image','inspect','androidforge/build-env:android-9','--format','{{.Id}}'],text=True).strip()
        started=int(Path('/home/circleci/ci-start').read_text())
        budget=min(1800, max(60,2700-int(time.time()-started)-240))
        recipe={
            'image_tag':'androidforge/build-env:android-9','image_id':image_id,'build_env_key':'android-9',
            'source_mount_path':'/home/circleci/crdroid9-m6','execution_profile':'cloud-mounted',
            'scratch_mount_path':str(mount),'container_user':'1001:1001','output_dir_in_container':'/workspace/out',
            'idempotency_key':'crdroid-pie-m6-circle-'+os.environ['CIRCLE_BUILD_NUM'],'timeout_seconds':budget,
            'env':{'FORGE_ROM_BRANCH':'lineage-16.0','FORGE_DEVICE':'meizu_m6','FORGE_OFFLINE_SOURCE_SNAPSHOT':'1','GIT_OPTIONAL_LOCKS':'0'},
            'command':['bash','/workspace/src/.forge/run.sh'],
            'required_artifacts':['rom-version.txt','boot.img','rom.zip','SHA256SUMS'],
        }
        if control.get('resume_url'):
            from crdroid9_resume import download_resume
            download_resume(control,private,mount,key,log)
        recipe_path=mount/'recipe.json'
        recipe_path.write_text(json.dumps(recipe,indent=2)+'\n')
        env=['FORGE_EPHEMERAL_BASE='+str(mount/'evidence'),'GIT_OPTIONAL_LOCKS=0',
             'GIT_CONFIG_COUNT=1','GIT_CONFIG_KEY_0=safe.directory','GIT_CONFIG_VALUE_0=*',
             'FORGE_SOURCE_PROOF_PATH='+str(mount/'source-proof.json'),
             'FORGE_RESUME_DIR='+str(mount/'resume'), 'FORGE_CURRENT_RECIPE='+str(recipe_path)]
        process=subprocess.Popen(['sudo','env',*env,'/usr/bin/python3',str(here/'scripts/crdroid9_forge.py'),'--recipe',str(recipe_path),'--verbose'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        while process.poll() is None:
            free=shutil.disk_usage('/').free
            print(json.dumps({'phase':'forge','elapsed_seconds':int(time.time()-started),'free_gib':free//2**30,'log_bytes':log_path.stat().st_size}),flush=True)
            if free<20*2**30 or shutil.disk_usage(mount).free<3*2**30:
                os.killpg(process.pid,signal.SIGINT)
                try: process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    status['stop_reason']='cleanup-unresolved'
                    raise RuntimeError('Forge did not stop after disk guard; checkpoint refused')
                status['stop_reason']='disk-reserve'
                break
            log.flush()
            diagnostic=io.BytesIO()
            tail=b''
            for recent_path in [log_path,*sorted((mount/'evidence').glob('*/run.log'))]:
                with recent_path.open('rb') as recent:
                    recent.seek(max(0,recent_path.stat().st_size-5500))
                    tail+=recent.read()+b'\n'
            encrypt(io.BytesIO(tail),diagnostic,key)
            print('PRIVATE_DIAGNOSTIC '+base64.b64encode(diagnostic.getvalue()).decode(),flush=True)
            time.sleep(20)
        status.update(build_exit=process.returncode,rom_complete=process.returncode==0,image_id=image_id,container_budget_seconds=budget)
    except Exception:
        traceback.print_exc(file=log)

try:
    assert status.get('stop_reason')!='cleanup-unresolved'
    if mount.is_mount():
        from crdroid9_resume import require_stopped
        require_stopped(mount)
    tar=['sudo','tar','-I','zstd -T2 -1','-cf','-']
    if mount.is_mount(): tar+=['-C',str(mount),'.']
    tar+=['-C',str(private),'build.log']
    process=subprocess.Popen(tar,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    target=artifacts/'private-checkpoint.rmc'
    with target.open('wb') as out: encrypt(process.stdout,out,key)
    assert process.wait()==0
    h=hashlib.sha256()
    with target.open('rb') as f:
        while data:=f.read(1024*1024): h.update(data)
    status.update(checkpoint_saved=True,ciphertext_sha256=h.hexdigest(),ciphertext_bytes=target.stat().st_size)
except Exception as error:
    status['checkpoint_error']=type(error).__name__
(artifacts/'status.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(status),flush=True)
