"""Reject incomplete CPU/memory/disk measurements before accepting CI success."""
import json,sys
from pathlib import Path

def verify(folder):
    files=sorted(Path(folder).glob('run-*.json'))
    assert len(files)==3,'Exactly three complete samples required'
    for path in files:
        r=json.loads(path.read_text())
        for name,workers in [('cpu_single',1),('cpu_parallel',4),('memory',2)]:
            v=r[name]
            assert not v['errors'] and v['workers_completed']==v['workers']==workers,(path.name,name)
            assert v['aggregate_bytes_per_second']>0,(path.name,name)
        assert r['fio']['version']=='fio-3.39',path.name
        assert len(r['disks'])==1,path.name
        d=r['disks'][0]
        assert d['complete'] and d['prefill_complete'] and d['owned_payload_removed'] and d['direct_io'],path.name
        assert len(d['cases'])==6,path.name
        assert all(c['exit_code']==0 and c['fio_job_errors']==[0] for c in d['cases']),path.name
    return len(files)

if __name__=='__main__':
    print(f'{verify(sys.argv[1])} complete benchmark samples verified')
