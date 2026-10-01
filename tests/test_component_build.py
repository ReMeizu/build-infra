import copy
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from component_manifest import relative, validate
from component_forge import forge, bounded_argv
from component_run import report_failure


def profile():
    return {'schema': 1, 'device': 'm5c', 'platform': 'mt6735', 'arch': 'arm64',
            'kernel_version': '4.9', 'target': 'Image.gz-dtb', 'jobs': 2, 'timeout_seconds': 3600, 'build_variant': 'userdebug',
            'source': {'url': 'https://github.com/ReMeizu/android_kernel_meizu_mt6735.git',
                       'commit': 'a' * 40, 'tree': 'b' * 40,
                       'files_sha256': {'arch/arm64/configs/m5c.config': 'c' * 64,
                                        'Makefile': 'c' * 64, 'arch/arm64/boot/dts/m5c.dts': 'c' * 64}},
            'toolchain': {'url': 'https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9',
                          'commit': 'd' * 40, 'tree': 'e' * 40, 'preparation': 'python3-wrappers',
                          'bin_sha256': {'aarch64-linux-android-gcc': 'f' * 64}},
            'config_file': 'arch/arm64/configs/m5c.config', 'expected_config_sha256': 'c' * 64,
            'dtb_file': 'arch/arm64/boot/dts/m5c.dtb', 'baseline_dtb_sha256': '0' * 64,
            'required_objects': ['drivers/input/touchscreen/gt9xx.o']}


class ComponentAdmissionTest(unittest.TestCase):
    def test_shell_and_make_injection_paths_rejected(self):
        for path in ('../kernel', '/tmp/kernel', 'a/../../kernel', 'a/.git/config',
                     'file;echo', 'file$(echo)', 'CC=evil', 'a//b', '.', '-C /tmp'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                relative(path)

    def test_bad_immutable_input_and_unbounded_compilation_refused(self):
        valid = profile()
        self.assertIs(validate(valid), valid)
        for key, value in [('jobs', 128), ('jobs', True), ('timeout_seconds', 86400),
                           ('target', 'Image.gz-dtb;curl'), ('arch', 'x86'),
                           ('kernel_version', '3.18'), ('config_file', 'unhashed.config')]:
            m = copy.deepcopy(valid); m[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(m)
        m = copy.deepcopy(valid); m['platform'] = 'mt6797'
        with self.assertRaises(ValueError):
            validate(m)
        for value in ('https://user:secret@github.com/ReMeizu/source.git',
                      'ssh://github.com/ReMeizu/source.git', 'https://github.com/other/source.git'):
            m = copy.deepcopy(valid); m['source']['url'] = value
            with self.subTest(url=value), self.assertRaises(ValueError):
                validate(m)
        m = copy.deepcopy(valid); m['source']['commit'] = 'main'
        with self.assertRaises(ValueError):
            validate(m)

    def test_full_kernel_recipe_runs_readonly_offline_nonroot_and_bounded(self):
        recipe = forge.recipe_from_dict({'image_tag': 'androidforge/build-component:component-kernel-gcc49',
            'image_id': 'sha256:' + 'a' * 64, 'build_env_key': 'component-kernel-gcc49',
            'source_mount_path': '/mnt/forge/source', 'output_dir_in_container': '/workspace/out',
            'command': ['python3', '/workspace/src/.forge/component_compile.py'], 'env': {},
            'idempotency_key': 'fixture', 'timeout_seconds': 3840, 'execution_profile': 'cloud-mounted',
            'scratch_mount_path': '/mnt/forge', 'container_user': '1001:1001',
            'required_artifacts': ['vmlinux', 'kernel-proof.json']})
        argv = bounded_argv(recipe, Path('/mnt/forge/evidence'), 'fixture-container')
        for option in ('--network=none', '--user=1001:1001', '--cpus=4', '--memory=5g', '--pids-limit=1024'):
            self.assertIn(option, argv)
        self.assertIn('/mnt/forge/source:/workspace/src:ro', argv)
        self.assertIn('sha256:' + 'a' * 64, argv)
        self.assertNotIn('--privileged', argv)
        self.assertEqual(argv[-2:], ['python3', '/workspace/src/.forge/component_compile.py'])

    def test_first_kbuild_fatal_visible_without_artifact_download(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'kernel-build.log').write_text('CC first.o\n/bin/sh: helper: not found\nmake: Error 127\n' + 'later noise\n' * 1000)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                report_failure(path)
            self.assertIn('helper: not found', output.getvalue())
            self.assertLess(len(output.getvalue()), 500)


if __name__ == '__main__':
    unittest.main()
