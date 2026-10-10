"""Setup-only controls: actual child logs/termination; no Docker/ROM success claim."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import setup_commands as setup
import free_native_run as run

class SetupControls(unittest.TestCase):
    def child(self,code):
        real=subprocess.Popen
        return patch.object(setup.subprocess,'Popen',side_effect=lambda argv,**kw:real([sys.executable,'-c',code],**kw))
    def record(self):return {'run_id':'123','source_lock_sha256':run.APPROVED_LOCK_SHA,'actual_forge_submitted':False}
    def test_nonzero_actual_child_logs_hashed_and_not_printed(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            root=Path(folder);record=self.record();public=io.StringIO()
            with self.child("import sys; print('actual stdout'); print('private stderr fixture',file=sys.stderr);sys.exit(19)"),contextlib.redirect_stdout(public):
                with self.assertRaises(setup.SetupCommandError) as caught:setup.execute('docker-build',['docker','build','fixture'],root,record)
            manifest=root/'setup-diagnostics/SETUP_COMMANDS.json';row=json.loads(manifest.read_text())['commands'][0]
            self.assertEqual(caught.exception.exit_code,19);self.assertEqual(public.getvalue(),'')
            for stream in ('stdout','stderr'):
                body=(manifest.parent/row[stream]['path']).read_bytes()
                self.assertEqual(row[stream]['bytes'],len(body));self.assertEqual(row[stream]['sha256'],hashlib.sha256(body).hexdigest())
            self.assertEqual(record['setup_diagnostics_sha256'],setup.sha(manifest))
            self.assertTrue(row['completed'] and row['owned_child_reaped']);self.assertFalse(record['actual_forge_submitted'])
            self.assertEqual(record['retention_scope'],'SETUP_FAILED')
    def test_actual_timeout_kills_owned_group_and_records_deadline(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            root=Path(folder);record=self.record();started=time.monotonic()
            with self.child('import os,time,signal; os.fork();signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)'):
                with self.assertRaises(setup.SetupCommandError):setup.execute('docker-build',['docker','build','fixture'],root,record,timeout=.15)
            row=json.loads((root/'setup-diagnostics/SETUP_COMMANDS.json').read_text())['commands'][0]
            self.assertLess(time.monotonic()-started,3);self.assertTrue(row['timed_out']);self.assertTrue(row['owned_child_reaped'])
            self.assertEqual(row['exit_code'],-signal.SIGKILL)
    def test_actual_cancel_flag_triggers_bounded_reap(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            root=Path(folder);record=self.record();cancelled=[0]
            timer=threading.Timer(.1,lambda:cancelled.__setitem__(0,signal.SIGTERM));timer.start();started=time.monotonic()
            try:
                with self.child('import time;time.sleep(30)'):
                    with self.assertRaises(setup.SetupCommandError):setup.execute('docker-build',['docker','build','fixture'],root,record,timeout=20,cancelled=cancelled)
            finally:timer.join()
            row=json.loads((root/'setup-diagnostics/SETUP_COMMANDS.json').read_text())['commands'][0]
            self.assertLess(time.monotonic()-started,3);self.assertEqual(row['interrupted_signal'],signal.SIGTERM)
            self.assertFalse(row['timed_out']);self.assertTrue(record['setup_commands_termination_verified'])
    def test_unknown_phase_refused_and_inspect_parse_bounded(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            root=Path(folder);record=self.record()
            with self.assertRaises(ValueError):setup.execute('arbitrary',['docker','build'],root,record)
            self.assertFalse((root/'setup-diagnostics').exists())
            with self.child("import sys;sys.stdout.write('x'*65538)"):
                with self.assertRaisesRegex(ValueError,'bounded parse'):setup.execute('image-inspect',['docker','image','inspect','fixture'],root,record)
            row=json.loads((root/'setup-diagnostics/SETUP_COMMANDS.json').read_text())['commands'][0]
            self.assertEqual(row['stdout']['bytes'],65538)
    def test_pre_forge_setup_failure_runs_real_after_witness_branch(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            base=Path(folder);original=base/'public-inputs';original.mkdir()
            real_sha=run.sha
            def digest(path):
                path=Path(path)
                if path.name=='Dockerfile':return run.DOCKER_SHA
                return real_sha(path)
            calls=[]
            def after(source,expected,ram,timeout):
                calls.append((source,expected,timeout));setup.atomic_json(ram/'PUBLIC_INPUTS_AFTER.json',{'fixture':True})
                return {'all_source_tool_wheel_inventory_pass':True}
            def fail(*args,**kw):raise setup.SetupCommandError('docker-build',23)
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','RUNNER_TEMP':str(base)}),patch.object(sys,'argv',['control']),patch.object(run,'checked_public_job'),patch.object(run,'snapshot',return_value={}),patch.object(run,'admit_values'),patch.object(run,'command',return_value=subprocess.CompletedProcess([],0,b'tmpfs',b'')),patch.object(run,'keyring',return_value=(None,run.RECIPIENT)),patch.object(run,'acquire',return_value=original),patch.object(run,'sha',side_effect=digest),patch.object(run,'setup_command',side_effect=fail),patch.object(run,'verify_inputs',side_effect=after),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.main(),1)
            record=json.loads((base/'native-public-123/PUBLIC_RESULT.json').read_text())
            self.assertEqual(len(calls),1);self.assertEqual(record['status'],'SETUP_FAILED')
            self.assertTrue(record['all_public_source_tool_wheel_before_after_verified'])
            self.assertFalse(record['actual_forge_submitted']);self.assertFalse(record['native_compile_executed'])
            for forbidden in ('compiler_termination_verified','recipe_hash','image_id'):self.assertNotIn(forbidden,record)

if __name__=='__main__':unittest.main()
