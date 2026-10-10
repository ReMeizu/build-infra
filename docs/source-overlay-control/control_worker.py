"""Literal source-filesystem fixture only: never run GN/Ninja/Clang."""
import hashlib
import json
import os
from pathlib import Path
import ram_overlay_protocol as model

ram=Path('/workspace/ram')
plan=json.loads(Path('/workspace/src/PLAN.json').read_text())
lower=ram/'lower';merged=ram/'merged'
before=model.verify_lower(lower,plan['source_rows'],plan['source_inventory_sha256'])
if model.filesystem(merged)!='overlay' or model.filesystem(ram/'upper')!='tmpfs' or model.filesystem(ram/'work')!='tmpfs':raise ValueError('actual recursively bound overlay/RAM directories required')
if os.getuid()!=plan['uid'] or os.getgid()!=plan['gid']:raise ValueError('actual non-root runner identity required')
(merged/'source.txt').write_text('source copy-up fixture only\n')
(merged/'generated').mkdir();(merged/'generated/probe.txt').write_text('known literal output fixture only\n')
artifact=ram/plan['artifact_root_relative']
artifact.resolve().relative_to(ram.resolve())
row=model.retain_ram_file(ram/'upper/generated/probe.txt',artifact,'retained/probe.txt',model.sha(ram/'upper/generated/probe.txt'),ram)
after=model.verify_lower(lower,plan['source_rows'],plan['source_inventory_sha256'])
proof={'schema':'remeizu.cloud-source-overlay-worker-control.v1','actual_uid':os.getuid(),'actual_gid':os.getgid(),'source_before':before,'source_after':after,'actual_overlay_type':model.filesystem(merged),'actual_upper_type':model.filesystem(ram/'upper'),'actual_work_type':model.filesystem(ram/'work'),'same_RAM_artifact':row,'target_compilation':False,'private_android_inputs':False,'full375_images':False,'full375_fit_proven':False}
(artifact/'SOURCE_WORKER_PROOF.json').write_text(json.dumps(proof,sort_keys=True,indent=2)+'\n')
print('SOURCE_OVERLAY_WORKER_CONTROL_PASS',flush=True)
