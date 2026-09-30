#!/usr/bin/env python3
"""Acceptance-gate tests only: synthetic files, no compiler or network."""
import json
from pathlib import Path
import tempfile
import unittest

import mx6_kernel_build as build
import mx6_kernel_run as runner


class MX6Tests(unittest.TestCase):
    def pins(self):
        return json.loads((runner.HERE/'recipes/mx6-wifi-inputs.json').read_text())

    def config(self, path, replace=None):
        values = dict(build.CONFIG)
        if replace:
            values.update(replace)
        path.write_text('\n'.join(k+'='+v for k, v in values.items())+'\n')

    def outputs(self, root):
        (root/'arch/arm64/boot').mkdir(parents=True)
        (root/'arch/arm64/boot/Image.gz-dtb').write_bytes(b'\x1f\x8bsynthetic-test')
        (root/'System.map').write_text('ffffff8008081234 T rlmGetVhtCapIE\n')
        (root/'vmlinux').write_bytes(b'synthetic-test')
        self.config(root/'.config')
        for name in build.OBJECTS:
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'\x7fELF\x02\x01'+b'\x00'*10+b'\x01\x00\xb7\x00')
            path.with_name('.'+path.name+'.cmd').write_text('cmd_test := aarch64-linux-android-gcc -c source.c\n')

    def test_reviewed_pins_valid(self):
        build.validate_pins(self.pins())

    def test_pins_reject_missing_source_or_changed_target(self):
        for name in ('defconfig', 'target', 'kernel_commit', 'kernel_tree'):
            pins = self.pins(); pins[name] = 'unreviewed'
            with self.subTest(name=name), self.assertRaises(ValueError):
                build.validate_pins(pins)
        pins = self.pins(); pins['source_sha256'].pop(next(iter(pins['source_sha256'])))
        with self.assertRaises(ValueError):
            build.validate_pins(pins)

    def test_pins_reject_path_escape_unreviewed_repository_and_boolean_jobs(self):
        for field, value in [('jobs', True), ('kernel_url', 'https://example.invalid/kernel'),
                             ('toolchain_url', 'https://example.invalid/gcc')]:
            pins = self.pins(); pins[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build.validate_pins(pins)
        pins = self.pins(); pins['toolchain_sha256']['../gcc'] = 'a'*64
        with self.assertRaises(ValueError):
            build.validate_pins(pins)

    def test_source_and_compiler_bytes_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pins = self.pins()
            for mapping, parent in [('source_sha256', root/'kernel'), ('toolchain_sha256', root/'toolchain/bin')]:
                for name in pins[mapping]:
                    path = parent/name; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'synthetic-input'); pins[mapping][name] = build.sha(path)
            build.verify_inputs(root, pins)
            (root/'toolchain/bin/aarch64-linux-android-gcc').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                build.verify_inputs(root, pins)

    def test_config_requires_actual_gen3_chip_and_wifi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'.config'; self.config(path)
            self.assertEqual(build.validate_config(path), build.CONFIG)
            for key in build.CONFIG:
                self.config(path, {key: 'n'})
                with self.subTest(key=key), self.assertRaises(ValueError):
                    build.validate_config(path)

    def test_duplicate_config_symbol_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'.config'; self.config(path)
            path.write_text(path.read_text()+'CONFIG_MTK_COMBO_WIFI=y\n')
            with self.assertRaises(ValueError):
                build.validate_config(path)

    def test_accept_actual_object_layout_and_link_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.outputs(root)
            outputs = build.validate_outputs(root)
            self.assertTrue(set(build.OBJECTS).issubset(outputs))
            self.assertTrue(set(outputs).issubset(runner.required_artifacts()))

    def test_missing_or_wrong_arch_object_is_rejected(self):
        for payload in (b'', b'\x7fELF\x01\x01'+b'\x00'*14):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); self.outputs(root); (root/build.OBJECTS[0]).write_bytes(payload)
                with self.assertRaises(ValueError):
                    build.validate_outputs(root)

    def test_command_without_cross_compiler_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.outputs(root); obj = root/build.OBJECTS[0]
            obj.with_name('.'+obj.name+'.cmd').write_text('fake\n')
            with self.assertRaises(ValueError):
                build.validate_outputs(root)

    def test_link_without_vht_helper_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.outputs(root); (root/'System.map').write_text('ffffff8008081234 T unrelated\n')
            with self.assertRaises(ValueError):
                build.validate_outputs(root)

    def test_forge_recipe_is_networkless_and_read_only(self):
        recipe = runner.forge.recipe_from_dict({'image_tag': 'androidforge/build-kernel:kernel-gcc49',
            'image_id': 'sha256:'+'a'*64, 'build_env_key': 'kernel-gcc49', 'source_mount_path': '/mnt/forge/source',
            'output_dir_in_container': '/workspace/out', 'command': ['python3', '/workspace/src/.forge/mx6_kernel_build.py'],
            'env': {'FORGE_KERNEL_JOBS': '4'}, 'idempotency_key': 'test-mx6', 'timeout_seconds': 1320,
            'execution_profile': 'cloud-mounted', 'scratch_mount_path': '/mnt/forge', 'container_user': '1001:1001',
            'required_artifacts': runner.required_artifacts()})
        argv = runner.forge.build_docker_argv(recipe, Path('/mnt/forge/evidence/test'), 'test')
        self.assertIn('--network=none', argv)
        self.assertIn('--user=1001:1001', argv)
        self.assertIn('/mnt/forge/source:/workspace/src:ro', argv)
        self.assertIn('3.18', recipe.build_env_contract['kernel_versions'])


if __name__ == '__main__':
    unittest.main()
