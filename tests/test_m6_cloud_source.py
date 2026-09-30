import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = load('m6_cloud_source')
C = load('m6_cache_policy')


class CloudSourceTests(unittest.TestCase):
    def test_nine_retained_source_corrections_keep_exact_bytes(self):
        expected = {
            '.forge/run.sh': 'ba934b92a197de2aa452773ac55d12d52621361efebe5bdb4c88109b6a02313b',
            'build/make/core/Makefile': 'f065c30fcf83c68839ce1e59c5fa80a2b5d84f6de46ca05ef8c7e7d088c7e51a',
            'device/meizu/meizu_m6/BoardConfig.mk': '1e3180c849daeb88070510ceaa5c29435ec0e011d40d07c3aae11be73caf3522',
            'external/vim/Android.mk': 'ff496c557f616ab54d8ab190ae34bdfde58ef7e61ee93bfdff8cded3190fffe0',
            'frameworks/base/services/core/java/com/android/server/MmsServiceBroker.java': 'f4c183aab1cc88753db4872df250bbf16fbcc028ec5dca4b62d08a728f8087be',
            'frameworks/base/telephony/java/android/telephony/SmsManager.java': '7ac95b95f2c66c333c68a3794be9fec84d983451c5a487f823b9f1ffbaafa037',
            'frameworks/base/telephony/java/com/android/internal/telephony/IMms.aidl': '74aa5738de1a57b78a8ae479ac03a43c4c455524863dc122c5e9e54175ad650a',
            'vendor/lineage/build/tools/changelog.sh': '7c295f12f1ff0342b073bfb7467558ffdaf40c0b36829893770fb6e1a7c040db',
            'vendor/lineage/config/BoardConfigSoong.mk': '4227fd313b779845f149fd15c7fcdd4c9df13281d538312737a06642b3b8bce5',
        }
        for path, sha in expected.items():
            self.assertEqual(S.digest(HERE / 'inputs/m6-corrections-20260930' / path), sha)

    def test_exact_manifest_identity_and_all_701_pins(self):
        manifest = HERE / 'inputs/crdroid9-m6-resolved.xml'
        self.assertEqual(S.digest(manifest), S.MANIFEST_SHA)
        projects, generated = S.inventory(manifest.read_bytes())
        self.assertEqual(len(projects), 701)
        self.assertEqual(projects['device/meizu/meizu_m6'],
                         'b31f1449e25129810cf9b6d239d8b466c4ec6f55')
        self.assertIn('Makefile', generated)

    def test_rejects_unpinned_private_duplicate_traversal_and_includes(self):
        def xml(path='p', revision='a' * 40, remote='https://github.com/', extra=''):
            return ('<manifest><remote name="r" fetch="' + remote + '"/>'
                    '<default remote="r"/><project name="public" path="' + path +
                    '" revision="' + revision + '"/>' + extra + '</manifest>').encode()
        for raw in (xml(revision='main'), xml(path='../p'), xml(path='out'),
                    xml(path='vendor/meizu'), xml(remote='ssh://git@github.com'),
                    xml(extra='<include name="other.xml"/>'),
                    xml(extra='<project name="public" path="p" revision="' + 'b' * 40 + '"/>')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                S.inventory(raw, count=1)

    def test_foreign_private_output_and_proofs_rejected_before_cache(self):
        for foreign in ('out', '.forge', 'vendor/meizu', 'm6-private-inputs.json'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / 'build/make').mkdir(parents=True)
                (root / foreign).mkdir(parents=True)
                with self.assertRaises(ValueError):
                    S.public_boundary(root, {'build/make': 'a' * 40}, {})

    def test_partial_public_download_cache_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.repo').mkdir()
            (root / 'build/make').mkdir(parents=True)
            S.public_boundary(root, {'build/make': 'a' * 40, 'art': 'b' * 40}, {})
            (root / '.repo/local_manifests').mkdir()
            (root / '.repo/local_manifests/private.xml').write_text('private')
            with self.assertRaises(ValueError):
                S.public_boundary(root, {'build/make': 'a' * 40}, {})

    def test_cache_policy_rejects_unknown_source_and_forces_strict_exports(self):
        original = (HERE / 'inputs/ccache-original.mk').read_bytes()
        modified = C.patched(original)
        self.assertIn(b'override export CCACHE_NODIRECT := 1', modified)
        self.assertIn(b'override export CCACHE_COMPILERCHECK := content', modified)
        self.assertIn(b'override export CCACHE_SLOPPINESS :=\n', modified)
        self.assertNotIn(b'time_macros', modified)
        with self.assertRaises(ValueError):
            C.patched(original + b'# changed\n')

    @unittest.skipIf(os.name == 'nt', 'Effective GNU Make exports are verified by the cloud job')
    def test_effective_cache_policy_overrides_inherited_and_command_line_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'cache.mk').write_bytes(C.patched((HERE / 'inputs/ccache-original.mk').read_bytes()))
            (root / 'check.py').write_text('import os\nassert os.environ["CCACHE_COMPILERCHECK"] == "content"\nassert os.environ["CCACHE_NODIRECT"] == "1"\nassert os.environ["CCACHE_SLOPPINESS"] == ""\n')
            (root / 'Makefile').write_text('USE_CCACHE := true\ninclude cache.mk\ncheck:\n\t' + sys.executable + ' check.py\n')
            env = dict(os.environ, CCACHE_SLOPPINESS='time_macros',
                       CCACHE_COMPILERCHECK='none', CCACHE_NODIRECT='0')
            subprocess.run(['make', '--no-print-directory', 'check',
                            'CCACHE_SLOPPINESS=file_macro', 'CCACHE_COMPILERCHECK=mtime',
                            'CCACHE_NODIRECT=0'], cwd=root, env=env, check=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
