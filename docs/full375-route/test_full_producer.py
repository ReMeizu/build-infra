"""Meaningful startup/immutable recipe and real output admission controls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import run_full_phone as run
import retain_full_phone as retain

class FullProducerControls(unittest.TestCase):
    def test_actual_job_event_branch_retry_and_public_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            event=Path(tmp)/'event';event.write_text(json.dumps({'repository':{'private':False}}))
            env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'ReMeizu/build-infra','GITHUB_REF':'refs/heads/codex/free-full375-20261010','GITHUB_RUN_ATTEMPT':'1','GITHUB_EVENT_NAME':'push','GITHUB_EVENT_PATH':str(event),'RUNNER_ARCH':'X64','GITHUB_RUN_ID':'123'}
            with mock.patch.object(run.os,'geteuid',return_value=1001):
                run.checked_job(env)
                for key,value in [('GITHUB_EVENT_NAME','pull_request'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/main'),('GITHUB_RUN_ID','../123')]:
                    with self.subTest(key=key),self.assertRaises(ValueError):run.checked_job(dict(env,**{key:value}))
                event.write_text(json.dumps({'repository':{'private':True}}))
                with self.assertRaises(ValueError):run.checked_job(env)

    def test_recipe_immutable_image_and_exact_ram_lower_tool_bindings(self):
        recipe=run.make_recipe(Path('/owned/controller'),Path('/owned/inputs'),Path('/owned/ram'),'sha256:'+'a'*64,'123','b'*64,600,'c'*64)
        self.assertEqual(recipe['image_tag'],'sha256:'+'a'*64)
        self.assertEqual(recipe['command'],['bash','/workspace/src/worker.sh'])
        self.assertEqual(recipe['extra_mounts'][0],['/owned/ram','/workspace/ram','rw'])
        self.assertEqual(recipe['extra_mounts'][1],['/owned/ram/lower','/workspace/src/native-source-input','ro'])
        self.assertTrue(all(row[2]=='ro' for row in recipe['extra_mounts'][1:]))
        self.assertEqual(recipe['timeout_seconds'],720)
        with self.assertRaises(ValueError):run.make_recipe(Path('/c'),Path('/i'),Path('/r'),'mutable:tag','123','b'*64,600,'c'*64)

    def test_source_cancellation_interrupts_owned_acquisition_and_keeps_setup_signal(self):
        cancelled=[0];acquiring=[True];handler=run.cancellation_handler(cancelled,acquiring)
        with self.assertRaises(KeyboardInterrupt):handler(2,None)
        self.assertEqual(cancelled[0],2);acquiring[0]=False;handler(15,None);self.assertEqual(cancelled[0],15)

    def test_actual_fresh_controller_git_freeze_and_worker_self_hash(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            root=Path(tmp);original=root/'original';original.mkdir();target=root/'controller';ram=root/'ram'
            for name in ('native_gn_worker.py','layout_native_rust.py'):
                shutil.copyfile(run.HERE/'controller'/name,original/name)
            for name in ('canonical_full_phone_coverage.json','runtime_core_nonproduction_scope.json'):
                shutil.copyfile(run.HERE/name,original/name)
            inputs={'patches':[],'overlay_files':[],'tools':[],'source_files':[],'successor_evidence':{}}
            (original/'GN_INPUTS.json').write_text(json.dumps(inputs))
            with mock.patch.object(run,'require_profile') as guard:
                actual=run.prepare_controller(original,target,ram,600)
                guard.assert_called_once()
            self.assertEqual(actual['worker_sha256'],run.sha(target/'native_gn_worker.py'))
            self.assertEqual(actual['execution_deadline_seconds'],600)
            self.assertEqual(actual['overlay_host_paths']['upper'],str(ram/'upper'))
            self.assertEqual(subprocess.check_output(['git','-C',str(target),'status','--porcelain']).strip(),b'')
            self.assertEqual(len(subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD']).strip()),40)
            with self.assertRaises(ValueError):run.prepare_controller(original,target,ram,600)

    def test_original_forge_success_recipe_and_all_artifact_readback(self):
        import importlib.util
        import sys
        path=run.ROOT/'vendor/forge/forge_ephemeral_build.py'
        self.assertEqual(run.sha(path),run.FORGE_SHA)
        spec=importlib.util.spec_from_file_location('full_test_official_forge',path);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifact=root/'actual.log';artifact.write_text('actual fixture artifact')
            manifest=root/'artifacts.json';manifest.write_text(json.dumps({'actual.log':run.sha(artifact)}))
            marker=root/'SUCCESS';record={'recipe_hash':'a'*64};value={'recipe_hash':'a'*64,'artifacts_count':1,'artifacts_sha256':run.sha(manifest)};marker.write_text(json.dumps(value))
            run.verify_forge_success(forge,root,record);self.assertTrue(record['forge_success_readback_verified'])
            artifact.write_text('wrong body')
            with self.assertRaises(RuntimeError):run.verify_forge_success(forge,root,record)
            artifact.write_text('actual fixture artifact');marker.write_text(json.dumps(dict(value,recipe_hash='b'*64)))
            with self.assertRaises(ValueError):run.verify_forge_success(forge,root,record)
            marker.write_text(json.dumps(value));(root/'FAILURE').write_text('original failure')
            with self.assertRaises(ValueError):run.verify_forge_success(forge,root,record)

    def test_actual_bounded_source_witness_and_body_drift_cancellation_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/'original';original.mkdir();ram=root/'ram';ram.mkdir();source=original/'native-source-input';source.mkdir();file=source/'file';file.write_text('actual source')
            gn=original/'GN_INPUTS.json';gn.write_text(json.dumps({'source_files':[{'path':'file','mode':'0o644','bytes':file.stat().st_size,'sha256':run.sha(file)}],'tools':[],'python_wheels':[],'projects':[]}));gn_sha=run.sha(gn)
            proof=run.verify_full_inputs(original,gn_sha,ram,timeout=10);self.assertTrue(proof['all_source_tool_wheel_inventory_pass'])
            file.write_text('wrong source')
            with self.assertRaises(ValueError):run.verify_full_inputs(original,gn_sha,ram,timeout=10)
            with self.assertRaises(ValueError):run.verify_full_inputs(original,gn_sha,ram,timeout=10,cancelled=[2])

    def fixture(self,tmp):
        job=Path(tmp);root=job/'ram/forge'/('a'*64);root.mkdir(parents=True)
        record={'source_lock_sha256':'b'*64,'profile_kind':'canonical-full-gui-a2','private_android_inputs':False,'recipe_hash':'a'*64,'actual_gn_inputs_sha256':'c'*64}
        for key in ('public_input_acquisition_verified','retention_preflight_verified','all_public_source_tool_wheel_before_after_verified','actual_forge_submitted','compiler_termination_verified'):record[key]=True
        return job,root,record

    def result(self,root,rows,images=None):
        data={'source_inventory_sha256':'c'*64,'runtime':False,'whole_image_producer_admission':False,'complete_gui_phone':False,'build_phases':[{'phase':'libc-utils-loader','exit_code':0},{'phase':'native-images','exit_code':0}], 'native_libraries':rows,'native_images':images or [],'native_image_built':len(images or [])==4}
        (root/'GN_RESULT.json').write_text(json.dumps(data));return data

    def file_row(self,root,name,body):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
        return {'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}

    def test_real_aarch64_elf_and_four_ext4_images_then_body_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            job,root,record=self.fixture(tmp);body=bytearray(64);body[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',body,16,3);struct.pack_into('<H',body,18,183)
            elf=self.file_row(root,'native-artifacts/out/libs/libfixture.so',body)
            images=[]
            for partition in ('system','vendor','sys_prod','chip_prod'):
                image=bytearray(1082);image[1080:1082]=b'\x53\xef';images.append(dict(self.file_row(root,'native-artifacts/out/packages/m5c/images/'+partition+'.img',image),partition=partition))
            self.result(root,[elf],images);_,policy=retain.actual_policy(job,record,'b'*64)
            self.assertEqual(sum(r['kind']=='native-image' for r in policy['outputs']),4)
            (root/elf['path']).write_bytes(bytes(body[:-1])+b'x')
            with self.assertRaises(ValueError):retain.actual_policy(job,record,'b'*64)

    def test_failed_phase_foreign_arch_or_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            job,root,record=self.fixture(tmp);body=bytearray(64);body[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',body,16,3);struct.pack_into('<H',body,18,62)
            row=self.file_row(root,'native-artifacts/out/libs/x.so',body);data=self.result(root,[row])
            with self.assertRaises(ValueError):retain.actual_policy(job,record,'b'*64)
            data['native_libraries']=[dict(row,path='native-artifacts/out/../../outside')];(root/'GN_RESULT.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):retain.actual_policy(job,record,'b'*64)
            data['build_phases'][0]['exit_code']=1;data['native_libraries']=[row];(root/'GN_RESULT.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):retain.actual_policy(job,record,'b'*64)

    def test_retention_recovery_closes_owned_forge_and_reuses_exact_after_witness(self):
        import full_profile
        with tempfile.TemporaryDirectory() as tmp:
            job,root,record=self.fixture(tmp);original=job/'public-inputs/original';original.mkdir(parents=True)
            gn=original/'GN_INPUTS.json';gn.write_text('{}');record.update(original_gn_inputs_sha256=run.sha(gn),run_id='123',retention_scope='NATIVE_FORGE')
            after=job/'ram/PUBLIC_INPUTS_AFTER.json';after.write_text(json.dumps({'all_source_tool_wheel_inventory_pass':True,'gn_inputs_sha256':run.sha(gn)}));record['independent_after_witness_sha256']=run.sha(after)
            original_record=copy.deepcopy(record)
            with mock.patch.object(full_profile,'require_profile'),mock.patch.object(retain,'closed_containers',return_value={'all_owned_container_closure_pass':True}) as closure,mock.patch.object(run,'verify_full_inputs') as verify:
                recovered=retain.recover_admission(job,record,'b'*64)
                closure.assert_called_once();verify.assert_not_called();self.assertTrue(recovered['compiler_termination_verified']);self.assertEqual(record,original_record)
                after.write_text('{}')
                with self.assertRaises(ValueError):retain.recover_admission(job,record,'b'*64)

    def test_unsubmitted_or_source_drift_attempt_cannot_recover_native_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            job,root,record=self.fixture(tmp);original=job/'public-inputs/original';original.mkdir(parents=True);(original/'GN_INPUTS.json').write_text('{}')
            record['original_gn_inputs_sha256']='0'*64
            with self.assertRaises(ValueError):retain.recover_admission(job,record,'b'*64)
            record['public_input_acquisition_verified']=False
            with self.assertRaises(ValueError):retain.recover_admission(job,record,'b'*64)

    def test_setup_failure_retained_without_forge_identity_and_source_drift_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp);ram=job/'ram';folder=ram/'setup-diagnostics';folder.mkdir(parents=True)
            record={'run_id':'123','source_lock_sha256':'b'*64,'profile_kind':'canonical-full-gui-a2','retention_scope':'SETUP_FAILED','status':'SETUP_FAILED','public_input_acquisition_verified':True,'retention_preflight_verified':True,'setup_commands_termination_verified':True,'actual_forge_submitted':False,'native_compile_executed':False,'native_four_images':False,'private_android_inputs':False,'full375_phone':False,'runtime':False,'setup_failure_phase':'docker-build','setup_exit_code':1,'original_gn_inputs_sha256':'c'*64,'all_public_source_tool_wheel_before_after_verified':True}
            argv=['docker','build','-f',str(job/'public-inputs/original/official-build-env/Dockerfile'),'-t','androidforge/build-full-phone-123:android-9',str(job/'public-inputs/original/official-build-env')]
            row={'phase':'docker-build','argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),'started':True,'completed':True,'exit_code':1,'owned_child_reaped':True,'timed_out':False,'interrupted_signal':0}
            for stream in ('stdout','stderr'):
                path=folder/('docker-build.'+stream);path.write_text('actual captured fixture '+stream);row[stream]={'path':path.name,'bytes':path.stat().st_size,'sha256':run.sha(path)}
            manifest=folder/'SETUP_COMMANDS.json';manifest.write_text(json.dumps({'schema':'remeizu.free-native-setup-commands.v1','run_id':'123','source_lock_sha256':'b'*64,'commands':[row]}));record['setup_diagnostics_sha256']=run.sha(manifest)
            after=ram/'PUBLIC_INPUTS_AFTER.json';after.write_text(json.dumps({'all_source_tool_wheel_inventory_pass':True,'gn_inputs_sha256':'c'*64}));record['independent_after_witness_sha256']=run.sha(after)
            _,policy=retain.setup_policy(job,record,'b'*64);self.assertEqual(policy['retention_scope'],'SETUP_FAILED');self.assertNotIn('recipe_hash',record)
            after.write_text('{}')
            with self.assertRaises(ValueError):retain.setup_policy(job,record,'b'*64)

if __name__=='__main__':unittest.main()
