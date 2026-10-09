import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE/'scripts'))
from component_manifest import artifacts, validate
from component_compile import verify_symbol_table

class U10ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((HERE/'recipes/components/u10-devapc-native.json').read_text())

    def test_all_historical_profiles_still_validate(self):
        for path in (HERE/'recipes/components').glob('*.json'):
            validate(json.loads(path.read_text()))

    def test_pin_and_full_artifacts(self):
        p = validate(self.profile)
        self.assertEqual(p['jobs'],2)
        self.assertEqual(p['expected_config_sha256'], '06e84cb1b7540e8e715a25b472b0ae4f33a72d434fe8034de1ec6b6ba769cf4e')
        names = artifacts(p)
        for name in ['arch/arm64/boot/Image', 'vmlinux','System.map','kernel.config','compiled-devapc-table.json','objects/drivers/misc/mediatek/devapc/mt6755/devapc.o']:
            self.assertIn(name,names)
        self.assertTrue(p['require_baseline_dtb'])
        import hashlib
        data=(HERE/p['config_seed']['file']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),p['config_seed']['sha256'])
        for row in ['CONFIG_MTK_CCCI_LEGACY_PORT_ABI5=y','CONFIG_MEIZU_U10_DEVAPC_STOCK_LAYOUT=y','CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW=y','CONFIG_MTK_LCM_PHYSICAL_ROTATION="0"']:
            self.assertIn(row,data.decode().splitlines())

    def test_wrong_seed_other_board_and_table_rejected(self):
        for key, change in [('seed',None),('board',None),('count',None),('dtbbool',None)]:
            p=copy.deepcopy(self.profile)
            if key=='seed':p['config_seed']['sha256']='0'*64
            elif key=='board':p['device']='u20';p['platform']='mt6755'
            elif key=='count':p['required_symbol_table']['bytes']=158*16
            else:p['require_baseline_dtb']='true'
            with self.assertRaises(ValueError):validate(p)

    def test_actual_nm_format_and_failure_controls(self):
        table=self.profile['required_symbol_table']
        good='ffffffc001222000 00000000000009d0 d devapc_devices\n'
        self.assertEqual(verify_symbol_table(good,table)['count'],157)
        for bad in [good.replace('09d0','09e0'), '',good+good,good.replace(' d ',' T '), 'garbage devapc_devices\n']:
            with self.assertRaises(ValueError):verify_symbol_table(bad,table)

    def test_actual_cgroup_argv_follows_two_job_bound(self):
        old=sys.modules.get('kernel_forge')
        stub=types.ModuleType('kernel_forge')
        stub.forge=types.SimpleNamespace(BUILD_ENV_CONTRACTS={},build_docker_argv=lambda *args:['docker','run','--network=none'])
        sys.modules['kernel_forge']=stub
        try:
            spec=importlib.util.spec_from_file_location('u10_bound_fixture',HERE/'scripts/component_forge.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            r=types.SimpleNamespace(build_env_key='component-kernel-gcc49',env={'FORGE_KERNEL_JOBS':'2'})
            argv=module.bounded_argv(r,Path('/out'),'fixture')
            for option in ['--cpus=2','--memory=5g','--memory-swap=6g','--pids-limit=1024','--network=none']:self.assertIn(option,argv)
            r.env['FORGE_KERNEL_JOBS']='64'
            with self.assertRaises(ValueError):module.bounded_argv(r,Path('/out'),'fixture')
        finally:
            if old is None:del sys.modules['kernel_forge']
            else:sys.modules['kernel_forge']=old

if __name__=='__main__':unittest.main()
