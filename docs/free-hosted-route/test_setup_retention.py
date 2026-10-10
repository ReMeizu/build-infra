"""Refusal controls for real source-bound pre-Forge setup evidence only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from retain_release import setup_policy,setup_commands,HEALTH_CODE
from acquire import sha


class SetupRetentionControls(unittest.TestCase):
    def fixture(self):
        job=Path(tempfile.mkdtemp(prefix='setup-retention-control-',dir='/dev/shm'))
        root=job/'ram/setup-diagnostics';root.mkdir(parents=True)
        context=job/'public-inputs/original/official-build-env'
        argv=['docker','build','-f',str(context/'Dockerfile'),'-t','androidforge/build-free-native-123:android-9',str(context)]
        row={'phase':'docker-build','argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),
             'started':True,'completed':True,'owned_child_reaped':True,'exit_code':1}
        for stream in ('stdout','stderr'):
            path=root/('docker-build.'+stream);path.write_text('private setup diagnostic fixture\n')
            row[stream]={'path':path.name,'bytes':path.stat().st_size,'sha256':sha(path)}
        manifest={'schema':'remeizu.free-native-setup-commands.v1','run_id':'123','source_lock_sha256':'0'*64,'commands':[row]}
        (root/'SETUP_COMMANDS.json').write_text(json.dumps(manifest))
        after=job/'ram/PUBLIC_INPUTS_AFTER.json'
        after.write_text(json.dumps({'all_source_tool_wheel_inventory_pass':True,'gn_inputs_sha256':'a'*64}))
        record={'schema':'remeizu.free-hosted-native-run.v1','run_id':'123','status':'SETUP_FAILED','retention_scope':'SETUP_FAILED',
                'source_lock_sha256':'0'*64,'public_input_acquisition_verified':True,'retention_preflight_verified':True,
                'setup_commands_termination_verified':True,'actual_forge_submitted':False,'native_compile_executed':False,
                'native_four_images':False,'private_android_inputs':False,'full375_phone':False,'runtime':False,'setup_failure_phase':'docker-build','setup_exit_code':1,
                'setup_diagnostics_sha256':sha(root/'SETUP_COMMANDS.json'),'all_public_source_tool_wheel_before_after_verified':True,
                'independent_after_witness_sha256':sha(after)}
        return job,root,manifest,record,{'gn_inputs_sha256':'a'*64}

    def rewrite(self,root,manifest,record):
        (root/'SETUP_COMMANDS.json').write_text(json.dumps(manifest))
        record['setup_diagnostics_sha256']=sha(root/'SETUP_COMMANDS.json')

    def test_setup_policy_is_evidence_only_without_forge_identity(self):
        job,root,manifest,record,lock=self.fixture();original=copy.deepcopy(record)
        actual,policy=setup_policy(job,record,'0'*64,lock)
        self.assertEqual(actual,root);self.assertEqual(policy['retention_scope'],'SETUP_FAILED')
        self.assertTrue(all(r['kind']=='public-producer-evidence' for r in policy['outputs']))
        self.assertEqual(record,original);self.assertNotIn('recipe_hash',record)
        self.assertNotIn('compiler_termination_verified',record);self.assertNotIn('image_id',record)

    def test_no_scope_upgrade_from_setup_to_native_or_private(self):
        job,root,manifest,record,lock=self.fixture()
        for field in ('actual_forge_submitted','native_compile_executed','native_four_images','private_android_inputs','full375_phone','runtime'):
            with self.subTest(field=field),self.assertRaises(ValueError):
                setup_policy(job,dict(record,**{field:True}),'0'*64,lock)

    def test_source_after_witness_is_real_bound_file_not_boolean_only(self):
        job,root,manifest,record,lock=self.fixture()
        (job/'ram/PUBLIC_INPUTS_AFTER.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'after-witness'):setup_policy(job,record,'0'*64,lock)

    def test_inflight_or_unreaped_setup_client_rejected(self):
        for field in ('completed','owned_child_reaped'):
            job,root,manifest,record,lock=self.fixture();manifest['commands'][0][field]=False;self.rewrite(root,manifest,record)
            with self.assertRaisesRegex(ValueError,'completed reaped'):setup_commands(job,record,'0'*64)

    def test_log_byte_drift_and_carrier_path_rejected(self):
        job,root,manifest,record,lock=self.fixture();(root/'docker-build.stderr').write_text('different real bytes')
        with self.assertRaisesRegex(ValueError,'log identity'):setup_commands(job,record,'0'*64)
        job,root,manifest,record,lock=self.fixture();manifest['commands'][0]['stderr']['path']='../android-donor.img';self.rewrite(root,manifest,record)
        with self.assertRaisesRegex(ValueError,'unlisted'):setup_commands(job,record,'0'*64)

    def test_command_hash_and_owned_context_must_both_match(self):
        job,root,manifest,record,lock=self.fixture();manifest['commands'][0]['argv_sha256']='b'*64;self.rewrite(root,manifest,record)
        with self.assertRaisesRegex(ValueError,'command binding'):setup_commands(job,record,'0'*64)
        job,root,manifest,record,lock=self.fixture();row=manifest['commands'][0];row['argv']=['cat','/secret/credential'];row['argv_sha256']=hashlib.sha256(json.dumps(row['argv'],separators=(',',':')).encode()).hexdigest();self.rewrite(root,manifest,record)
        with self.assertRaisesRegex(ValueError,'owned public source'):setup_commands(job,record,'0'*64)

    def test_success_or_foreign_setup_manifest_rejected(self):
        job,root,manifest,record,lock=self.fixture();manifest['commands'][0]['exit_code']=0;self.rewrite(root,manifest,record)
        with self.assertRaisesRegex(ValueError,'failed setup phase'):setup_commands(job,record,'0'*64)
        job,root,manifest,record,lock=self.fixture();manifest['run_id']='456';self.rewrite(root,manifest,record)
        with self.assertRaisesRegex(ValueError,'run/source binding'):setup_commands(job,record,'0'*64)

    def test_timeout_or_signal_race_with_zero_exit_is_still_setup_failure(self):
        for flag,value in [('timed_out',True),('interrupted_signal',2)]:
            job,root,manifest,record,lock=self.fixture();row=manifest['commands'][0]
            row['exit_code']=0;row[flag]=value;record['setup_exit_code']=0;self.rewrite(root,manifest,record)
            actual,files=setup_commands(job,record,'0'*64)
            self.assertEqual(actual,root);self.assertEqual(len(files),3)

    def test_real_unsubmitted_recipe_is_not_discarded_or_relabelled(self):
        job,root,manifest,record,lock=self.fixture();record['recipe_hash']='c'*64
        record['image_id']='sha256:'+'d'*64
        original=copy.deepcopy(record)
        actual,policy=setup_policy(job,record,'0'*64,lock)
        self.assertEqual(record,original)
        witness=json.loads((actual/'SETUP_FAILED_SOURCE_AFTER.json').read_text())
        self.assertFalse(witness['actual_forge_submitted'])
        self.assertFalse(witness['forge_identity_fabricated'])
        self.assertNotIn('forge_identity_constructed',witness)

    def test_health_binding_rejects_arbitrary_python_and_foreign_identity(self):
        job,root,manifest,record,lock=self.fixture()
        first=manifest['commands'][0];first['exit_code']=0
        tag='androidforge/build-free-native-123:android-9'
        commands=[('image-inspect',['docker','image','inspect',tag,'--format','{{.Id}}'],0),
                  ('image-health',['docker','run','--rm','--network=none','--user',str(os.getuid())+':'+str(os.getgid()),
                    '--mount','type=bind,src='+str(job/'ram')+',dst=/workspace/out','sha256:'+'d'*64,'python3','-c',HEALTH_CODE],1)]
        for phase,argv,code in commands:
            row={'phase':phase,'argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),
                 'started':True,'completed':True,'owned_child_reaped':True,'exit_code':code}
            for stream in ('stdout','stderr'):
                path=root/(phase+'.'+stream);path.write_text('fixture')
                row[stream]={'path':path.name,'bytes':path.stat().st_size,'sha256':sha(path)}
            manifest['commands'].append(row)
        record['setup_failure_phase']='image-health';self.rewrite(root,manifest,record)
        setup_commands(job,record,'0'*64)
        before=copy.deepcopy(manifest)
        for index,value in ((11,'import os; print(os.environ)'),(5,'999999:999999')):
            bad=copy.deepcopy(before);bad['commands'][-1]['argv'][index]=value
            bad['commands'][-1]['argv_sha256']=hashlib.sha256(json.dumps(bad['commands'][-1]['argv'],separators=(',',':')).encode()).hexdigest()
            self.rewrite(root,bad,record)
            with self.assertRaisesRegex(ValueError,'health command scope'):setup_commands(job,record,'0'*64)


if __name__=='__main__':unittest.main(verbosity=2)
