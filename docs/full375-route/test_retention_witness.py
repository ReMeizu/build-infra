"""Source/identity fixtures only; no Docker, GN, Ninja or target compiler."""
import copy,hashlib,importlib.util,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest import mock
import run_full_phone as run
import container_image_witness as images
import native_target_witness as targets
import producer_metadata as metadata

class WitnessControls(unittest.TestCase):
    def test_actual_official_constructor_and_old_digest_refusal(self):
        path=run.ROOT/'vendor/forge/forge_ephemeral_build.py';self.assertEqual(run.sha(path),run.FORGE_SHA)
        spec=importlib.util.spec_from_file_location('actual_constructor_control',path);forge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=forge;spec.loader.exec_module(forge)
        recipe=run.make_recipe(Path('/owned/controller'),Path('/owned/original'),Path('/owned/ram'),'androidforge/build-full-phone-123:android-9','123','a'*64,600,'b'*64)
        model=forge.recipe_from_dict(recipe);self.assertEqual(model.build_env_key,'android-9');self.assertEqual(model.recipe_hash(),hashlib.sha256(model.canonical_json().encode()).hexdigest())
        with self.assertRaisesRegex(ValueError,'requires image tag'):forge.recipe_from_dict(dict(recipe,image_tag='sha256:'+'c'*64))
        with self.assertRaises(ValueError):forge.recipe_from_dict(dict(recipe,image_tag='host'))

    def image_fixture(self):
        rh='a'*64;inv='b'*32;cid='c'*64;tag='androidforge/build-full-phone-123:android-9';image='sha256:'+'d'*64;name='forge-eph-'+rh[:12]+'-'+inv[:12]
        state={'recipe_hash':rh,'invocation':inv,'container_id':cid,'container_name':name}
        data=[{'Id':cid,'Name':'/'+name,'Image':image,'Config':{'Image':tag,'Labels':{'androidforge.invocation':inv,'androidforge.recipe_sha256':rh}}}]
        return state,data,rh,image,tag

    def test_full_id_name_labels_image_and_config_image_required(self):
        state,data,rh,image,tag=self.image_fixture();self.assertEqual(images.attest(state,data,rh,image,tag)['actual_image_id'],image)
        for field in ('Id','Name','Image','tag','owner','recipe'):
            wrong=copy.deepcopy(data)
            if field in ('Id','Name','Image'):wrong[0][field]='wrong'
            elif field=='tag':wrong[0]['Config']['Image']='foreign:android-9'
            else:wrong[0]['Config']['Labels']['androidforge.invocation' if field=='owner' else 'androidforge.recipe_sha256']='wrong'
            with self.subTest(field=field),self.assertRaises(ValueError):images.attest(state,wrong,rh,image,tag)

    def test_observer_preserves_raw_inspect_and_missing_is_not_proof(self):
        state,data,rh,image,tag=self.image_fixture()
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            out=Path(tmp);folder=out/'.forge-container';folder.mkdir();(folder/(state['invocation']+'.json')).write_text(json.dumps(state));raw=json.dumps(data).encode();cancelled=[0];forge=type('Forge',(),{'CONTAINER_METADATA_DIR':'.forge-container'})()
            with mock.patch.object(images.subprocess,'run',return_value=type('Result',(),{'returncode':0,'stdout':raw})()):
                observer=images.ImageObserver(forge,out,rh,image,tag,cancelled);observer.start()
                for _ in range(100):
                    if observer.rows:break
                    time.sleep(.01)
                proof=observer.finish()
            self.assertTrue(proof['all_observed_owned_images_verified']);row=proof['owned_container_images'][0]['raw_inspect'];self.assertEqual((out/row['path']).read_bytes(),raw);self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(cancelled,[0])
            empty=out/'empty';empty.mkdir();observer=images.ImageObserver(forge,empty,rh,image,tag,[0]);observer.start();self.assertFalse(observer.finish()['all_observed_owned_images_verified'])

    def test_declared_labels_bind_exact_linked_files_and_tamper_refuses(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            root=Path(tmp);source=root/'source';native=source/'out/m5c';native.mkdir(parents=True);out=root/'forge';out.mkdir();files=[]
            for index,label in enumerate(targets.LABELS):
                relative='lib'+str(index)+'.so';file=native/relative;file.write_bytes(b'explicit linked-output fixture'+bytes([index]));name='native-artifacts/out/m5c/'+relative;artifact=out/name;artifact.parent.mkdir(parents=True,exist_ok=True);os.link(file,artifact);files.append({'path':name,'bytes':file.stat().st_size,'sha256':targets.sha(file)})
                targets.capture(out,'e'*64,label,['gn','desc',str(native),label,'outputs','--format=json'],json.dumps({label:{'outputs':['//out/m5c/'+relative]}}),[relative])
            result=targets.complete(out,'e'*64,files,source,native);self.assertEqual(set(result['labels']),set(targets.LABELS));self.assertEqual(len(result['actual_files']),4)
            (out/files[0]['path']).write_bytes(b'wrong')
            with self.assertRaises(ValueError):targets.complete(out,'e'*64,files,source,native)

    def test_wrong_or_empty_declared_target_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);label=targets.LABELS[0];argv=['gn','desc','out',label,'outputs','--format=json']
            with self.assertRaises(ValueError):targets.capture(out,'e'*64,label,argv,json.dumps({'//fake:target':{'outputs':['//out/a']}}),['a'])
            with self.assertRaises(ValueError):targets.capture(out,'e'*64,label,argv,json.dumps({label:{'outputs':[]}}),[])

    def test_metadata_readback_missing_records_and_outside_alias(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            job=Path(tmp)/'job';original=job/'public-inputs/original';original.mkdir(parents=True);gn=original/'GN_INPUTS.json';gn.write_text('{"fixture_source_only":true}');out=job/'ram/forge'/('a'*64);out.mkdir(parents=True);record={'run_id':'123','source_lock_sha256':'b'*64,'retention_scope':'NATIVE_FORGE'}
            rows=metadata.preserve(job,out,record);manifest=json.loads((out/'FULL_PHONE_METADATA/MANIFEST.json').read_text());self.assertIn('RECIPE.json',manifest['missing_actual_records']);row=next(r for r in rows if r['path'].endswith('/ACQUIRED_GN_INPUTS.json'));self.assertEqual(row['sha256'],metadata.sha(gn));self.assertEqual((out/row['path']).read_bytes(),gn.read_bytes())
            outside=Path(tmp)/'outside';outside.write_text('not owned');gn.unlink();gn.symlink_to(outside)
            with self.assertRaises(ValueError):metadata.preserve(job,out,record)

    def test_transformed_worker_preserves_commands_and_records_existing_calls(self):
        from make_overlay_worker import transformed_worker
        code=transformed_worker((run.HERE/'controller/native_gn_worker.py').read_bytes())
        for label in targets.LABELS:self.assertIn(repr(label),code)
        self.assertIn("'desc', str(native_out), label, 'outputs', '--format=json'",code);self.assertIn("'-j2', 'images'",code)
        self.assertIn('capture_target(out, sha(manifest), label, command, described.stdout, relative_outputs)',code);self.assertIn('complete_targets(out, sha(manifest), native_libraries, source, native_out)',code)

if __name__=='__main__':unittest.main()
