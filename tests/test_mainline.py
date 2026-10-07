import sys
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import mainline_build
import mainline_forge


class MainlineContractTests(unittest.TestCase):
    def test_common_drivers_must_be_built_in(self):
        config = '\n'.join('CONFIG_' + name + '=y' for name in mainline_build.REQUIRED_CONFIG)
        mainline_build.configuration(config)
        for value in ('m', 'n'):
            with self.assertRaises(ValueError):
                mainline_build.configuration(config.replace('CONFIG_PINCTRL_MT6755=y',
                                                             'CONFIG_PINCTRL_MT6755=' + value))

    def test_isolation_and_resource_limits(self):
        recipe = mainline_forge.forge.recipe_from_dict({
            'image_tag': 'androidforge/build-mainline:mainline-6.18',
            'source_mount_path': str(ROOT), 'output_dir_in_container': '/workspace/out',
            'command': ['python3', '/workspace/src/.forge/mainline_build.py'],
            'build_env_key': 'mainline-6.18', 'timeout_seconds': 3600,
            'idempotency_key': 'contract-test',
        })
        argv = mainline_forge.forge.build_docker_argv(recipe, ROOT / 'test-output', 'contract-test')
        for option in ('--cpus=2', '--memory=5g', '--memory-swap=6g', '--pids-limit=1024'):
            self.assertIn(option, argv)
        self.assertIn(str(ROOT) + ':/workspace/src:ro', argv)
        self.assertNotIn('--privileged', argv)

    def test_workflow_cannot_allocate_paid_runners(self):
        workflow = yaml.load((ROOT / '.github/workflows/mainline.yml').read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertEqual(workflow['jobs']['kernel']['runs-on'], 'ubuntu-24.04')
        self.assertEqual(workflow['jobs']['kernel']['timeout-minutes'], '85')


if __name__ == '__main__':
    unittest.main()
