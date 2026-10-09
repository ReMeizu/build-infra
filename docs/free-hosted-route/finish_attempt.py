"""Bounded owned-process cancellation and independent readonly input witness."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

HERE=Path(__file__).resolve().parent

def atomic_json(path,value):
    pending=path.with_name('.'+path.name+'.pending.'+str(os.getpid()))
    with pending.open('x') as out:
        json.dump(value,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    pending.replace(path)

def run_owned(argv,env,timeout,ram,cancelled,on_started=None):
    """SIGINT gives unchanged Forge its real owned-container cleanup window."""
    deadline=time.monotonic()+timeout
    with (ram/'forge-controller.stdout').open('wb') as stdout,(ram/'forge-controller.stderr').open('wb') as stderr:
        proc=subprocess.Popen(argv,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        if on_started:on_started()
        reason=None
        while proc.poll() is None:
            if cancelled[0] or time.monotonic()>=deadline:
                reason='signal' if cancelled[0] else 'timeout'
                proc.send_signal(signal.SIGINT)
                try:proc.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
                break
            time.sleep(0.2)
    return {'returncode':proc.returncode,'owned_launcher_reaped':proc.poll() is not None,'termination_reason':reason}

def closed_containers(forge,actual,recipe_hash):
    rows=[]
    metadata=actual/forge.CONTAINER_METADATA_DIR
    for path in sorted(metadata.glob('*.json')):
        if path.is_symlink() or path.stat().st_size>16384:raise ValueError('invalid owned Forge state')
        state=json.loads(path.read_text());inv=state.get('invocation','')
        expected='forge-eph-'+recipe_hash[:12]+'-'+inv[:12]
        if not re.fullmatch('[a-f0-9]{32}',inv) or path.name!=inv+'.json' or state.get('recipe_hash')!=recipe_hash or state.get('container_name')!=expected:
            raise ValueError('owned Forge invocation binding differs')
        before=dict(state)
        if state.get('cleanup_needed',True):
            # Reuse the unchanged launcher's label/full-ID ownership guard.
            # Preserve its original state JSON and FAILURE; independent proof
            # never rewrites producer history as a successful run.
            cleanup=forge._cleanup_owned_container(state)
        else:cleanup={'cleanup_needed':False,'cleanup_reason':'actual launcher reports attached container closed'}
        cid=state.get('container_id')
        if not cid:
            cidpath=metadata/(inv+'.cid')
            if cidpath.is_file() and not cidpath.is_symlink():cid=cidpath.read_text().strip()
        if cid and re.fullmatch('[a-f0-9]{64}',cid):
            inspected=subprocess.run(['docker','container','inspect',cid],capture_output=True,text=True,timeout=10)
            absent=inspected.returncode!=0 and ('No such object' in inspected.stderr or 'No such container' in inspected.stderr)
            if not absent:
                raise ValueError('actual known owned container still exists or closure unresolved')
            closed=True
        else:
            closed=not cleanup['cleanup_needed'] and state.get('create_issued') is False and state.get('client_reaped') is True
            if not closed:raise ValueError('possible late owned Docker creation unresolved')
        if json.loads(path.read_text())!=before:raise ValueError('original producer state changed during independent closure')
        rows.append({'invocation':inv,'known_container_absent':bool(cid),'owned_closed':closed})
    proof={'schema':'remeizu.free-native-owned-termination.v1','recipe_hash':recipe_hash,
           'all_owned_container_closure_pass':True,'owned_states':rows,
           'no_state_means_launcher_did_not_reach_create':not rows,'producer_history_rewritten':False}
    if actual.is_dir():atomic_json(actual/'OWNED_TERMINATION.json',proof)
    return proof

def verify_inputs(original,expected_gn_sha,ram,timeout=300):
    output=ram/'PUBLIC_INPUTS_AFTER.json'
    proc=subprocess.run([os.sys.executable,'-B',str(HERE/'verify_inputs_after.py'),'--root',str(original),
        '--gn-sha256',expected_gn_sha,'--output',str(output)],capture_output=True,timeout=timeout,start_new_session=True)
    if proc.returncode!=0 or not output.is_file():raise ValueError('actual readonly input after-witness failed')
    proof=json.loads(output.read_text())
    if proof.get('all_source_tool_wheel_inventory_pass') is not True or proof['gn_inputs_sha256']!=expected_gn_sha:
        raise ValueError('independent actual input witness differs')
    return proof
