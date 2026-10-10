import json
from pathlib import Path
import tempfile
import unittest
import full_profile


class FullProfileTests(unittest.TestCase):
    def fixture(self):
        root = Path(full_profile.__file__).parent
        proof = json.loads((root/full_profile.COVERAGE_NAME).read_text())
        return root, {'full_phone_profile_kind': 'canonical-full-gui-a2', 'full_phone_source_closed': True,
                      'canonical_full_phone_source_bindings_verified': True,
                      'actual_selected_parts': proof['actual_selected_parts'],
                      'original375_selected_parts': proof['original375_requests'],
                      'original_dynamic_parts': proof['original_dynamic_parts']}

    def test_actual_reviewed_profile_preserves_requests_and_distinguishes_counts(self):
        root, inputs = self.fixture();result = full_profile.require_profile(inputs, root)
        self.assertEqual(result['original_requests'], 375)
        self.assertEqual(result['actual_selected_parts'], 366)
        self.assertFalse(result['native_GN_or_images_proven_by_profile'])

    def test_partial_GUI_or_changed_flag_or_dynamic_provider_refuses(self):
        root, inputs = self.fixture()
        for key in ('arkui:ace_engine', 'device_hybris_generic:device_hybris_generic'):
            actual = dict(inputs['actual_selected_parts']);actual.pop(key)
            with self.assertRaises(ValueError):
                full_profile.require_profile(dict(inputs, actual_selected_parts=actual), root)
        actual = dict(inputs['actual_selected_parts']);actual['arkui:ace_engine'] = {'features': {'ace_engine_feature_enable_web': False}}
        with self.assertRaises(ValueError):full_profile.require_profile(dict(inputs, actual_selected_parts=actual), root)
        with self.assertRaises(ValueError):full_profile.require_profile(dict(inputs, full_phone_source_closed=False), root)
        with self.assertRaises(ValueError):full_profile.require_profile(dict(inputs, uninitialized_gitlinks=[{'path':'missing-child'}]), root)

    def test_tampered_coverage_cannot_admit_profile(self):
        root, inputs = self.fixture()
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            path = Path(folder)/full_profile.COVERAGE_NAME;path.write_bytes((root/full_profile.COVERAGE_NAME).read_bytes()+b'\n')
            with self.assertRaises(ValueError):full_profile.require_profile(inputs, Path(folder))


if __name__ == '__main__':unittest.main(verbosity=2)
