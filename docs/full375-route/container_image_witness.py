"""Attest only the unchanged Forge's actual owned container image IDs."""
import hashlib
import json
import re
import signal
import subprocess
import threading
from pathlib import Path
from finish_attempt import atomic_json

SCHEMA='remeizu.full-phone-owned-container-image.v1'
WRAPPER='OWNED_CONTAINER_IMAGE.json'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def attest(state,data,recipe_hash,image_id,image_tag):
    invocation=state.get('invocation','');cid=state.get('container_id','')
    expected='forge-eph-'+recipe_hash[:12]+'-'+invocation[:12]
    if not re.fullmatch('[a-f0-9]{32}',invocation) or not re.fullmatch('[a-f0-9]{64}',cid) or state.get('recipe_hash')!=recipe_hash or state.get('container_name')!=expected:raise ValueError('exact original owned Forge state required')
    if not isinstance(data,list) or len(data)!=1:raise ValueError('one actual owned Docker inspect required')
    container=data[0];labels=container.get('Config',{}).get('Labels',{})
    if container.get('Id')!=cid or container.get('Name')!='/'+expected or labels.get('androidforge.invocation')!=invocation or labels.get('androidforge.recipe_sha256')!=recipe_hash:raise ValueError('actual full CID/name/Forge ownership differs')
    if not re.fullmatch('sha256:[a-f0-9]{64}',image_id) or container.get('Image')!=image_id or container.get('Config',{}).get('Image')!=image_tag:raise ValueError('actual owned immutable image or requested tag differs')
    return {'invocation':invocation,'container_id':cid,'container_name':expected,'actual_image_id':container['Image'],
            'requested_image_tag':image_tag,'ownership_labels':{'androidforge.invocation':invocation,'androidforge.recipe_sha256':recipe_hash}}

class ImageObserver:
    def __init__(self,forge,actual,recipe_hash,image_id,image_tag,cancelled):
        self.forge,self.actual,self.recipe_hash,self.image_id,self.cancelled=forge,actual,recipe_hash,image_id,cancelled
        self.image_tag=image_tag
        self.stop=threading.Event();self.rows={};self.error=None
        self.thread=threading.Thread(target=self.observe,name='owned-forge-image-witness',daemon=True)

    def start(self):self.thread.start()

    def observe(self):
        try:
            while not self.stop.is_set():
                metadata=self.actual/self.forge.CONTAINER_METADATA_DIR
                if metadata.is_symlink():raise ValueError('original owned metadata directory required')
                for path in sorted(metadata.glob('*.json')):
                    if path.is_symlink() or path.stat().st_size>16384:raise ValueError('actual owned state file required')
                    state=json.loads(path.read_text());inv=state.get('invocation','')
                    if not re.fullmatch('[a-f0-9]{32}',inv) or path.name!=inv+'.json' or state.get('recipe_hash')!=self.recipe_hash:raise ValueError('exact owned image observation scope required')
                    if inv in self.rows:continue
                    cid=state.get('container_id')
                    cidfile=metadata/(inv+'.cid')
                    if not cid and cidfile.is_file() and not cidfile.is_symlink() and cidfile.stat().st_size<=65:cid=cidfile.read_text().strip()
                    if not cid:continue
                    if not re.fullmatch('[a-f0-9]{64}',cid):raise ValueError('full owned container ID required')
                    result=subprocess.run(['docker','container','inspect',cid],capture_output=True,timeout=5)
                    if result.returncode:continue  # Creation/closure races are not positive proof.
                    if len(result.stdout)>4*1024**2:raise ValueError('bounded actual Docker inspect required')
                    state=dict(state,container_id=cid)
                    row=attest(state,json.loads(result.stdout),self.recipe_hash,self.image_id,self.image_tag)
                    raw=self.actual/('owned-container-image-'+inv+'.json')
                    with raw.open('xb') as output:output.write(result.stdout)
                    row['raw_inspect']={'path':raw.name,'bytes':raw.stat().st_size,'sha256':sha(raw)}
                    self.rows[inv]=row
                self.stop.wait(.2)
        except Exception as error:
            self.error=type(error).__name__
            self.cancelled[0]=signal.SIGTERM

    def finish(self):
        self.stop.set();self.thread.join(timeout=7)
        proof={'schema':SCHEMA,'recipe_hash':self.recipe_hash,'expected_image_id':self.image_id,'expected_tag':self.image_tag,
               'owned_container_images':list(self.rows.values()),'observer_termination_verified':not self.thread.is_alive(),
               'all_observed_owned_images_verified':bool(self.rows) and self.error is None and not self.thread.is_alive(),
               'error_type':self.error,'missing_observation_is_not_image_proof':True}
        if self.actual.is_dir():atomic_json(self.actual/WRAPPER,proof)
        return proof
