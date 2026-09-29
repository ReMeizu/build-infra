#!/usr/bin/env python3
"""Freeze only M6 inputs on n8n. The archive must travel over private SSH."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

src = Path('/srv/forge/android/los16-ct07')
dest = Path(sys.argv[1]).resolve()
dest.mkdir(parents=True, exist_ok=False)
trees = {
    'device/meizu/m3_meizu_m6-common': 'fe0347645132fd21dfc6c0dbd6010fb8e2dd2a8d',
    'device/meizu/meizu_mt675x-common': 'c4e09d20fe64a42b0c4760d0e39bf7f6f0f685ab',
    'vendor/mediatek': '9514dfaf15bb5fe67f78c8f3fbdd1b5f14e70be9',
}
for rel, sha in trees.items():
    assert subprocess.check_output(['git', '-C', str(src / rel), 'rev-parse', 'HEAD'], text=True).strip() == sha
    assert not subprocess.check_output(['git', '-C', str(src / rel), 'diff', 'HEAD', '--'])
    target = dest / rel
    target.mkdir(parents=True)
    archive = subprocess.Popen(['git', '-C', str(src / rel), 'archive', sha], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=archive.stdout, mode='r|') as tf:
        for member in tf:
            assert not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            tf.extract(member, target)
    assert archive.wait() == 0
shutil.copytree(src / 'vendor/meizu/meizu_m6', dest / 'vendor/meizu/meizu_m6', symlinks=True)
rel = 'device/meizu/meizu_m6/prebuilt-kernel/Image.gz-dtb'
(dest / rel).parent.mkdir(parents=True)
shutil.copy2(src / rel, dest / rel)
assert hashlib.sha256((dest / rel).read_bytes()).hexdigest() == 'e70854445d07a4063af52df08aa53a35ae5a92676521fa0de42fed9f17f3b8ca'
files = {}
materialized_symlinks = {}
for p in sorted(dest.rglob('*')):
    if p.is_symlink() and str(p.readlink()).startswith('/srv/forge/android/rom-meizu_M6-lineage-cm-14.1/vendor/meizu/meizu_m6/'):
        original = p.resolve()
        if not original.is_file():
            # The current vendor snapshot flattened the stock /system directory.
            # Relocate its stale app-JNI aliases to the corresponding supplied blob.
            suffix = str(p.readlink()).split('/proprietary/system/', 1)[1]
            original = dest / 'vendor/meizu/meizu_m6/proprietary' / suffix
            assert original.is_file(), original
        temporary = p.with_name(p.name + '.export-payload')
        shutil.copy2(original, temporary)
        temporary.replace(p)
        materialized_symlinks[p.relative_to(dest).as_posix()] = str(original)
    if p.is_symlink():
        target = str(p.readlink())
        assert p.resolve().is_relative_to(dest) or target.startswith(('/system/', '/vendor/')), p
        files[p.relative_to(dest).as_posix()] = {'symlink': str(p.readlink())}
    elif p.is_file():
        files[p.relative_to(dest).as_posix()] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
(dest / 'm6-private-inputs.json').write_text(json.dumps({'git_inputs': trees, 'files': files, 'materialized_symlinks': materialized_symlinks}, indent=2) + '\n')
archive = dest.with_suffix('.tar.gz')
with tarfile.open(archive, 'w:gz', compresslevel=1) as tf:
    for p in sorted(dest.iterdir()):
        tf.add(p, arcname=p.name)
print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': len(files)}))
