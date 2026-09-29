#!/usr/bin/env python3
"""Authenticate checkpoints and reuse compiler output only for identical inputs."""
import hashlib,json,shutil,subprocess,tarfile,urllib.request
from pathlib import Path
from crdroid9_checkpoint import decrypt

def require_stopped(root):
    for path in root.glob('**/.forge-container/*.json'):
        assert json.loads(path.read_text()).get('cleanup_needed') is False, 'unresolved container cleanup'

def download_resume(control, private, mount, key, log):
    url=control['resume_url']
    assert url.startswith('https://output.circle-artifacts.com/')
    cipher=private/'resume.rmc'
    urllib.request.urlretrieve(url,cipher)
    digest=hashlib.sha256()
    with cipher.open('rb') as f:
        while chunk:=f.read(1024*1024): digest.update(chunk)
    assert digest.hexdigest()==control['resume_sha256'], 'checkpoint hash mismatch'
    pending=private/'resume.pending.zst'
    with cipher.open('rb') as source,pending.open('wb') as target: decrypt(source,target,key)
    verified=private/'resume.authenticated.zst'
    pending.rename(verified) # No extraction before GCM authentication completes.
    root=mount/'resume'
    root.mkdir()
    process=subprocess.Popen(['zstd','-dc',str(verified)],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout,mode='r|') as tf:
        for entry in tf:
            rel=Path(entry.name)
            assert not rel.is_absolute() and '..' not in rel.parts
            path=root/rel
            assert path.parent.resolve().is_relative_to(root.resolve()) or path==root
            if entry.issym():
                target=Path(entry.linkname)
                assert (path.parent/target).resolve().is_relative_to(root.resolve()) or str(target).startswith(('/workspace/src/','/workspace/scratch/'))
            elif entry.islnk():
                assert not Path(entry.linkname).is_absolute() and '..' not in Path(entry.linkname).parts
                assert (root/entry.linkname).resolve().is_relative_to(root.resolve())
            else:
                assert entry.isfile() or entry.isdir()
                assert path.resolve().is_relative_to(root.resolve())
            tf.extract(entry,root)
    assert process.wait()==0
    require_stopped(root)
    print('Authenticated previous checkpoint; identity validation pending',file=log,flush=True)

def validate_identity(previous, current, old_recipe, new_recipe, root):
    assert previous==current, 'checkpoint source identity mismatch'
    def stable(recipe):
        return {k:v for k,v in recipe.items() if k not in ('idempotency_key','timeout_seconds')}
    assert stable(old_recipe)==stable(new_recipe), 'checkpoint image or build contract mismatch'
    require_stopped(root)

def restore_compiler_output(root, current, recipe, forge):
    old=json.loads((root/'recipe.json').read_text())
    proof=json.loads((root/'source-proof.json').read_text())
    validate_identity(proof,current,old,recipe,root)
    old_hash=forge.recipe_from_dict(old).recipe_hash()
    new_hash=forge.recipe_from_dict(recipe).recipe_hash()
    source=root/'forge-scratch'/old_hash
    destination=Path(recipe['scratch_mount_path'])/'forge-scratch'/new_hash
    assert source.is_dir() and destination.is_dir()
    for name in ('out','ccache','home'):
        target=destination/name
        assert not any(target.iterdir()), 'new scratch must be empty'
        target.rename(destination/(name+'.empty'))
        shutil.move(str(source/name),str(target))
    print('VERIFIED_COMPILER_CHECKPOINT_RESTORED',flush=True)

if __name__=='__main__':
    import sys
    assert len(sys.argv)==3 and sys.argv[1]=='--check-stopped'
    require_stopped(Path(sys.argv[2]))
    print('PASS: container lifecycle records confirm cleanup')
