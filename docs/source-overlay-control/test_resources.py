"""Real filesystem measurements and refusal controls; no build commands."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import resources
import run_control


class RunnerResourcesTests(unittest.TestCase):
    def test_actual_disk_and_ram_are_independent_and_same_disk_is_not_added(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as ram:
            result = resources.snapshot({'runner_temp': Path('/tmp'), 'workspace': Path('/tmp'), 'ram': Path(ram)})
        self.assertIn(['runner_temp', 'workspace'], result['same_filesystem_pairs'])
        self.assertGreater(result['memory_bytes']['MemTotal'], 0)
        self.assertGreater(result['filesystems']['ram']['capacity_bytes'], 0)
        self.assertFalse(result['full375_fit_proven'])
        self.assertFalse(result['compiler_peak_measured'])

    def test_missing_or_wrong_kernel_units_cannot_become_capacity(self):
        for body in ('MemTotal: 16 GB\n', 'MemTotal: 1024 kB\n',
                     'MemTotal: 1 kB\nMemAvailable: 2 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n'):
            with self.assertRaises(ValueError):
                resources.memory_bytes(body)

    def test_insufficient_disk_refuses_without_counting_ram_or_second_disk_alias(self):
        measured = {'schema': 'remeizu.actual-runner-readonly-resources.v1',
                    'filesystems': {'runner_temp': {'available_bytes': 100, 'readonly': False},
                                    'workspace': {'available_bytes': 100},
                                    'ram': {'available_bytes': 10000}}}
        with self.assertRaisesRegex(ValueError, 'insufficient'):
            resources.admit_lower_capacity(measured, 101, 0)
        with self.assertRaisesRegex(ValueError, 'insufficient'):
            resources.admit_lower_capacity(measured, 99, 2)
        self.assertFalse(resources.admit_lower_capacity(measured, 99, 1)['full375_fit_proven'])

    def test_readonly_or_missing_disk_witness_refuses_source_capacity(self):
        for disk in ({'available_bytes': 100}, {'available_bytes': 100, 'readonly': True},
                     {'available_bytes': True, 'readonly': False}):
            measured = {'schema': 'remeizu.actual-runner-readonly-resources.v1',
                        'filesystems': {'runner_temp': disk}}
            with self.assertRaisesRegex(ValueError, 'writable disk'):
                resources.admit_lower_capacity(measured, 1, 0)

    def test_expected_bytes_require_explicit_positive_integer_and_reserve(self):
        for source, reserve in ((True, 0), (0, 0), (-1, 0), (1, -1), (1.0, 0)):
            with self.assertRaises(ValueError):
                resources.admit_lower_capacity({}, source, reserve)

    def test_final_counter_failure_refuses_but_preserves_actual_filesystem_proof(self):
        result = {'status': 'ACTUAL_SOURCE_FILESYSTEM_CONTROL_PASS_NOT_FULL375',
                  'actual_Forge_returncode': 0, 'actual_artifacts': {'probe': 'original-digest'}}
        with patch.object(resources, 'snapshot', side_effect=OSError('secret path must not be exposed')):
            run_control.final_resources(result, {})
        self.assertEqual(result['status'], 'SOURCE_CONTROL_REFUSED')
        self.assertEqual(result['fixed_error_code'], 'RUNNER_RESOURCE_MEASUREMENT_REFUSED')
        self.assertEqual(result['resources_after_control_refused'], 'OSError')
        self.assertEqual(result['actual_artifacts'], {'probe': 'original-digest'})
        self.assertNotIn('secret', str(result))


if __name__ == '__main__':
    unittest.main(verbosity=2)
