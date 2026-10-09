import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / 'scripts'))
from component_manifest import artifacts, validate, validate_config_seed

NEW_HASH = '930341e6f7558b4f2d05a903b82f14309295e363f26e80a9c2ee0b57c3eec854'
OLD_HASH = '06e84cb1b7540e8e715a25b472b0ae4f33a72d434fe8034de1ec6b6ba769cf4e'

class U10UprightTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((HERE / 'recipes/components/u10-upright-native.json').read_text())
        self.data = (HERE / self.profile['config_seed']['file']).read_bytes()

    def test_exact_single_change_from_accepted_config(self):
        baseline = (HERE / 'recipes/u10-devapc-selected.config').read_bytes()
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), OLD_HASH)
        self.assertEqual(self.data, baseline.replace(b'CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW=y\n',
                         b'# CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW is not set\n'))
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), NEW_HASH)
        validate_config_seed(self.profile, self.data)

    def test_all_old_profiles_remain_valid_with_original_rotation(self):
        for path in (HERE / 'recipes/components').glob('*.json'):
            p = validate(json.loads(path.read_text()))
            if p.get('config_seed'):
                validate_config_seed(p, (HERE / p['config_seed']['file']).read_bytes())
        old = json.loads((HERE / 'recipes/components/u10-native.json').read_text())
        self.assertEqual(old['expected_config_sha256'], OLD_HASH)
        with self.assertRaises(ValueError):
            validate_config_seed(old, self.data)

    def test_changed_board_defaults_fail_even_with_self_consistent_new_hash(self):
        for old, new in [
            (b'# CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW is not set', b'CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW=y'),
            (b'CONFIG_MTK_LCM_PHYSICAL_ROTATION="0"', b'CONFIG_MTK_LCM_PHYSICAL_ROTATION="180"'),
            (b'CONFIG_MTK_CCCI_LEGACY_PORT_ABI5=y', b'# CONFIG_MTK_CCCI_LEGACY_PORT_ABI5 is not set'),
            (b'CONFIG_MEIZU_U10_DEVAPC_STOCK_LAYOUT=y', b'# CONFIG_MEIZU_U10_DEVAPC_STOCK_LAYOUT is not set'),
        ]:
            self.assertEqual(self.data.count(old), 1)
            changed = self.data.replace(old, new)
            with self.assertRaises(ValueError): validate_config_seed(self.profile, changed)
            p = copy.deepcopy(self.profile)
            p['config_seed']['sha256'] = p['expected_config_sha256'] = hashlib.sha256(changed).hexdigest()
            with self.assertRaises(ValueError): validate(p)

    def test_old_new_seed_paths_and_hashes_cannot_be_crossed(self):
        for file, digest in [('recipes/u10-devapc-selected.config', NEW_HASH),
                             ('recipes/u10-upright-selected.config', OLD_HASH),
                             ('recipes/unreviewed.config', NEW_HASH)]:
            p = copy.deepcopy(self.profile)
            p['config_seed'] = {'file': file, 'sha256': digest}
            p['expected_config_sha256'] = digest
            with self.assertRaises(ValueError): validate(p)

    def test_native_display_objects_and_free_workflow_route(self):
        p = validate(self.profile)
        self.assertEqual(p['jobs'], 2)
        self.assertEqual(p['required_symbol_table'], {'symbol': 'devapc_devices', 'bytes': 157 * 16})
        self.assertTrue(p['require_baseline_dtb'])
        for name in ['ddp_ovl', 'primary_display', 'mtk_disp_mgr']:
            self.assertIn('objects/drivers/misc/mediatek/video/mt6755/' + name + '.o', artifacts(p))
        text = (HERE / '.github/workflows/blacksmith.yml').read_text()
        self.assertIn('          - u10-upright-native\n', text)
        component = text[text.index('\n  component:'):]
        self.assertIn('runs-on: ubuntu-24.04', component)
        self.assertIn("inputs.mode == 'component'", component)
        self.assertNotIn('blacksmith-', component)

if __name__ == '__main__': unittest.main()
