"""Admission/refusal and actual RAM/unchanged-Forge artifact controls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import run_control as control
import ram_overlay_protocol as model

class SourceControlTests(unittest.TestCase):
    def test_public_first_attempt_exact_control_branch_only(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            event=Path(folder)/'event.json';event.write_text(json.dumps({'repository':{'private':False}}))
            env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'ReMeizu/build-infra','GITHUB_REF':'refs/heads/codex/source-overlay-control-20261010','GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'123','GITHUB_EVENT_PATH':str(event),'RUNNER_ARCH':'X64'}
            control.checked_job(env)
            for change in ({'GITHUB_REF':'refs/heads/codex/free-native-20261009'},{'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_REPOSITORY':'foreign/repository'}):
                with self.assertRaises(ValueError):control.checked_job(dict(env,**change))
            event.write_text(json.dumps({'repository':{'private':True}}))
            with self.assertRaises(ValueError):control.checked_job(env)
    def test_lower_requires_actual_readonly_mount_and_exact_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);file=root/'source.txt';file.write_text('original');file.chmod(0o644)
            rows=[{'path':'source.txt','bytes':8,'mode':'0o644','sha256':model.sha(file)}];digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            with self.assertRaisesRegex(ValueError,'readonly'):model.verify_lower(root,rows,digest)
            with patch.object(model,'filesystem',return_value='ext4'),patch.object(model.subprocess,'check_output',return_value=b'ro,relatime'):
                model.verify_lower(root,rows,digest)
                file.write_text('changed')
                with self.assertRaisesRegex(ValueError,'SHA/size/mode'):model.verify_lower(root,rows,digest)
    def test_extra_opaque_lower_member_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'unlisted.py').write_text('unlisted source')
            digest=hashlib.sha256(b'[]').hexdigest()
            with patch.object(model,'filesystem',return_value='ext4'),patch.object(model.subprocess,'check_output',return_value=b'ro,relatime'):
                with self.assertRaisesRegex(ValueError,'unlisted'):model.verify_lower(root,[],digest)
    def test_actual_same_RAM_hardlink_and_original_Forge_artifact_enumeration(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            ram=Path(folder);upper=ram/'upper';artifact=ram/'forge-output';upper.mkdir();artifact.mkdir();source=upper/'fixture.txt';source.write_text('literal source control output')
            result=model.retain_ram_file(source,artifact,'retained/fixture.txt',model.sha(source),ram)
            self.assertTrue(result['actual_same_inode_RAM_hardlink']);self.assertFalse(result['target_compilation_proven_by_filesystem_control'])
            spec=importlib.util.spec_from_file_location('control_test_original_Forge',control.FORGE);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
            self.assertEqual(model.sha(control.FORGE),control.FORGE_SHA)
            self.assertEqual(forge.collect_artifacts(artifact),{'retained/fixture.txt':model.sha(source)})
    def test_wrong_SHA_or_disk_artifact_cannot_pass_as_RAM_output(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder,tempfile.TemporaryDirectory() as disk:
            ram=Path(folder);artifact=ram/'output';artifact.mkdir();source=ram/'source';source.write_text('literal')
            with self.assertRaises(ValueError):model.retain_ram_file(source,artifact,'fixture','0'*64,ram)
            external=Path(disk)/'source';external.write_text('literal')
            with self.assertRaises(ValueError):model.retain_ram_file(external,artifact,'fixture',model.sha(external),ram)
    def test_unchanged_Forge_constructs_real_readonly_source_and_RAM_root_binds(self):
        spec=importlib.util.spec_from_file_location('control_recipe_original_Forge',control.FORGE);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
        recipe=forge.recipe_from_dict({'image_tag':'androidforge/build-source-overlay-123:android-9','build_env_key':'android-9','source_mount_path':'/source-control','output_dir_in_container':'/workspace/out','command':['python3','-B','/workspace/src/control_worker.py'],'extra_mounts':[['/owned-ram','/workspace/ram','rw']],'env':{},'timeout_seconds':120,'idempotency_key':'source-control-fixture'})
        argv=forge.build_docker_argv(recipe,Path('/owned-ram/forge')/recipe.recipe_hash(),'owned-source-control')
        self.assertIn('/source-control:/workspace/src:ro',argv);self.assertIn('/owned-ram:/workspace/ram:rw',argv)
        self.assertNotIn('--privileged',argv);self.assertNotIn('ninja',argv);self.assertNotIn('clang',argv)
    def test_exact_RAM_controller_git_satisfies_actual_Forge_provenance(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            source=Path(folder)
            for name in ('control_worker.py','ram_overlay_protocol.py','PLAN.json'):(source/name).write_text('{}' if name.endswith('.json') else '# source fixture\n')
            identity=control.freeze_git(source)
            spec=importlib.util.spec_from_file_location('control_provenance_actual_Forge',control.FORGE);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
            before=forge.current_source_provenance(source);self.assertEqual(len(identity['head']),40);self.assertEqual(len(identity['tree']),40)
            (source/'control_worker.py').write_text('# actual source drift fixture\n')
            self.assertNotEqual(forge.current_source_provenance(source),before)
    def test_cleanup_uses_single_state_contract_and_preserves_original_receipt(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            actual=Path(folder);meta=actual/'.forge-container';meta.mkdir();rh='a'*64;inv='b'*32
            state={'recipe_hash':rh,'invocation':inv,'container_name':'forge-eph-'+rh[:12]+'-'+inv[:12],'cleanup_needed':True,'container_id':'c'*64,'client_reaped':True,'create_issued':True};path=meta/(inv+'.json');path.write_text(json.dumps(state));original=path.read_bytes();calls=[]
            def cleanup(receipt):calls.append(receipt);return {'cleanup_needed':False,'cleanup_reason':'owned exact fixture closure'}
            forge=SimpleNamespace(CONTAINER_METADATA_DIR='.forge-container',_cleanup_owned_container=cleanup)
            absent=subprocess.CompletedProcess([],1,'','No such container')
            with patch.object(control.subprocess,'run',return_value=absent):proof=control.closed_containers(forge,actual,rh)
            self.assertEqual(len(calls),1);self.assertTrue(proof['all_owned_container_closure_pass']);self.assertEqual(path.read_bytes(),original)
    def test_unresolved_late_created_cannot_pass_cleanup_contract(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            actual=Path(folder);meta=actual/'.forge-container';meta.mkdir();rh='a'*64;inv='b'*32
            state={'recipe_hash':rh,'invocation':inv,'container_name':'forge-eph-'+rh[:12]+'-'+inv[:12],'cleanup_needed':True,'client_reaped':True,'create_issued':True};(meta/(inv+'.json')).write_text(json.dumps(state))
            forge=SimpleNamespace(CONTAINER_METADATA_DIR='.forge-container',_cleanup_owned_container=lambda receipt:{'cleanup_needed':True,'cleanup_reason':'create may complete late'})
            with self.assertRaisesRegex(ValueError,'owned client or daemon closure'):control.closed_containers(forge,actual,rh)
    def test_known_CID_absence_does_not_override_unreaped_or_needed_cleanup(self):
        for reaped,needed in ((False,True),(False,False),(True,True)):
            with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
                actual=Path(folder);meta=actual/'.forge-container';meta.mkdir();rh='a'*64;inv='b'*32
                state={'recipe_hash':rh,'invocation':inv,'container_name':'forge-eph-'+rh[:12]+'-'+inv[:12],'cleanup_needed':True,'container_id':'c'*64,'client_reaped':reaped,'create_issued':True};(meta/(inv+'.json')).write_text(json.dumps(state))
                forge=SimpleNamespace(CONTAINER_METADATA_DIR='.forge-container',_cleanup_owned_container=lambda receipt:{'cleanup_needed':needed})
                with patch.object(control.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','No such container')),self.assertRaisesRegex(ValueError,'owned client or daemon closure'):control.closed_containers(forge,actual,rh)
    def test_failure_diagnosis_emits_only_bounded_source_owned_codes(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            log=Path(folder)/'stderr';log.write_text('github_pat_PRIVATE\nValueError: actual lower readonly bind mount required\n')
            codes=control.bounded_log_reasons([log]);self.assertEqual(codes,['LOWER_READONLY_BIND_REQUIRED']);self.assertNotIn('PRIVATE',str(codes))
            self.assertEqual(control.failure_code(subprocess.TimeoutExpired(['fixture'],3)),'OWNED_SOURCE_COMMAND_DEADLINE')

if __name__=='__main__':unittest.main(verbosity=2)
