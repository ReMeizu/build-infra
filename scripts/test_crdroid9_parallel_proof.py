#!/usr/bin/env python3
"""Compare complete Forge identities for serial and parallel snapshots on Linux."""
import os,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/forge'))
import forge_ephemeral_build as forge
from crdroid9_parallel_proof import install
os.environ['GIT_OPTIONAL_LOCKS']='0'
def git(path,*args):
    return subprocess.check_output(['git','-C',str(path),*args],stderr=subprocess.DEVNULL)
def repo(path):
    path.mkdir(parents=True,exist_ok=True)
    git(path,'init');git(path,'config','user.name','Proof test');git(path,'config','user.email','proof@localhost')
    (path/'tracked.txt').write_text('tracked\n');(path/'.gitignore').write_text('ignored\n')
    git(path,'add','.');git(path,'commit','-m','fixture')
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);repo(root)
    for name in ('a','b','c'):
        child=root/name;repo(child)
        (child/'ignored').write_bytes(b'ignored payload')
        (child/'untracked').write_bytes(b'untracked payload')
        (child/'link').symlink_to('untracked')
    (root/'.repo').mkdir();(root/'.repo/project.list').write_text('a\nb\nc\n')
    (root/'b/tracked.txt').write_text('modified tracked content\n')
    serial=install(forge,root)
    baseline=serial(root)
    parallel=forge._source_provenance_snapshot(root)
    assert parallel==baseline, (baseline,parallel)
    (root/'c/ignored').write_bytes(b'changed ignored payload')
    changed=forge._source_provenance_snapshot(root)
    assert changed==serial(root) and changed!=baseline
    # Both algorithms must reject index flags that could hide changed inputs.
    git(root/'a','update-index','--assume-unchanged','tracked.txt')
    for algorithm in (serial,forge._source_provenance_snapshot):
        try: algorithm(root)
        except RuntimeError: pass
        else: raise AssertionError('Unsafe Git index accepted')
print('PASS: serial/parallel identities match; dirty/ignored bytes and unsafe indexes retain checks')
