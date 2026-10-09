#!/usr/bin/env python3
"""Independent bounded readonly source/tool witness after stopped compilation."""
import argparse
import json
from pathlib import Path
from acquire import sha,verify_all
from finish_attempt import atomic_json

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--gn-sha256',required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();gn=a.root/'GN_INPUTS.json'
if sha(gn)!=a.gn_sha256:raise ValueError('original source inventory changed')
inputs=json.loads(gn.read_text());verify_all(a.root,inputs)
for row in inputs.get('uninitialized_gitlinks',[]):
 node=a.root/'native-source-input'/row['path']
 if node.is_symlink() or not node.is_dir() or list(node.iterdir()):raise ValueError('original empty gitlink changed')
if sha(gn)!=a.gn_sha256:raise ValueError('source inventory changed during witness')
proof={'schema':'remeizu.free-native-inputs-after.v1','gn_inputs_sha256':a.gn_sha256,
       'all_source_tool_wheel_inventory_pass':True,'source_projects':len(inputs['projects']),'source_files':len(inputs['source_files']),
       'full375_phone':False,'runtime':False}
atomic_json(a.output,proof)
