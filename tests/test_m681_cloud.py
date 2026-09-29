import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import m681_manifest as M
import m681_compile as C
import m681_cloud_run as R
import provision_scratch as P


def complete_manifest():
    m = json.loads((ROOT / 'recipes/m681-full-inputs.json').read_text())
    m['ready'] = m['source_license_reviewed'] = True
    m['source']['commit'] = 'a' * 40
    m['source']['tree'] = 'b' * 40
    for k in m['source']['files_sha256']: m['source']['files_sha256'][k] = 'c' * 64
    m['config']['fragment_sha256'] = m['config']['generated_sha256'] = 'c' * 64
    m['container']['image_id'] = 'sha256:' + 'd' * 64
    return m


class M681CloudTest(unittest.TestCase):
    def test_unready_manifest_rejected_before_network_or_docker(self):
        m = complete_manifest(); m['ready'] = False
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'unready.json'; manifest.write_text(json.dumps(m))
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/m681_cloud_run.py'), '--manifest', str(manifest), '--validate-only'],
                                    cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('public M681 immutable inputs are not ready', result.stderr)

    def test_complete_pins_and_cloud_contract(self):
        m = M.validate(complete_manifest())
        recipe = R.recipe_for(m, Path('/mnt/forge/source'), Path('/mnt/forge'), 'fixture')
        parsed = R.forge.recipe_from_dict(recipe)
        self.assertEqual(parsed.image_id, m['container']['image_id'])
        self.assertEqual(parsed.execution_profile, 'cloud-mounted')
        self.assertEqual(parsed.container_user, '1001:1001')
        self.assertFalse(parsed.extra_mounts)
        self.assertEqual(parsed.env['OUT_DIR'], '/workspace/scratch/out')
        self.assertIn('vmlinux', parsed.required_artifacts)
        self.assertEqual(len([p for p in parsed.required_artifacts if p.startswith('objects/')]), 18)

    def test_preparation_accepts_dynamic_container_and_config_then_pins_before_full_build(self):
        m = complete_manifest()
        m['container']['image_id'] = m['config']['generated_sha256'] = None
        M.validate(m)  # Public source/base/recipe hashes are ready before allocation.
        m['container']['image_id'] = 'sha256:' + 'f' * 64
        recipe = R.recipe_for(m, Path('/mnt/forge/source'), Path('/mnt/forge'), 'fixture', config_only=True)
        parsed = R.forge.recipe_from_dict(recipe)
        self.assertEqual(parsed.timeout_seconds, 300)
        self.assertEqual(parsed.command[-1], '--config-only')
        self.assertEqual(parsed.required_artifacts, ['kernel.config', 'config-proof.json', 'kernel-build.log'])
        m['config']['generated_sha256'] = '9' * 64
        full = R.forge.recipe_from_dict(R.recipe_for(m, Path('/mnt/forge/source'), Path('/mnt/forge'), 'fixture'))
        self.assertEqual(full.image_id, parsed.image_id)
        self.assertNotIn('--config-only', full.command)
        self.assertIn('vmlinux', full.required_artifacts)
        self.assertEqual(full.timeout_seconds, 1800)

    def test_pin_paths_target_budget_and_hardware_claim_rejected(self):
        good = complete_manifest()
        for mutate in (
            lambda m: m['source'].update(commit='mt6755-4.9'),
            lambda m: m['source'].update(tree=None),
            lambda m: m['source']['files_sha256'].update({'../private': 'a' * 64}),
            lambda m: m['source']['files_sha256'].update({'.omc/state.json': 'a' * 64}),
            lambda m: m['toolchain'].update(url='file:///srv/private'),
            lambda m: m.update(jobs=16),
            lambda m: m.update(timeout_seconds=3600),
            lambda m: m.update(targets=['drivers/iio/imu/inv_mpu_m681/inv-mpu-iio.o']),
            lambda m: m.update(flash_ready=True),
            lambda m: m['container'].update(base_image_digest='ubuntu:20.04'),
            lambda m: m['config'].update(generated_sha256='mutable'),
        ):
            with self.subTest(mutate=mutate):
                m = copy.deepcopy(good); mutate(m)
                with self.assertRaises(ValueError): M.validate(m)

    def test_full_normal_graph_has_no_direct_objects_or_extra_flags(self):
        setup, config, build = C.commands(Path('/workspace/src'), Path('/workspace/scratch/out'), complete_manifest())
        self.assertEqual(setup[-1], 'm681_49_a13_defconfig')
        self.assertEqual(config[-1], 'olddefconfig')
        self.assertEqual(build[-2:], ['Image.gz-dtb', 'vmlinux'])
        self.assertFalse(any(x.endswith('.o') or x.startswith('KCFLAGS=') for x in build))
        self.assertIn('MTK_PLATFORM=mt6755', build)
        self.assertIn('-j8', build)

    def test_selection_and_factory_board_guards(self):
        fragment = 'CONFIG_INV_MPU_IIO=y\n# CONFIG_INV_MPU_M681_FACTORY_CALIBRATION is not set\n'
        generated = fragment + 'CONFIG_MACH_MT6755=y\nCONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE=y\nCONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE_NAMES="' + M.DTB + '"\n'
        self.assertTrue(M.check_config(fragment, generated)['board_guards_retained'])
        for bad in (generated.replace('CONFIG_INV_MPU_IIO=y', '# CONFIG_INV_MPU_IIO is not set'),
                    generated + 'CONFIG_INV_MPU_M681_FACTORY_CALIBRATION=y\n', generated.replace(M.DTB, 'wrong-board')):
            with self.assertRaises(ValueError): M.check_config(fragment, bad)

    def test_elf_object_and_vmlinux_linkage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifact'
            data = bytearray(20); data[:6] = b'\x7fELF\x02\x01'; data[18:20] = (183).to_bytes(2, 'little')
            for linked, kind in ((False, 1), (True, 2)):
                data[16:18] = kind.to_bytes(2, 'little'); path.write_bytes(data)
                C.elf64_arm(path, linked=linked)
                with self.assertRaises(ValueError): C.elf64_arm(path, linked=not linked)
            path.write_bytes(b'not an ELF')
            with self.assertRaises(ValueError): C.elf64_arm(path)

    def test_actual_compile_driver_config_only_and_drift_stop_before_full_make(self):
        for case in ('config-only', 'drift', 'factory-enabled', 'full-drift', 'full-success', 'full-missing-object', 'full-missing-cmd'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                fixture = Path(directory)
                source, out, publish = fixture / 'source', fixture / 'out', fixture / 'publish'
                for p in (source / '.forge', out, publish): p.mkdir(parents=True)
                (fixture / 'dockerenv').write_text('synthetic container fixture')
                generated = ('CONFIG_MACH_MT6755=y\nCONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE=y\n'
                             'CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE_NAMES="' + M.DTB + '"\n'
                             'CONFIG_INV_MPU_IIO=y\n# CONFIG_INV_MPU_M681_FACTORY_CALIBRATION is not set\n')
                fragment = 'CONFIG_INV_MPU_IIO=y\n# CONFIG_INV_MPU_M681_FACTORY_CALIBRATION is not set\n'
                m = complete_manifest()
                m['config']['generated_sha256'] = ('9' * 64 if case == 'drift' else (__import__('hashlib').sha256(generated.encode()).hexdigest() if case.startswith('full-') else None))
                m['config']['fragment_sha256'] = __import__('hashlib').sha256(fragment.encode()).hexdigest()
                for name in m['source']['files_sha256']:
                    p = source / 'kernel' / name; p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(fragment if name == m['config']['fragment_path'] else generated)
                    m['source']['files_sha256'][name] = M.sha(p)
                for name in m['toolchain']['bin_sha256']:
                    p = source / 'toolchain/bin' / name; p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('synthetic compiler fixture')
                    m['toolchain']['bin_sha256'][name] = M.sha(p)
                (source / '.forge/m681-full-inputs.json').write_text(json.dumps(m))
                (source / '.forge/m681-full-selected.fragment').write_text(fragment)
                calls = []

                def mapped_path(value):
                    value = str(value)
                    special = {'/workspace/src': source, '/workspace/scratch/out': out,
                               '/workspace/out': publish, '/.dockerenv': fixture / 'dockerenv',
                               '/workspace/src/.forge/m681_compile.py': source / '.forge/m681_compile.py'}
                    return special.get(value, Path(value))

                def make(command, **kwargs):
                    calls.append(command)
                    if not case.startswith('full-'):
                        self.assertNotIn('Image.gz-dtb', command)
                    # All commands are mocked: this fixture never invokes make.
                    data = generated
                    if case == 'factory-enabled' and command[-1] == 'olddefconfig':
                        data += 'CONFIG_INV_MPU_M681_FACTORY_CALIBRATION=y\n'
                    if case == 'full-drift' and command[-1] == 'vmlinux':
                        data += 'CONFIG_UNEXPECTED_DRIFT=y\n'
                    (out / '.config').write_text(data)
                    if case in ('full-success', 'full-missing-object', 'full-missing-cmd') and command[-1] == 'vmlinux':
                        header = bytearray(64); header[:6] = b'\x7fELF\x02\x01'
                        header[16:18] = (1).to_bytes(2, 'little'); header[18:20] = (183).to_bytes(2, 'little')
                        for obj in M.OBJECTS:
                            if case == 'full-missing-object' and obj == M.OBJECTS[-1]: continue
                            p = out / obj; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(header)
                            if case != 'full-missing-cmd' or obj != M.OBJECTS[-1]:
                                p.with_name('.' + p.name + '.cmd').write_text('synthetic command fixture\n')
                        header[16:18] = (2).to_bytes(2, 'little'); (out / 'vmlinux').write_bytes(header)
                        (out / 'System.map').write_text('synthetic symbol fixture\n')
                        gz = out / 'arch/arm64/boot/Image.gz'; gz.parent.mkdir(parents=True, exist_ok=True)
                        gz.write_bytes(b'\x1f\x8bsynthetic gzip fixture')
                        dtb = out / ('arch/arm64/boot/dts/' + M.DTB + '.dtb'); dtb.parent.mkdir(parents=True, exist_ok=True)
                        dtb.write_bytes(b'\xd0\x0d\xfe\xed' + (40).to_bytes(4, 'big') + bytes(32))
                        (out / 'arch/arm64/boot/Image.gz-dtb').write_bytes(gz.read_bytes() + dtb.read_bytes())
                    return subprocess.CompletedProcess(command, 0)

                argv = ['m681_compile.py'] + ([] if case == 'drift' or case.startswith('full-') else ['--config-only'])
                with patch.object(C, 'Path', side_effect=mapped_path), patch.object(C, '__file__', '/workspace/src/.forge/m681_compile.py'), patch.object(C.subprocess, 'run', side_effect=make), patch.object(C.subprocess, 'check_output', return_value='synthetic package fixture\n'), patch.object(sys, 'argv', argv):
                    if case in ('config-only', 'full-success'): C.main()
                    elif case == 'full-missing-object':
                        with self.assertRaises(FileNotFoundError): C.main()
                    elif case == 'full-missing-cmd':
                        with self.assertRaisesRegex(ValueError, 'missing normal Kbuild output'): C.main()
                    elif case == 'full-drift':
                        with self.assertRaisesRegex(ValueError, 'full make changed'): C.main()
                    else:
                        with self.assertRaises(ValueError): C.main()
                self.assertEqual([c[-1] for c in calls], ['m681_49_a13_defconfig', 'olddefconfig'] + (['vmlinux'] if case.startswith('full-') else []))
                self.assertTrue((publish / 'kernel.config').is_file())
                if case == 'config-only':
                    proof = json.loads((publish / 'config-proof.json').read_text())
                    self.assertEqual(proof['config_sha256'], M.sha(publish / 'kernel.config'))
                    self.assertEqual(proof['container_image_id'], m['container']['image_id'])
                if case == 'full-success':
                    proof = json.loads((publish / 'kernel-proof.json').read_text())
                    self.assertEqual(set(proof['required_objects']), set(M.OBJECTS))
                    self.assertFalse(proof['runtime_verified']); self.assertFalse(proof['flash_ready'])
                    self.assertTrue(all((publish / p).is_file() for p in M.artifacts()))
                else:
                    self.assertFalse((publish / 'kernel-proof.json').exists())

    def test_actual_scratch_parser_accepts_m681_size_without_provisioning(self):
        for size in ('8', '32', '600'):
            with self.subTest(size=size), patch.object(sys, 'argv', ['provision_scratch.py', '--runner-temp', '/tmp', '--run-id', '123', '--size-gib', size]), patch.object(P.os, 'geteuid', return_value=1000), patch.object(P.os, 'open') as opened, patch.object(P.subprocess, 'run') as executed:
                # Parsing must succeed, then the real privilege guard stops all writes.
                with self.assertRaisesRegex(ValueError, 'root and a numeric GitHub run ID required'):
                    P.main()
                opened.assert_not_called(); executed.assert_not_called()
        for size in ('0', '16', '2048'):
            with self.subTest(size=size), patch.object(sys, 'argv', ['provision_scratch.py', '--runner-temp', '/tmp', '--run-id', '123', '--size-gib', size]), patch.object(P.os, 'open') as opened, patch.object(P.subprocess, 'run') as executed:
                with self.assertRaises(SystemExit): P.main()
                opened.assert_not_called(); executed.assert_not_called()

    def test_actual_32gib_scratch_headroom_refuses_before_any_file_write(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / 'mount-parent/forge'; target.parent.mkdir()
            original_path = Path

            def mapped_path(value):
                return target if str(value) == '/mnt/forge' else original_path(value)

            with patch.object(sys, 'argv', ['provision_scratch.py', '--runner-temp', str(parent), '--run-id', '123', '--size-gib', '32']), patch.object(P, 'Path', side_effect=mapped_path), patch.object(P.os, 'geteuid', return_value=0), patch.object(P.shutil, 'disk_usage', return_value=SimpleNamespace(free=43 * 1024**3)), patch.object(P.os, 'open') as opened, patch.object(P.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as executed:
                with self.assertRaisesRegex(ValueError, 'insufficient ephemeral disk headroom'): P.main()
                opened.assert_not_called()
                self.assertEqual(executed.call_count, 1)  # Read-only findmnt, no mkfs/mount.
                self.assertEqual(executed.call_args.args[0][0], 'findmnt')

    def test_workflow_default_yassy_and_stub_fail_before_reservation(self):
        workflow = (ROOT / '.github/workflows/blacksmith.yml').read_text()
        self.assertIn('default: yassy', workflow)
        self.assertLess(workflow.index('Validate the selected public kernel before admission'),
                        workflow.index('Reserve the full bounded job cost before runner allocation'))
        code = textwrap.dedent(workflow.split("<<'PYSELECT'\n", 1)[1].split('          PYSELECT', 1)[0])
        for mode, target, expected in (('kernel', 'yassy', 0), ('probe', 'yassy', 0),
                                       ('kernel', 'm681', 0), ('rom', 'm681', 1), ('kernel', 'unknown', 1)):
            with self.subTest(mode=mode, target=target):
                result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                                        env=dict(os.environ, REQUEST_MODE=mode, KERNEL_TARGET=target),
                                        capture_output=True, timeout=10)
                self.assertEqual(int(result.returncode != 0), expected)
        with tempfile.TemporaryDirectory() as directory:
            pending = Path(directory) / 'pending.json'
            manifest = complete_manifest(); manifest['ready'] = False
            pending.write_text(json.dumps(manifest))
            pending_code = code.replace("'recipes/m681-full-inputs.json'", repr(str(pending)))
            result = subprocess.run([sys.executable, '-B', '-c', pending_code], cwd=ROOT,
                                    env=dict(os.environ, REQUEST_MODE='kernel', KERNEL_TARGET='m681'),
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'public M681 immutable inputs are not ready', result.stderr)
        policy = json.loads((ROOT / 'config/blacksmith-policy.json').read_text())
        self.assertEqual(policy['modes']['kernel']['reserved_normalized_minutes'], 504)
        self.assertNotIn('m681', policy['modes'])


if __name__ == '__main__': unittest.main()
