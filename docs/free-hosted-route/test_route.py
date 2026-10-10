"""Meaningful refusal/source-preservation controls; no fake accepted ROMs."""
import ast
import hashlib
from pathlib import Path
import sys
import tempfile
import tarfile
import io
import unittest

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from acquire import public_url, validate_lock, extract_tool,verify,validate_cohort_proof
from make_j2_successor import transformed_worker
from resource import GIB, admit_values
from retain_release import actual_policy,cipher_upper_bound,complete_snapshot
from free_native_run import checked_public_job
from finish_attempt import run_owned
from diagnostics import diagnostic,PublicInputError
from materialize_lfs import pointer_identity,declaration,smudge_process

B6=HERE/'controller/native_gn_worker.py'

class ResourceControls(unittest.TestCase):
    def test_actual_sdk_source_cohort_fits_unchanged_ram_floor(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text())
        row={'cpu_affinity':4,'cpu_quota':None,'available_bytes':13*GIB,'tmpfs_free_bytes':10*GIB}
        proof=admit_values(row,'prepare',lock['source_bytes'],349008915)
        self.assertEqual(proof['jobs'],2)
        self.assertEqual(proof['memory_floor_bytes'],12*GIB)
        self.assertLess(proof['free_floor_bytes'],10*GIB)
        row['tmpfs_free_bytes']=proof['free_floor_bytes']-1
        with self.assertRaisesRegex(ValueError,'tmpfs capacity'):
            admit_values(row,'prepare',lock['source_bytes'],349008915)
    def test_measured_b6_source_rust_model_with_documented_host_can_fit(self):
        proof=admit_values({'cpu_affinity':4,'cpu_quota':None,'available_bytes':13*GIB,'tmpfs_free_bytes':10*GIB},'prepare',1628260457,349008915)
        self.assertEqual(proof['jobs'],2)
        self.assertFalse(proof['full375_phone'])
    def test_insufficient_memory_refused(self):
        with self.assertRaisesRegex(ValueError,'memory headroom'):
            admit_values({'cpu_affinity':4,'cpu_quota':None,'available_bytes':11*GIB,'tmpfs_free_bytes':10*GIB},'prepare',1628260457,349008915)
    def test_insufficient_tmpfs_refused(self):
        with self.assertRaisesRegex(ValueError,'tmpfs capacity'):
            admit_values({'cpu_affinity':4,'cpu_quota':None,'available_bytes':13*GIB,'tmpfs_free_bytes':7*GIB},'prepare',1628260457,349008915)
    def test_cgroup_cpu_refused(self):
        with self.assertRaisesRegex(ValueError,'CPU allowance'):
            admit_values({'cpu_affinity':4,'cpu_quota':1.5,'available_bytes':13*GIB,'tmpfs_free_bytes':10*GIB},'prepare',1628260457,349008915)
    def test_images_need_second_real_capacity_admission(self):
        with self.assertRaisesRegex(ValueError,'tmpfs capacity'):
            admit_values({'cpu_affinity':4,'cpu_quota':2,'available_bytes':4*GIB,'tmpfs_free_bytes':3*GIB},'images',1628260457,349008915)
    def test_images_need_second_real_memory_admission(self):
        with self.assertRaisesRegex(ValueError,'memory headroom'):
            admit_values({'cpu_affinity':4,'cpu_quota':2,'available_bytes':2*GIB,'tmpfs_free_bytes':5*GIB},'images',1628260457,349008915)
    def test_unmeasured_full375_source_size_refused(self):
        with self.assertRaisesRegex(ValueError,'source/Rust bound'):
            admit_values({'cpu_affinity':4,'cpu_quota':2,'available_bytes':13*GIB,'tmpfs_free_bytes':10*GIB},'prepare',5*GIB,349008915)

class PublicInputControls(unittest.TestCase):
    def test_actual_reviewed_production_cohort_preserves_original_members_and_features(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        validate_lock(lock,gni);proof=validate_cohort_proof(lock,gni,HERE/'controller')
        self.assertEqual(len(proof['actual_selected_parts']),95)
        self.assertTrue(all(proof['actual_selected_parts'][k]==v for k,v in proof['baseline_selected_parts'].items()))
    def test_unreviewed_production_proof_or_counts_refused(self):
        import json,copy
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        for mutated in (dict(lock,selected_part_count=94),dict(lock,cohort_proof={}),dict(lock,gn_inputs_sha256='0'*64)):
            with self.assertRaises(ValueError):validate_lock(mutated,gni)
    def test_changed_original_sdk_or_source_row_refused(self):
        import json,copy
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        bad=copy.deepcopy(gni);bad['tools'][0]['members'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SDK/wheel'):validate_cohort_proof(lock,bad,HERE/'controller')
        bad=copy.deepcopy(gni);bad['source_files'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source bytes/modes/links'):validate_cohort_proof(lock,bad,HERE/'controller')
    def test_source_admitted_parent101_additional_provider_rows_cannot_drift(self):
        import json,copy
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        bad=copy.deepcopy(gni)
        row=next(r for r in bad['source_files'] if r['path']=='foundation/distributeddatamgr/relational_store/bundle.json')
        row['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'parent101 source rows'):validate_cohort_proof(lock,bad,HERE/'controller')
        bad=copy.deepcopy(gni)
        project=next(r for r in bad['projects'] if r['path']=='foundation/window/window_manager')
        project['tracked_inventory_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'parent101 project rows'):validate_cohort_proof(lock,bad,HERE/'controller')
    def test_idl_ancestry_retains_all_source_admitted_parent85_features(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        proof=validate_cohort_proof(lock,gni,HERE/'controller');parent=proof['source_admitted_parent101']
        self.assertEqual(len(parent['selected_parts']),85)
        self.assertEqual(set(proof['source_admitted_parent102']['selected_parts'])-set(parent['selected_parts']),{'ability:idl_tool'})
        self.assertTrue(all(proof['actual_selected_parts'][k]==v for k,v in parent['selected_parts'].items()))
        added=next(r for r in proof['added_projects'] if r['component']=='idl_tool')
        self.assertEqual(added['head'],'afbaf94ee3a8d3b1bc5d4995bda335257670e3d2')
        self.assertEqual(added['required_gn_evidence'][0]['label'],'idl_tool:idl(${host_toolchain})')
    def test_memorytracker_batch_reuses_driver_rows_and_retains_parent102_86(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        proof=validate_cohort_proof(lock,gni,HERE/'controller');parent=proof['source_admitted_parent102']
        self.assertEqual(len(parent['selected_parts']),86)
        self.assertEqual(set(proof['immediate_parent']['selected_parts'])-set(parent['selected_parts']),{'hdf:drivers_interface_memorytracker','commonlibrary:memory_utils'})
        self.assertEqual(proof['existing_source_component_additions'][0]['provider_path'],'drivers/interface')
        self.assertTrue(all(proof['actual_selected_parts'][k]==v for k,v in parent['selected_parts'].items()))
        memory=next(r for r in gni['projects'] if r['path']=='commonlibrary/memory_utils')
        self.assertEqual(memory['head'],'651da30d5e980fcc01b923389c4c41202e76ba7e')
    def test_source_admitted_idl_provider_and_driver_rows_cannot_drift(self):
        import json,copy
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        bad=copy.deepcopy(gni)
        next(r for r in bad['source_files'] if r['path']=='foundation/ability/idl_tool/bundle.json')['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'A7 source102 rows'):validate_cohort_proof(lock,bad,HERE/'controller')
        bad=copy.deepcopy(gni)
        next(r for r in bad['projects'] if r['path']=='foundation/ability/idl_tool')['tracked_inventory_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'A7 project102 rows'):validate_cohort_proof(lock,bad,HERE/'controller')
    def test_sdk_production_batch_preserves_parent103_and_original_compiler_mode(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        proof=validate_cohort_proof(lock,gni,HERE/'controller');parent=proof['immediate_parent']
        self.assertEqual(len(parent['selected_parts']),88)
        self.assertEqual(set(proof['actual_selected_parts'])-set(parent['selected_parts']),{'arkcompiler:ets_frontend', 'sdk:sdk', 'thirdparty:abseil-cpp', 'thirdparty:zlib', 'thirdparty:protobuf', 'developtools:ace_ets2bundle', 'thirdparty:typescript'})
        self.assertTrue(proof['sdk_production_closure']['abseil_required_by_protobuf'])
        self.assertTrue(proof['sdk_production_closure']['frontend_independent_compiler_branch_unchanged_false'])
        self.assertFalse(proof['sdk_production_closure']['compiler_version_changed'])
    def test_source_admitted_memory_utils_members_cannot_drift(self):
        import json,copy
        lock=json.loads((HERE/'public_inputs.lock.json').read_text());gni=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        bad=copy.deepcopy(gni)
        next(r for r in bad['source_files'] if r['path']=='commonlibrary/memory_utils/bundle.json')['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'A8 source103 rows'):validate_cohort_proof(lock,bad,HERE/'controller')
        bad=copy.deepcopy(gni)
        next(r for r in bad['projects'] if r['path']=='commonlibrary/memory_utils')['tracked_inventory_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'A8 project103 rows'):validate_cohort_proof(lock,bad,HERE/'controller')
    def test_lfs_timeout_kills_owned_descendant_holding_stdout_pipe(self):
        import os,time,subprocess
        code="import os,time,signal; p=os.fork(); signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)"
        start=time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):smudge_process([sys.executable,'-c',code],dict(os.environ),b'pointer control',timeout=0.2)
        self.assertLess(time.monotonic()-start,3)
    def test_declared_lfs_pointer_oid_or_size_tampering_refused(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text())
        row=next(p for p in lock['projects'] if p['path']=='third_party/icu')['lfs_objects'][0]
        pointer=('version https://git-lfs.github.com/spec/v1\noid sha256:'+row['material_sha256']+'\nsize '+str(row['bytes'])+'\n').encode()
        self.assertEqual(pointer_identity(pointer,row),(row['material_sha256'],row['bytes']))
        for bad in (pointer.replace(b'size 9713',b'size 9714'),pointer.replace(row['material_sha256'].encode(),b'0'*64),pointer+b'extra\n'):
            with self.assertRaisesRegex(PublicInputError,'pointer differs'):pointer_identity(bad,row)
    def test_lfs_identity_missing_or_unbounded_capture_refused(self):
        with self.assertRaises(PublicInputError):declaration({'path':'public/member','bytes':100})
        with self.assertRaises(PublicInputError):declaration({'path':'public/member','bytes':9*1024**2,'material_sha256':'0'*64,'committed_pointer_sha256':'0'*64})
    def test_lfs_other_mismatch_size_sha_are_safe_fixed_diagnostics(self):
        error=PublicInputError('LFS_WORKING_MEMBER_MISMATCH','third_party/icu/public-member',129,'a'*64)
        d=diagnostic(error)
        self.assertEqual(d['public_member_actual_bytes'],129)
        self.assertEqual(d['public_member_actual_sha256'],'a'*64)
        self.assertNotIn('message',d)
    def test_source_mismatch_exposes_only_declared_canonical_member_and_fixed_code(self):
        root=Path(tempfile.mkdtemp(prefix='free-native-public-diagnostic-',dir='/dev/shm'))
        (root/'member.c').write_bytes(b'actual source control')
        try:verify(root,{'path':'member.c','sha256':'0'*64},diagnostic_member='base/example/member.c')
        except PublicInputError as error:
            result=diagnostic(error)
            self.assertEqual(result['error_code'],'SOURCE_BYTES_MISMATCH')
            self.assertEqual(result['declared_public_member'],'base/example/member.c')
            self.assertEqual(result['source_check']['module'],'acquire.py')
        else:self.fail('mismatched source accepted')
    def test_untrusted_exception_text_and_unsafe_path_are_never_published(self):
        result=diagnostic(ValueError('https://example.invalid/?token=ghp_secret\nprivate stderr'))
        self.assertEqual(result['error_code'],'UNCLASSIFIED_VALUE_ERROR')
        self.assertNotIn('ghp_secret',str(result))
        for member in ('../private','/home/private','https://example.invalid/secret','base/ghp_secret','bad\npath'):
            result=diagnostic(PublicInputError('SOURCE_LINK_MISMATCH',member))
            self.assertNotIn('declared_public_member',result)
    def test_fixed_non_source_code_is_bounded(self):
        result=diagnostic(ValueError('actual disk cannot retain verified source/tools/downloads/Docker headroom'))
        self.assertEqual(result['error_code'],'PUBLIC_DISK_CAPACITY_REFUSAL')
    def test_truncated_snapshot_falls_back_to_complete_bound_record(self):
        import json
        root=Path(tempfile.mkdtemp(prefix='free-native-snapshot-negative-',dir='/dev/shm'))
        first=root/'PUBLIC_RESULT.json';first.write_text('{"schema":')
        second=root/'INFLIGHT_PUBLIC_RESULT.json'
        record={'schema':'remeizu.free-hosted-native-run.v1','run_id':'123','source_lock_sha256':'0'*64,
                'full375_phone':False,'private_android_inputs':False}
        second.write_text(json.dumps(record))
        selected,parsed=complete_snapshot([first,second],'123','0'*64)
        self.assertEqual(selected,second)
        self.assertNotIn('all_public_source_tool_wheel_before_after_verified',parsed)
    def test_real_owned_process_timeout_reaps_only_spawned_process_and_keeps_logs(self):
        import os,time
        root=Path(tempfile.mkdtemp(prefix='free-native-owned-timeout-',dir='/dev/shm'))
        state=run_owned([sys.executable,'-c',"import time;print('owned timeout control',flush=True);time.sleep(30)"],
                        dict(os.environ),0.3,root,[0])
        self.assertEqual(state['termination_reason'],'timeout')
        self.assertTrue(state['owned_launcher_reaped'])
        self.assertNotEqual(state['returncode'],0)
        self.assertIn(b'owned timeout control',(root/'forge-controller.stdout').read_bytes())
    def test_cipher_capacity_counts_all_parts_without_assuming_compression(self):
        size=3*GIB
        bound=cipher_upper_bound({'outputs':[{'bytes':size}]})
        self.assertGreater(bound,size)
        self.assertGreater(bound,64*1024**2)
    def test_foreign_branch_or_repeated_attempt_refused_before_source_fetch(self):
        base={'GITHUB_REPOSITORY':'ReMeizu/build-infra','GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'push',
              'GITHUB_RUN_ATTEMPT':'1','GITHUB_REF':'refs/heads/codex/free-native-20261009'}
        for changes in ({'GITHUB_REF':'refs/heads/main'},{'GITHUB_RUN_ATTEMPT':'2'},
                        {'GITHUB_REPOSITORY':'foreign/repo'},{'GITHUB_EVENT_NAME':'pull_request'}):
            with self.assertRaisesRegex(ValueError,'exact owned free-native branch'):
                checked_public_job(dict(base,**changes))
    def test_authenticated_or_private_transport_refused(self):
        for url in ('https://token@github.com/ReMeizu/build-infra','http://github.com/a/b','https://github.com/a/b?token=secret','https://drive.google.com/a','https://github.com/a/b#credentials'):
            with self.assertRaises(ValueError):public_url(url)
    def test_public_pinned_source_host_accepted(self):
        url='https://github.com/openharmony/third_party_libusb.git'
        self.assertEqual(public_url(url),url)
    def test_full375_or_unreviewed_carrier_refused(self):
        with self.assertRaisesRegex(ValueError,'source-only public acquisition'):
            validate_lock({'schema':'fake','public_sources_only':False},{})
    def test_exact_intermediate_count_required(self):
        with self.assertRaisesRegex(ValueError,'110/95'):
            validate_lock({'schema':'remeizu.free-hosted-native-public-inputs.v1','public_sources_only':True,'private_android_inputs':False,'source_projects':87,'selected_part_count':71},{'projects':[]})
    def test_actual_public_88_72_lock_matches_exact_gn_inventory(self):
        import json
        lock=json.loads((HERE/'public_inputs.lock.json').read_text())
        inventory=json.loads((HERE/'controller/GN_INPUTS.json').read_text())
        validate_lock(lock,inventory)
        self.assertEqual(hashlib.sha256((HERE/'controller/GN_INPUTS.json').read_bytes()).hexdigest(),lock['gn_inputs_sha256'])
    def test_archive_traversal_refused_without_outside_write(self):
        root=Path(tempfile.mkdtemp(prefix='free-native-archive-negative-',dir='/dev/shm'))
        archive=root/'negative.tar'
        with tarfile.open(archive,'w') as tar:
            m=tarfile.TarInfo('../outside');m.size=4;tar.addfile(m,io.BytesIO(b'test'))
        with self.assertRaises(ValueError):extract_tool(archive,root/'output',{})
        self.assertFalse((root/'outside').exists())
    def test_archive_absolute_symlink_refused(self):
        root=Path(tempfile.mkdtemp(prefix='free-native-link-negative-',dir='/dev/shm'))
        archive=root/'negative.tar'
        with tarfile.open(archive,'w') as tar:
            m=tarfile.TarInfo('escape');m.type=tarfile.SYMTYPE;m.linkname='/etc';tar.addfile(m)
        with self.assertRaisesRegex(ValueError,'absolute symlink'):extract_tool(archive,root/'output',{})
    def test_plaintext_retention_requires_actual_source_proof(self):
        with self.assertRaisesRegex(ValueError,'verified public-source'):
            actual_policy(Path('/dev/shm/absent-native-producer'),{'source_lock_sha256':'0'*64},'0'*64)
    def test_recipe_path_injection_refused_before_output_admission(self):
        record={'public_input_acquisition_verified':True,'retention_preflight_verified':True,
                'all_public_source_tool_wheel_before_after_verified':True,'actual_forge_submitted':True,
                'compiler_termination_verified':True,
                'private_android_inputs':False,'full375_phone':False,'source_lock_sha256':'0'*64,'recipe_hash':'../android-donor'}
        with self.assertRaisesRegex(ValueError,'recipe hash'):
            actual_policy(Path('/dev/shm/absent-native-producer'),record,'0'*64)

@unittest.skipUnless(B6.is_file(),'actual frozen b6 source not present; no fabricated replacement')
class ActualWorkerSourceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=B6.read_bytes();cls.code=cls.before.decode();cls.new=transformed_worker(cls.code)
    def test_actual_b6_source_unchanged(self):
        self.assertEqual(B6.read_bytes(),self.before)
    def test_generated_actual_worker_parses_and_has_two_j2_targets(self):
        ast.parse(self.new)
        self.assertEqual(self.new.count("'-j2'"),2)
        self.assertNotIn("'-j6'",self.new)
    def test_actual_labels_and_policy_not_disabled(self):
        for label in ('//third_party/musl:soft_libc_musl_shared','//commonlibrary/c_utils/base:utils','//third_party/libhybris/hybris/common:libhybris-common','//third_party/libhybris/hybris/common:q'):
            self.assertEqual(self.new.count(label),self.code.count(label))
        tail=self.code[self.code.index("            command = [str(ninja), '-C', str(native_out), '-j6', 'images']"):]
        self.assertEqual(self.new[self.new.index("            command = [str(ninja), '-C', str(native_out), '-j2', 'images']"):],tail.replace("'-j6'","'-j2'"))
    def test_real_source_hash_checks_and_sdk_unchanged(self):
        for string in ("inputs['worker_sha256']","inputs['source_files']","inputs['tools']","source-and-official-tools-verified","native-python-dependencies-installed"):
            self.assertEqual(self.new.count(string),self.code.count(string))
    def test_original_drift_refused(self):
        with self.assertRaises(ValueError):transformed_worker(self.code.replace("available < 24*1024**3","available < 1"))

if __name__=='__main__':unittest.main(verbosity=2)
