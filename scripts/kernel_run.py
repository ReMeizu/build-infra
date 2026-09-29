#!/usr/bin/env python3
"""Fetch pinned public inputs, build a new image, then compile solely via Forge.

The caller provisions a separate ext4/xfs scratch mount and performs budget
admission. This script never formats/mounts a disk, flashes or cleans old jobs.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'scripts'))
from kernel_forge import forge
from kernel_build import require, sha


def run(argv, **kwargs):
    return subprocess.run(list(map(str,argv)),check=True,timeout=kwargs.pop('timeout',900),**kwargs)


def output(argv):
    return run(argv,stdout=subprocess.PIPE,text=True).stdout.strip()


def extract(archive, destination):
    """Git archives only; reject traversal, special files and escaping links."""
    destination.mkdir()
    links = []
    with tarfile.open(archive,'r:gz') as stream:
        for member in stream:
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and '.git' not in name.parts, 'unsafe archive path')
            target = destination.joinpath(*name.parts)
            require(not target.exists() and not target.is_symlink(), 'duplicate archive member')
            if member.isdir():
                target.mkdir(parents=True,exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True,exist_ok=True)
                with stream.extractfile(member) as r, target.open('xb') as w:
                    shutil.copyfileobj(r,w)
                target.chmod(0o755 if member.mode&0o111 else 0o644)
            elif member.issym():
                resolved = posixpath.normpath(str(name.parent/member.linkname))
                require(not PurePosixPath(member.linkname).is_absolute() and resolved != '..' and not resolved.startswith('../'), 'escaping archive symlink')
                links.append((target,member.linkname))
            else:
                raise ValueError('special or hardlink archive member refused')
    for target,value in links:
        target.parent.mkdir(parents=True,exist_ok=True)
        require(not target.exists() and not target.is_symlink(), 'symlink overwrites input')
        target.symlink_to(value)
        require(target.resolve().is_relative_to(destination.resolve()), 'resolved link escapes source')


def fetch(parent, name, url, commit, expected_tree=None):
    repository = parent/(name+'.git')
    run(['git','init','--bare',repository])
    run(['git','-C',repository,'-c','credential.helper=','fetch','--depth=1','--no-tags',url,commit],timeout=600)
    require(output(['git','-C',repository,'rev-parse','FETCH_HEAD'])==commit,'fetched wrong commit')
    tree=output(['git','-C',repository,'rev-parse',commit+'^{tree}'])
    require(expected_tree is None or tree==expected_tree,'fetched wrong toolchain tree')
    archive=parent/(name+'.tar.gz')
    run(['git','-C',repository,'archive','--format=tar.gz','-o',archive,commit],timeout=180)
    return archive,{'url':url,'commit':commit,'tree':tree,'archive_sha256':sha(archive)}


def verify_receipt(path):
    success=json.loads((path/'SUCCESS').read_text())
    manifest=json.loads((path/'artifacts.json').read_text())
    require(sha(path/'artifacts.json')==success['artifacts_sha256'],'manifest digest mismatch')
    for name,digest in manifest.items():
        p=PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and sha(path/name)==digest,'artifact digest mismatch')
    require(success['artifacts_count']==len(manifest),'artifact count mismatch')
    return success


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-mount',type=Path,required=True)
    parser.add_argument('--receipt-dir',type=Path,required=True)
    args=parser.parse_args()
    mount=args.scratch_mount
    require(os.geteuid()==0,'run via sudo; non-root UID1001 is used inside Forge')
    require(mount.is_absolute() and mount.resolve()==mount and mount!=Path('/'),'noncanonical scratch mount')
    mounts=forge._mount_filesystems()
    require(mount in mounts and mounts[mount][1] in {'ext4','xfs'} and mounts[mount][0]!=mounts[Path('/')][0],
            'caller must provision a distinct mounted ext4/xfs filesystem; a root-disk directory is refused')
    require(shutil.disk_usage(mount).free>6*1024**3,'less than6GiB scratch space available')
    require(args.receipt_dir.is_absolute() and not args.receipt_dir.is_symlink(),'unsafe receipt directory')
    args.receipt_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid())
    job=mount/('remeizu-kernel-'+stamp)
    job.mkdir(); downloads=job/'downloads';downloads.mkdir(); source=job/'source';source.mkdir()
    pins=json.loads((HERE/'recipes/m5s-yassy-inputs.json').read_text())
    record={'kind':'new-public-kernel-runner-inputs','kernel_input':None,'toolchain_input':None,'flash_ready':False}
    receipt_file=args.receipt_dir/'kernel-preparation.json'
    require(not receipt_file.exists(),'preparation receipt already exists')
    recipe=None
    try:
        for name in ('kernel','toolchain'):
            archive,provenance=fetch(downloads,name,pins[name+'_url'],pins[name+'_commit'],pins.get(name+'_tree'))
            extract(archive,source/name);record[name+'_input']=provenance
        for name in ('aarch64-linux-android-gcc','aarch64-linux-android-g++'):
            path=source/'toolchain/bin'/name
            data=path.read_bytes();require(data.startswith(b'#!/usr/bin/python\n'),'unexpected original compiler wrapper')
            path.write_bytes(data.replace(b'#!/usr/bin/python\n',b'#!/usr/bin/env python3\n',1))
        for name,digest in pins['toolchain_sha256'].items():
            require(sha(source/'toolchain/bin'/name)==digest,'compiler pin failed: '+name)
        for name,digest in pins['source_sha256'].items():
            require(sha(source/'kernel'/name)==digest,'source pin failed: '+name)
        tooling=source/'.forge';tooling.mkdir()
        shutil.copy2(HERE/'scripts/kernel_build.py',tooling/'kernel_build.py')
        shutil.copy2(HERE/'recipes/m5s-yassy-inputs.json',tooling/'m5s-yassy-inputs.json')
        # Small provenance root; Forge hashes every tracked/untracked source byte.
        run(['git','init',source]);run(['git','-C',source,'add','.forge'])
        env=dict(os.environ,GIT_AUTHOR_DATE='2026-09-29T00:00:00Z',GIT_COMMITTER_DATE='2026-09-29T00:00:00Z')
        run(['git','-C',source,'-c','user.name=ReMeizu','-c','user.email=build@remeizu.invalid','commit','-m','Pinned public M5s object inputs'],env=env)
        run(['docker','pull','ubuntu:20.04'],timeout=240)
        base=json.loads(output(['docker','image','inspect','ubuntu:20.04']))[0]['RepoDigests'][0]
        require('@sha256:' in base,'base image has no immutable digest')
        tag='androidforge/build-kernel:kernel-gcc49'
        run(['docker','build','--build-arg','BASE_IMAGE='+base,'-f',HERE/'recipes/kernel-gcc49.Dockerfile','-t',tag,HERE/'recipes'],timeout=600)
        image=output(['docker','image','inspect',tag,'--format','{{.Id}}'])
        record.update(base_image_digest=base,image_id=image,dockerfile_sha256=sha(HERE/'recipes/kernel-gcc49.Dockerfile'),
                      launcher_sha256=sha(HERE/'vendor/forge/forge_ephemeral_build.py'),new_environment=True)
        recipe={'image_tag':tag,'image_id':image,'build_env_key':'kernel-gcc49','source_mount_path':str(source),
                'output_dir_in_container':'/workspace/out','command':['python3','/workspace/src/.forge/kernel_build.py'],
                'env':{'FORGE_KERNEL_JOBS':'2','KBUILD_BUILD_TIMESTAMP':'2026-09-28 00:00:00 UTC','KBUILD_BUILD_VERSION':'1'},
                'idempotency_key':'m5s-public-yassy-object-'+stamp,'timeout_seconds':600,'execution_profile':'cloud-mounted',
                'scratch_mount_path':str(mount),'container_user':'1001:1001',
                'required_artifacts':['yassy-lcm.o','yassy-lcm.o.cmd','kernel.config','kernel-build.log','kernel-proof.json','tool-versions.txt']}
        model=forge.recipe_from_dict(recipe)
        record['recipe_hash']=model.recipe_hash()
        recipe_file=args.receipt_dir/'kernel-recipe.json';recipe_file.write_text(json.dumps(recipe,indent=2)+'\n')
        run([sys.executable,HERE/'scripts/kernel_forge.py','--recipe',recipe_file,'--no-resume'],
            env=dict(os.environ,FORGE_EPHEMERAL_BASE=str(job/'evidence')),timeout=1500)
        record['success']=verify_receipt(job/'evidence'/model.recipe_hash())
    finally:
        receipt_file.write_text(json.dumps(record,indent=2)+'\n')
        if (job/'evidence').exists():
            shutil.copytree(job/'evidence',args.receipt_dir/'forge',dirs_exist_ok=False)


if __name__=='__main__':
    main()
