import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(1,str(Path(__file__).resolve().parent.parent/'free-hosted-route'))
import acquire_full_phone as full

class FullAcquisitionControls(unittest.TestCase):
    def test_sanitized_source_genuine_hardlink_and_full_bytes_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);checkout=root/'checkout';checkout.mkdir();source=root/'lower';source.mkdir();file=checkout/'file';file.write_bytes(b'actual public source');file.chmod(0o644);row={'path':'file','full_path':'project/file','mode':'0o664','bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()};full.link_verified_source(checkout,source,row,{})
            actual=source/'project/file';self.assertEqual(actual.stat().st_ino,file.stat().st_ino);self.assertEqual(actual.read_bytes(),file.read_bytes());self.assertEqual(actual.stat().st_mode&0o777,0o664)
    def test_same_inode_alias_mode_conflict_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);checkout=root/'checkout';checkout.mkdir();source=root/'lower';source.mkdir();file=checkout/'file';file.write_bytes(b'fixture');file.chmod(0o644);os.link(file,checkout/'alias');mode={};row={'path':'file','full_path':'project/file','mode':'0o644','bytes':7,'sha256':hashlib.sha256(b'fixture').hexdigest()};full.link_verified_source(checkout,source,row,mode)
            with self.assertRaisesRegex(ValueError,'mode conflict'):full.link_verified_source(checkout,source,dict(row,path='alias',full_path='project/alias',mode='0o664'),mode)
    def test_wrong_body_and_git_executable_tamper_do_not_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);checkout=root/'checkout';checkout.mkdir();source=root/'lower';source.mkdir();file=checkout/'file';file.write_bytes(b'fixture');file.chmod(0o644);row={'path':'file','full_path':'project/file','mode':'0o644','bytes':7,'sha256':'0'*64}
            with self.assertRaises(Exception):full.link_verified_source(checkout,source,row,{})
            self.assertFalse((source/'project/file').exists());row['sha256']=hashlib.sha256(b'fixture').hexdigest();file.chmod(0o755)
            with self.assertRaisesRegex(ValueError,'executable'):full.link_verified_source(checkout,source,row,{})
    def test_public_failure_phase_exit_preserves_private_log_without_echo(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);log=root/'fetch.private.log';output=io.StringIO()
            from unittest import mock
            with mock.patch.object(full,'disk_floor'),contextlib.redirect_stdout(output):
                with self.assertRaises(ValueError):full.command([sys.executable,'-c',"print('PRIVATE_STDERR_SENTINEL');raise SystemExit(7)"],dict(os.environ),log,project='third_party/fixture',phase='fetch')
            self.assertIn('PRIVATE_STDERR_SENTINEL',log.read_text());self.assertNotIn('PRIVATE_STDERR_SENTINEL',output.getvalue());self.assertIn('"exit_code": 7',output.getvalue());self.assertIn('"phase": "fetch"',output.getvalue())
            with self.assertRaises(ValueError):full.progress('arbitrary-stderr',project='third_party/fixture')

    def test_separate_lfs_cache_is_counted_in_initial_source_disk_floor(self):
        registry={'source_bytes':100,'public_projects':[{'lfs_objects':[{'object_bytes':30}], 'resolved_child_layers':[{'lfs_objects':[{'bytes':20}]}]}]}
        self.assertEqual(full.source_disk_minimum(registry),full.FLOOR+150)
        registry['public_projects'][0]['lfs_objects'][0]['object_bytes']=-1
        with self.assertRaises(ValueError):full.source_disk_minimum(registry)

    def test_single_actual_disk_floor_refuses(self):
        from unittest import mock
        with mock.patch.object(full.shutil,'disk_usage',return_value=type('Disk',(),{'free':full.FLOOR-1})()):
            with self.assertRaises(ValueError):full.disk_floor(Path('/tmp'))

if __name__=='__main__':unittest.main()
