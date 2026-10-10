"""Real pinned patch application and correction-admission refusal controls."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from acquire import validate_lock,validate_cohort_proof
from libhybris_patch_guard import validate_patch_source_correction,CORRECTION,OLD_PATCH,NEW_PATCH

HERE=Path(__file__).resolve().parent

class LibhybrisGNPrependControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock=json.loads((HERE/'public_inputs.lock.json').read_text())
        cls.inputs=json.loads((HERE/'controller/GN_INPUTS.json').read_text())

    def test_actual_cohort_and_corrected_patch_admitted(self):
        validate_lock(self.lock,self.inputs)
        proof=validate_cohort_proof(self.lock,self.inputs,HERE/'controller')
        self.assertEqual(len(proof['actual_selected_parts']),110)
        self.assertEqual(self.inputs['worker_sha256'],'196b46fc755f5ef77eeca02dc81c448f46f3f70daf095f3997624ec2583bc9be')

    def test_unreviewed_correction_proof_refused(self):
        for changed in ({},dict(CORRECTION,sha256='0'*64)):
            bad=dict(self.lock,patch_source_correction=changed)
            with self.assertRaisesRegex(ValueError,'correction proof differs'):
                validate_patch_source_correction(bad,self.inputs,HERE/'controller')

    def test_wrong_patch_or_old_bug_reintroduced_refused(self):
        for replacement in (OLD_PATCH,dict(NEW_PATCH,sha256='0'*64)):
            bad=copy.deepcopy(self.inputs)
            bad['patches']=[replacement if r==NEW_PATCH else r for r in bad['patches']]
            with self.assertRaisesRegex(ValueError,'substitution differs'):
                validate_patch_source_correction(self.lock,bad,HERE/'controller')

    def test_unrelated_patch_change_and_reordering_refused(self):
        bad=copy.deepcopy(self.inputs);bad['patches'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'patch rows or patch order changed'):
            validate_patch_source_correction(self.lock,bad,HERE/'controller')
        bad=copy.deepcopy(self.inputs);bad['patches'][0],bad['patches'][1]=bad['patches'][1],bad['patches'][0]
        with self.assertRaisesRegex(ValueError,'patch rows or patch order changed'):
            validate_patch_source_correction(self.lock,bad,HERE/'controller')

    def test_source_member_and_project_drift_refused(self):
        bad=copy.deepcopy(self.inputs);bad['source_files'][0]['mode']='0o600'
        with self.assertRaisesRegex(ValueError,'source136 member rows changed'):
            validate_patch_source_correction(self.lock,bad,HERE/'controller')
        bad=copy.deepcopy(self.inputs);bad['projects'][0]['tracked_inventory_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source136 project rows changed'):
            validate_patch_source_correction(self.lock,bad,HERE/'controller')

    def test_real_patch_applies_without_fuzz_and_preserves_headers_and_all_original_flags(self):
        original=Path('/home/n8n/ohos-m5c-platform-20261009/third_party/libhybris')
        root=Path(tempfile.mkdtemp(prefix='libhybris-gn-prepend-source-control-',dir='/dev/shm'))
        before={name:(original/name).read_bytes() for name in ('BUILD.gn','libhybris_args.gni')}
        source_map={r['path']:r for r in self.inputs['source_files']}
        for name,data in before.items():
            self.assertEqual(hashlib.sha256(data).hexdigest(),source_map['third_party/libhybris/'+name]['sha256'])
            (root/name).write_bytes(data)
        result=subprocess.run(['patch','--batch','--forward','--fuzz=0','-p1','-i',str(HERE/'controller'/NEW_PATCH['path'])],
                              cwd=root,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0)
        body=(root/'BUILD.gn').read_text();old=before['BUILD.gn'].decode()
        block='''  if (libhybris_android_header_overlay != "") {
    libhybris_android_include_dirs =
        [ libhybris_android_header_overlay ] + include_dirs
    include_dirs = []
    include_dirs = libhybris_android_include_dirs
  }
'''
        self.assertEqual(body.count(block),1)
        self.assertEqual(body.replace(block,''),old)
        old_headers=re.search(r'include_dirs = \[(.*?)\n  \]',old,re.S).group(1)
        new_headers=re.search(r'include_dirs = \[(.*?)\n  \]',body,re.S).group(1)
        self.assertEqual(new_headers,old_headers)
        self.assertEqual(len(re.findall(r'"[^"\n]+"',old_headers)),7)
        self.assertLess(body.index('[ libhybris_android_header_overlay ] + include_dirs'),body.index('include_dirs = []'))
        args=(root/'libhybris_args.gni').read_text()
        inserted='''
  # Explicit device-generated Android public header/version adaptation.
  # Empty retains the original pinned generic header cohort.
  libhybris_android_header_overlay = ""
'''
        self.assertEqual(args.replace(inserted,''),before['libhybris_args.gni'].decode())
        for name,data in before.items():self.assertEqual((original/name).read_bytes(),data)

if __name__=='__main__':unittest.main()
