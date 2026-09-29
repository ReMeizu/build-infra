#!/usr/bin/env python3
"""Connect the pinned private M6 image to Pie's expected prebuilt location."""
import hashlib,sys
from pathlib import Path

def prepare(root):
    device=Path(root)/'device/meizu/meizu_m6'
    image=device/'prebuilt-kernel/Image.gz-dtb'
    expected='e70854445d07a4063af52df08aa53a35ae5a92676521fa0de42fed9f17f3b8ca'
    assert hashlib.sha256(image.read_bytes()).hexdigest()==expected, 'Unexpected M6 kernel image'
    target=device/'radio/kernel'
    target.parent.mkdir(exist_ok=True)
    if target.is_symlink() or target.exists():
        assert target.resolve()==image.resolve(), 'Refusing to replace another kernel input'
    else: target.symlink_to('../prebuilt-kernel/Image.gz-dtb')
    assert target.is_file() and target.resolve()==image.resolve()
    print('M6_PINNED_PREBUILT_CONNECTED')

if __name__=='__main__': prepare(Path(sys.argv[1]))
