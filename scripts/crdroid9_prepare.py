#!/usr/bin/env python3
"""Prepare an isolated cached checkout. Never upload the resulting tree publicly."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

root = Path('/home/circleci/crdroid9-m6')
infra = Path(__file__).resolve().parents[1]
bundle = Path(sys.argv[1])
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == sys.argv[2]
assert json.loads((root / 'sync-status.json').read_text())['sync_complete']
assert subprocess.check_output(['git', '-C', str(root / 'device/meizu/meizu_m6'), 'rev-parse', 'HEAD'], text=True).strip() == 'b31f1449e25129810cf9b6d239d8b466c4ec6f55'
def hydrate(rel):
    path = root / rel
    listed = subprocess.check_output(['git', '-C', str(path), 'lfs', 'ls-files'], text=True)
    if listed.strip():
        print('LFS hydration:', rel, flush=True)
        subprocess.run(['git', '-C', str(path), 'lfs', 'pull'], check=True, timeout=900)
        subprocess.run(['git', '-C', str(path), 'lfs', 'fsck'], check=True, timeout=300)
    return rel

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(hydrate, (root / '.repo/project.list').read_text().splitlines()))

with tarfile.open(bundle) as tf:
    for entry in tf:
        p = root / entry.name
        assert not Path(entry.name).is_absolute() and '..' not in Path(entry.name).parts
        assert p.parent.resolve().is_relative_to(root)
        if entry.issym():
            assert (p.parent / entry.linkname).resolve().is_relative_to(root) or entry.linkname.startswith(('/system/', '/vendor/'))
        elif entry.islnk():
            assert (root / entry.linkname).resolve().is_relative_to(root)
        else:
            assert entry.isfile() or entry.isdir()
            assert p.resolve().is_relative_to(root)
        tf.extract(entry, root)
inputs = json.loads((root / 'm6-private-inputs.json').read_text())
for rel, expected in inputs['files'].items():
    p = root / rel
    actual = {'symlink': str(p.readlink())} if p.is_symlink() else {'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    assert actual == expected, rel

subprocess.run([sys.executable, str(infra / 'scripts/crdroid9_scope_kernel.py')], check=True)
subprocess.run([sys.executable, str(infra / 'scripts/crdroid9_kernel_input.py'),str(root)], check=True)
mk = root / 'device/meizu/meizu_m6/lineage.mk'
old = mk.read_text()
# The product must inherit the crDroid version values, not override them with LOS16.
remove = ('PRODUCT_VERSION_MAJOR :=', 'PRODUCT_VERSION_MINOR :=',
          'PRODUCT_VERSION_MAINTENANCE :=', 'LINEAGE_VERSION :=',
          'LINEAGE_DISPLAY_VERSION :=', 'LINEAGE_PLATFORM_SDK_VERSION :=',
          'LINEAGE_PLATFORM_REV :=')
assert '    Trebuchet' in old and 'LINEAGE_VERSION := 16.0-UNOFFICIAL-meizu_m6' in old
new = '\n'.join(line for line in old.splitlines() if not line.startswith(remove)) + '\n'
assert 'LOCAL_PACKAGE_NAME := Launcher3QuickStep' in (root / 'packages/apps/crDroidHome/Android.mk').read_text()
new = new.replace('    Trebuchet', '    Launcher3QuickStep')
new = 'LINEAGE_BUILD := meizu_m6\nLINEAGE_BUILDTYPE := UNOFFICIAL\n' + new
mk.write_text(new)
forge = root / '.forge'
forge.mkdir(exist_ok=True)
shutil.copy2(infra / 'scripts/crdroid9_build.sh', forge / 'run.sh')
subprocess.run(['git', 'init', str(root)], check=True)
subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'ReMeizu CI'], check=True)
subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'ci@users.noreply.github.com'], check=True)
subprocess.run(['git', '-C', str(root), 'add', '-f', 'sync-status.json', 'm6-private-inputs.json', '.forge/run.sh'], check=True)
subprocess.run(['git', '-C', str(root), 'commit', '-m', 'Record crDroid M6 private build inputs'], check=True, env={**os.environ, 'GIT_AUTHOR_DATE':'2026-09-29T00:00:00Z', 'GIT_COMMITTER_DATE':'2026-09-29T00:00:00Z'})
print('CRDROID_M6_INPUTS_READY', flush=True)
