#!/usr/bin/env python3
"""Export only the kernel used by M6; preserve the unrelated full BSP outside ROM."""
import json
from pathlib import Path
import subprocess

root=Path('/home/circleci/crdroid9-m6')
kernel=root/'kernel/meizu/meizu_m6'
preserved=Path('/home/circleci/m6-original-kernel-bsp')
sha='888e2a4f5280de34ca398ed5e3e807a49805b056'
gitdir=subprocess.check_output(['git','-C',str(kernel),'rev-parse','--absolute-git-dir'],text=True).strip()
assert subprocess.check_output(['git','-C',str(kernel),'rev-parse','HEAD'],text=True).strip()==sha
assert (kernel/'kernel-3.18/Makefile').is_file()
assert not preserved.exists()
kernel.rename(preserved)
kernel.mkdir(parents=True)
export=subprocess.Popen(['git','--git-dir='+gitdir,'archive',sha,'kernel-3.18'],stdout=subprocess.PIPE)
result=subprocess.run(['tar','-xf','-','-C',str(kernel)],stdin=export.stdout)
assert result.returncode==0 and export.wait()==0
assert (kernel/'kernel-3.18/Makefile').is_file()
assert not (kernel/'external').exists()
(root/'.forge').mkdir(exist_ok=True)
(root/'.forge/kernel-source.json').write_text(json.dumps({'commit':sha,'subtree':'kernel-3.18','preserved_bsp':str(preserved)},indent=2)+'\n')
print('M6_KERNEL_SUBTREE_EXPORTED')
