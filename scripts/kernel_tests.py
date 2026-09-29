#!/usr/bin/env python3
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import kernel_build as build
import kernel_run as runner
from kernel_forge import forge


class KernelTests(unittest.TestCase):
    def archive(self, path, entries):
        with tarfile.open(path,'w:gz') as stream:
            for name,data,link in entries:
                member=tarfile.TarInfo(name)
                if link is not None:
                    member.type=tarfile.SYMTYPE;member.linkname=link;stream.addfile(member)
                else:
                    member.size=len(data);stream.addfile(member,io.BytesIO(data))

    def test_archive_accepts_safe_files_and_relative_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);a=p/'a.tar.gz'
            self.archive(a,[('bin/compiler',b'tool',None),('bin/alias',b'','compiler')])
            runner.extract(a,p/'source')
            self.assertEqual((p/'source/bin/alias').read_bytes(),b'tool')

    def test_archive_rejects_path_and_link_escape_and_git_metadata(self):
        for name,link in [('../escape',None),('/escape',None),('.git/config',None),('bin/alias','../../escape')]:
            with self.subTest(name=name,link=link),tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);a=p/'a.tar.gz';self.archive(a,[(name,b'bad',link)])
                with self.assertRaises(ValueError):runner.extract(a,p/'source')

    def test_source_table_parser_rejects_extra_expression(self):
        source='static x rows[] = { { REGFLAG_DELAY, 5, { 0x12 } }, };'
        self.assertEqual(build.table_bytes(source,'rows')[:6],b'\xfc\x00\x00\x00\x05\x12')
        with self.assertRaises(ValueError):build.table_bytes(source.replace('}, };','}, evil(), };'),'rows')

    def test_launcher_preserved_and_networkless_nonroot_contract(self):
        actual=hashlib.sha256((runner.HERE/'vendor/forge/forge_ephemeral_build.py').read_bytes()).hexdigest()
        self.assertEqual(actual,'9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8')
        recipe=forge.recipe_from_dict({'image_tag':'androidforge/build-kernel:kernel-gcc49','image_id':'sha256:'+'a'*64,
            'build_env_key':'kernel-gcc49','source_mount_path':'/mnt/forge/source','output_dir_in_container':'/workspace/out',
            'command':['python3','/workspace/src/.forge/kernel_build.py'],'env':{'FORGE_KERNEL_JOBS':'2'},
            'idempotency_key':'test','timeout_seconds':600,'execution_profile':'cloud-mounted',
            'scratch_mount_path':'/mnt/forge','container_user':'1001:1001','required_artifacts':['object.o']})
        args=forge.build_docker_argv(recipe,Path('/mnt/forge/evidence/test'),'test')
        self.assertIn('--network=none',args);self.assertIn('--user=1001:1001',args)
        self.assertIn('/mnt/forge/source:/workspace/src:ro',args)
        self.assertEqual(recipe.build_env_contract['jdk'],None)
        self.assertEqual(recipe.env['KBUILD_BUILD_USER'],'nomore')

    def test_receipt_hash_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'obj').write_bytes(b'object')
            (p/'artifacts.json').write_text(json.dumps({'obj':build.sha(p/'obj')}))
            (p/'SUCCESS').write_text(json.dumps({'artifacts_sha256':build.sha(p/'artifacts.json'),'artifacts_count':1}))
            runner.verify_receipt(p)
            (p/'obj').write_bytes(b'changed')
            with self.assertRaises(ValueError):runner.verify_receipt(p)


if __name__=='__main__':unittest.main()
