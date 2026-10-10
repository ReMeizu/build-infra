"""Structural source and actual RAM artifact controls; never run a compiler."""
import hashlib
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_overlay_worker as worker
import overlay_io as io


class OverlayWorkerTests(unittest.TestCase):
    def test_exact_original_transformation_preserves_real_commands_and_targets(self):
        original = (worker.PARENT / 'controller/native_gn_worker.py').read_bytes()
        code = worker.transformed_worker(original)
        self.assertEqual(code.count("'-j2'"), 2)
        self.assertIn("'--build-only-gn'", code)
        self.assertIn("'-j2', 'images'", code)
        for label in ('//third_party/musl:soft_libc_musl_shared', '//commonlibrary/c_utils/base:utils',
                      '//third_party/libhybris/hybris/common:libhybris-common', '//third_party/libhybris/hybris/common:q'):
            self.assertIn(label, code)
        self.assertNotIn('p.relative_to(out)', code)
        self.assertIn("if f.read(2) != b'\\x53\\xef'", code)
        self.assertIn("verify_file(original, item)", code)
        with self.assertRaises(ValueError):
            worker.transformed_worker(original + b'\n')

    def test_partial_selection_or_empty_children_cannot_be_full_source(self):
        with self.assertRaises(ValueError):
            io.require_full_source({'full375_source_closed': False})
        inputs = {'full375_source_closed': True, 'original375_source_bindings_verified': True,
                  'original375_selected_parts': {str(i): {} for i in range(375)},
                  'actual_selected_parts': {str(i): {} for i in range(375)},
                  'original_dynamic_parts': ['product_m5c:product_m5c', 'device_hybris_generic:device_hybris_generic']}
        with self.assertRaisesRegex(ValueError, 'actual registration'):
            io.require_full_source(inputs)
        inputs['actual_selected_parts'].update({key: {} for key in inputs['original_dynamic_parts']})
        io.require_full_source(inputs)
        with self.assertRaises(ValueError):
            io.require_full_source(dict(inputs, uninitialized_gitlinks=[{'path': 'child'}]))
        inputs['actual_selected_parts']['2'] = {'features': {'changed': True}}
        with self.assertRaises(ValueError):
            io.require_full_source(inputs)

    def test_same_RAM_generated_hardlink_and_lower_only_or_wrong_upper_refusal(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            ram = Path(folder);source = ram/'merged';upper = ram/'upper';output = ram/'forge'
            for p in (source/'out', upper/'out', output):p.mkdir(parents=True)
            logical = source/'out/image';logical.write_bytes(b'actual RAM output')
            with self.assertRaises(ValueError):
                io.retain_generated(logical, output, source, upper, ram)
            physical = upper/'out/image';physical.write_bytes(logical.read_bytes())
            name = io.retain_generated(logical, output, source, upper, ram)
            self.assertEqual((output/name).stat().st_ino, physical.stat().st_ino)
            self.assertEqual(io.retain_generated(logical, output, source, upper, ram), name)
            physical.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                io.retain_generated(logical, output, source, upper, ram)

    def test_RO_source_does_not_relax_original_prepare_or_image_reserves(self):
        row = {'cpu_affinity': 4, 'cpu_quota': None, 'available_bytes': 12*io.GIB, 'tmpfs_free_bytes': 10*io.GIB}
        self.assertFalse(io.admit_values(row, 'prepare', 349008915, 1024)['full375_fit_proven'])
        for change in ({'cpu_affinity': 1}, {'available_bytes': 12*io.GIB-1}, {'tmpfs_free_bytes': 6*io.GIB}):
            with self.assertRaises(ValueError):
                io.admit_values(dict(row, **change), 'prepare', 349008915, 1024)
        with self.assertRaises(ValueError):
            io.admit_values(dict(row, tmpfs_free_bytes=5*io.GIB-1), 'images', 349008915, 1024)

    def test_output_root_alias_cannot_turn_original_source_into_generated_artifact(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            ram = Path(folder);source = ram/'merged';upper = ram/'upper';output = ram/'forge'
            for p in (source, upper, output):p.mkdir()
            (source/'original').mkdir();(source/'original/file').write_bytes(b'original source')
            (source/'out').symlink_to('original', target_is_directory=True)
            with self.assertRaises(ValueError):
                io.retain_generated(source/'out/file', output, source, upper, ram)

    def test_retained_parent_alias_cannot_escape_real_Forge_artifact_walk(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            ram = Path(folder);source = ram/'merged';upper = ram/'upper';output = ram/'forge'
            for p in (source/'out', upper/'out', output):p.mkdir(parents=True)
            for p in (source/'out/file', upper/'out/file'):p.write_bytes(b'actual output')
            (output/'native-artifacts').symlink_to(upper, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'ancestors'):
                io.retain_generated(source/'out/file', output, source, upper, ram)

    def test_unrelated_overlay_or_extra_source_cannot_be_consumed(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            merged = Path(folder);(merged/'source').write_text('source')
            inputs = {'overlay_host_paths': {'lower': '/host/ram/lower', 'upper': '/host/ram/upper', 'work': '/host/ram/work'}}
            rows = [{'path': 'source'}]
            correct = b'rw,lowerdir=/host/ram/lower,upperdir=/host/ram/upper,workdir=/host/ram/work'
            with patch.object(io.subprocess, 'check_output', return_value=correct):
                io.verify_overlay_binding(merged, inputs, rows)
                (merged/'intruder.sh').write_text('unlisted')
                with self.assertRaisesRegex(ValueError, 'unlisted'):
                    io.verify_overlay_binding(merged, inputs, rows)
            with patch.object(io.subprocess, 'check_output', return_value=correct.replace(b'/host/ram/upper', b'/foreign/upper')):
                with self.assertRaisesRegex(ValueError, 'does not bind'):
                    io.verify_overlay_binding(merged, inputs, rows)

    def test_separate_tmpfs_upper_cannot_use_the_output_free_space(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as folder:
            ram = Path(folder);upper = ram/'upper';output = ram/'forge'
            upper.mkdir();output.mkdir()
            original_stat = Path.stat
            def different_device(path, *args, **kwargs):
                actual = original_stat(path, *args, **kwargs)
                if path == upper:
                    values = list(actual);values[2] += 1
                    return type(actual)(values)
                return actual
            with patch.object(Path, 'stat', different_device):
                with self.assertRaisesRegex(ValueError, 'share'):
                    io.require_shared_ram(output, ram, upper)


if __name__ == '__main__':
    unittest.main(verbosity=2)
