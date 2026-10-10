#!/usr/bin/env python3
"""Lossless bounded source inventory shards; never certify image/cohort readiness."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re

SCHEMA='remeizu.full375-public-source-inventory-index.v1'

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def validate_rows(rows):
    prior=None
    for row in rows:
        path=row.get('path');p=PurePosixPath(path or '')
        if not path or p.is_absolute() or '..' in p.parts or '.git' in p.parts or str(p)!=path or p.parts[0]=='out':raise ValueError('canonical immutable source member required')
        if prior is not None and path<=prior:raise ValueError('source inventory duplicate or order drift')
        prior=path
        mode=row.get('mode')
        if not isinstance(mode,str) or not re.fullmatch(r'0o[0-7]{3,4}',mode):raise ValueError('exact source-file mode required')
        if 'symlink' in row:
            if set(row)!={'path','mode','symlink'} or int(mode,8)!=0o777:raise ValueError('exact original symlink source schema required')
            target=row['symlink'];logical=posixpath.normpath(posixpath.join(str(p.parent),target))
            if not isinstance(target,str) or not target or PurePosixPath(target).is_absolute() or logical=='..' or logical.startswith('../'):raise ValueError('source symlink escapes immutable lower')
        elif set(row)!={'path','mode','bytes','sha256'} or not isinstance(row['bytes'],int) or isinstance(row['bytes'],bool) or row['bytes']<0 or not re.fullmatch('[a-f0-9]{64}',row['sha256']):raise ValueError('exact source regular-file identity required')
    return rows

def write_shards(rows,destination,max_bytes=8*1024**2):
    validate_rows(rows);destination=Path(destination)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh owned public source-shard directory required')
    if not 128<=max_bytes<=16*1024**2:raise ValueError('bounded source-shard byte cap required')
    destination.mkdir(parents=True);shards=[];group=[];size=2
    def flush():
        nonlocal group,size
        if not group:return
        body=canonical(group)+b'\n';name='source-files-'+str(len(shards)).zfill(5)+'.json';(destination/name).write_bytes(body);shards.append({'path':name,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'source_files':len(group)});group=[];size=2
    for row in rows:
        encoded=canonical(row)
        if len(encoded)+3>max_bytes:raise ValueError('one declared source row exceeds bounded shard')
        needed=len(encoded)+(1 if group else 0)
        if group and size+needed+1>max_bytes:flush();needed=len(encoded)
        group.append(row);size+=needed
    flush()
    index={'schema':SCHEMA,'shards':shards,'source_files':len(rows),'source_bytes':sum(r.get('bytes',0) for r in rows),'lower_inventory_sha256':hashlib.sha256(canonical(rows)).hexdigest(),'source_acquisition_verified':False,'original375_source_bindings_verified':False,'full375_images':False,'target_compilation':False};(destination/'INDEX.json').write_bytes(canonical(index)+b'\n');return index

def read_shards(destination,index):
    destination=Path(destination)
    if index.get('schema')!=SCHEMA or index.get('source_acquisition_verified') is not False or index.get('original375_source_bindings_verified') is not False:raise ValueError('inventory format is not image/cohort admission')
    rows=[]
    for position,part in enumerate(index['shards']):
        expected='source-files-'+str(position).zfill(5)+'.json'
        if part.get('path')!=expected or part['bytes']>16*1024**2:raise ValueError('canonical bounded shard required')
        path=destination/expected
        if path.is_symlink() or not path.is_file():raise ValueError('regular bound source shard required')
        body=path.read_bytes()
        if len(body)!=part['bytes'] or hashlib.sha256(body).hexdigest()!=part['sha256']:raise ValueError('source-shard bytes differ')
        value=json.loads(body)
        if len(value)!=part['source_files'] or body!=canonical(value)+b'\n':raise ValueError('source-shard canonical content differs')
        rows.extend(value)
    validate_rows(rows)
    if len(rows)!=index['source_files'] or sum(r.get('bytes',0) for r in rows)!=index['source_bytes'] or hashlib.sha256(canonical(rows)).hexdigest()!=index['lower_inventory_sha256']:raise ValueError('joined exact source inventory differs')
    return rows
