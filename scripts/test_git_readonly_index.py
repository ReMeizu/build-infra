"""Regression: provenance reads must not refresh an embedded repo's index."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

root=Path(tempfile.mkdtemp(prefix='remeizu-git-readonly-'))
def git(*args, **kw):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,**kw)
git('init')
(root/'input.txt').write_text('unchanged source\n')
git('add','input.txt')
git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture')
index=root/'.git/index'
before=hashlib.sha256(index.read_bytes()).hexdigest()
s=(root/'input.txt').stat()
os.utime(root/'input.txt',(s.st_atime,s.st_mtime+60))
git('status','--porcelain',env=dict(os.environ,GIT_OPTIONAL_LOCKS='0'))
assert hashlib.sha256(index.read_bytes()).hexdigest()==before
git('status','--porcelain',env=dict(os.environ,GIT_OPTIONAL_LOCKS='1'))
assert hashlib.sha256(index.read_bytes()).hexdigest()!=before
print('PASS: read-only Git status preserves index; default status changes it')
