"""Static Docker setup phases, actual RAM logs; never print captured text."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from finish_attempt import atomic_json
from acquire import sha

PHASES={'docker-build','image-inspect','image-health','image-inspect-prelaunch'}
HEALTH_CODE="import json,os,pathlib; p=pathlib.Path('/workspace/out/health');p.write_text('actual writable RAM');print(json.dumps({'uid':os.getuid(),'glibc':os.confstr('CS_GNU_LIBC_VERSION'),'writable_ram':p.read_text()=='actual writable RAM'}))"

class SetupCommandError(ValueError):
    def __init__(self,phase,code):
        super().__init__('actual Docker setup command failed')
        self.phase,self.exit_code=phase,code

def execute(phase,argv,ram,record,timeout=1200,cancelled=None):
    if phase not in PHASES or str(argv[0])!='docker':raise ValueError('fixed actual Docker setup phase required')
    folder=ram/'setup-diagnostics';folder.mkdir(exist_ok=True)
    path=folder/'SETUP_COMMANDS.json'
    manifest=json.loads(path.read_text()) if path.exists() else {'schema':'remeizu.free-native-setup-commands.v1',
        'run_id':record['run_id'],'source_lock_sha256':record['source_lock_sha256'],'commands':[]}
    out,err=folder/(phase+'.stdout'),folder/(phase+'.stderr')
    command=[str(x) for x in argv]
    timed_out=False;interrupted=0
    with out.open('xb') as stdout,err.open('xb') as stderr:
        proc=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
        deadline=time.monotonic()+timeout
        while True:
            interrupted=cancelled[0] if cancelled else 0
            timed_out=time.monotonic()>=deadline
            if interrupted or timed_out:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                code=proc.wait(timeout=5)
                break
            try:
                code=proc.wait(timeout=min(0.25,max(0.001,deadline-time.monotonic())))
                break
            except subprocess.TimeoutExpired:pass
    row={'phase':phase,'argv':command,'argv_sha256':hashlib.sha256(json.dumps(command,separators=(',',':')).encode()).hexdigest(),
         'started':True,'completed':True,'exit_code':code,'owned_child_reaped':proc.poll() is not None,'timed_out':timed_out,'interrupted_signal':interrupted,
         'stdout':{'path':out.name,'bytes':out.stat().st_size,'sha256':sha(out)},
         'stderr':{'path':err.name,'bytes':err.stat().st_size,'sha256':sha(err)}}
    manifest['commands'].append(row);atomic_json(path,manifest)
    record.update(setup_commands_termination_verified=all(x['owned_child_reaped'] for x in manifest['commands']),
                  setup_diagnostics_sha256=sha(path))
    if code!=0 or timed_out or interrupted:
        record.update(setup_failure_phase=phase,retention_scope='SETUP_FAILED')
        raise SetupCommandError(phase,code)
    if phase=='docker-build':data=b''
    else:
        with out.open('rb') as stream:data=stream.read(65537)
    if len(data)>65536:raise ValueError('actual setup metadata output exceeds bounded parse')
    return subprocess.CompletedProcess(command,code,data,b'')
