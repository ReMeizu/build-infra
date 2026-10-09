"""Exact declared public LFS postcondition; never replace unknown source bytes."""
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
from diagnostics import PublicInputError
from make_j2_successor import safe


def sha(data):return hashlib.sha256(data).hexdigest()

def declaration(row):
    oid=row.get('material_sha256',row.get('object_sha256'))
    size=row.get('bytes',row.get('object_bytes'))
    pointer_sha=row.get('committed_pointer_sha256',row.get('pointer_sha256'))
    if not isinstance(oid,str) or not re.fullmatch('[a-f0-9]{64}',oid) or type(size) is not int or not 0<size<=8*1024**2 or not isinstance(pointer_sha,str) or not re.fullmatch('[a-f0-9]{64}',pointer_sha):
        raise PublicInputError('LFS_DECLARATION_MISMATCH',row.get('path'))
    return oid,size,pointer_sha

def pointer_identity(data,row):
    oid,size,pointer_sha=declaration(row)
    match=re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([1-9][0-9]*)\n',data)
    if sha(data)!=pointer_sha or not match or match[1].decode()!=oid or int(match[2])!=size or ('pointer_bytes' in row and len(data)!=row['pointer_bytes']):
        raise PublicInputError('LFS_POINTER_MISMATCH',row['path'])
    return oid,size

def git(checkout,argv,env):
    return subprocess.run(['git','-C',str(checkout),'-c','credential.helper=',*argv],env=env,capture_output=True,check=True,timeout=120).stdout

def pinned_identity(checkout,project,env):
    head=git(checkout,['rev-parse','HEAD'],env).decode().strip()
    tree=git(checkout,['rev-parse','HEAD^{tree}'],env).decode().strip()
    if head!=project['head'] or tree!=project['git_tree']:
        raise PublicInputError('LFS_GIT_IDENTITY_MISMATCH',project['path'])
    return head,tree

def smudge_process(argv,env,pointer,timeout=180):
    proc=subprocess.Popen(argv,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        stdout,stderr=proc.communicate(pointer,timeout=timeout)
    except subprocess.TimeoutExpired:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.communicate(timeout=5)
        raise
    return subprocess.CompletedProcess(argv,proc.returncode,stdout,stderr)

def materialize(checkout,project,env):
    rows=project.get('lfs_objects',[])
    if not rows:return []
    if git(checkout,['remote','get-url','origin'],env).decode().strip()!=project['url']:
        raise PublicInputError('LFS_GIT_IDENTITY_MISMATCH',project['path'])
    pinned_identity(checkout,project,env)
    receipts=[]
    for row in rows:
        relative=str(safe(row['path']));member=project['path']+'/'+relative
        pointer=git(checkout,['show',project['head']+':'+relative],env)
        oid,size=pointer_identity(pointer,row)
        path=checkout/relative
        path.resolve().relative_to(checkout.resolve())
        if not path.is_file() or path.is_symlink():raise PublicInputError('LFS_WORKING_MEMBER_MISMATCH',member)
        before=path.read_bytes()
        if len(before)==size and sha(before)==oid:
            receipts.append({'member':member,'state':'already_exact_material','bytes':size,'sha256':oid});continue
        if before!=pointer:raise PublicInputError('LFS_WORKING_MEMBER_MISMATCH',member,len(before),sha(before))
        mode=stat.S_IMODE(path.stat().st_mode)
        partial=path.with_name('.'+path.name+'.lfs-material.partial')
        if partial.exists() or partial.is_symlink():raise PublicInputError('LFS_PARTIAL_EXISTS',member)
        child_env=dict(env);child_env.pop('GIT_LFS_SKIP_SMUDGE',None)
        private_log=path.with_name('.'+path.name+'.lfs-smudge.private.log')
        endpoint=project['url'].removesuffix('.git')+'.git/info/lfs'
        proc=smudge_process(['git','-C',str(checkout),'-c','credential.helper=',
              '-c','lfs.url='+endpoint,'lfs','smudge','--',relative],
              child_env,pointer,timeout=180)
        private_log.write_bytes(proc.stderr)
        # This route has three immutable small objects (largest 4.2MB).
        # Actual git-lfs resolves the exact OID; no generic stream worker or
        # global configuration is introduced. Rejection preserves old bytes.
        if proc.returncode!=0 or len(proc.stdout)!=size or sha(proc.stdout)!=oid:
            raise PublicInputError('LFS_MATERIAL_MISMATCH',member)
        with partial.open('xb') as target:target.write(proc.stdout)
        if path.read_bytes()!=pointer:raise PublicInputError('LFS_WORKING_MEMBER_MISMATCH',member)
        pinned_identity(checkout,project,env)
        partial.chmod(mode);partial.replace(path)
        if path.stat().st_size!=size or sha(path.read_bytes())!=oid:raise PublicInputError('LFS_MATERIAL_MISMATCH',member)
        receipts.append({'member':member,'state':'explicit_declared_pointer_smudged','bytes':size,'sha256':oid,
                         'committed_pointer_sha256':sha(pointer),'head_tree_preserved':True})
    pinned_identity(checkout,project,env)
    return receipts
