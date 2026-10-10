"""Owned closure refusal controls; no actual Docker or target compilation."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from finish_attempt import closed_containers


class OwnedClosureControls(unittest.TestCase):
    def fixture(self, *, reaped=True, pending=False):
        root=Path(tempfile.mkdtemp(prefix='native-owned-closure-control-',dir='/dev/shm'))
        metadata=root/'state';metadata.mkdir()
        inv='a'*32;recipe='b'*64;cid='c'*64
        state={'invocation':inv,'recipe_hash':recipe,'container_name':'forge-eph-'+recipe[:12]+'-'+inv[:12],
               'container_id':cid,'cleanup_needed':pending,'client_reaped':reaped,'create_issued':True}
        path=metadata/(inv+'.json');path.write_text(json.dumps(state))
        self.addCleanup(lambda:self.assertEqual(json.loads(path.read_text()),state))
        return root,path,recipe

    def forge(self, pending=False):
        return SimpleNamespace(CONTAINER_METADATA_DIR='state',_cleanup_owned_container=lambda state:
                               {'cleanup_needed':pending,'cleanup_reason':'synthetic owned cleanup control'})

    def test_reaped_known_absent_container_with_completed_cleanup_passes(self):
        root,path,recipe=self.fixture()
        with patch('finish_attempt.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='No such object')) as inspect:
            proof=closed_containers(self.forge(),root,recipe)
        inspect.assert_called_once()
        self.assertTrue(proof['all_owned_container_closure_pass'])
        self.assertEqual(json.loads(path.read_text())['client_reaped'],True)

    def test_completed_owned_cleanup_preserves_original_pending_producer_json(self):
        root,path,recipe=self.fixture(pending=True)
        with patch('finish_attempt.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='No such object')):
            proof=closed_containers(self.forge(),root,recipe)
        self.assertTrue(proof['all_owned_container_closure_pass'])
        self.assertTrue(json.loads(path.read_text())['cleanup_needed'])

    def test_known_absent_cid_does_not_accept_unreaped_client(self):
        root,path,recipe=self.fixture(reaped=False)
        with patch('finish_attempt.subprocess.run') as inspect:
            with self.assertRaisesRegex(ValueError,'client reap or cleanup unresolved'):
                closed_containers(self.forge(),root,recipe)
        inspect.assert_not_called()
        self.assertFalse((root/'OWNED_TERMINATION.json').exists())

    def test_known_cid_does_not_override_unresolved_late_creation_cleanup(self):
        root,path,recipe=self.fixture(pending=True)
        with patch('finish_attempt.subprocess.run') as inspect:
            with self.assertRaisesRegex(ValueError,'client reap or cleanup unresolved'):
                closed_containers(self.forge(pending=True),root,recipe)
        inspect.assert_not_called()
        self.assertFalse((root/'OWNED_TERMINATION.json').exists())

    def test_reaped_client_still_requires_known_container_actual_absence(self):
        root,path,recipe=self.fixture()
        with patch('finish_attempt.subprocess.run',return_value=SimpleNamespace(returncode=0,stderr='')):
            with self.assertRaisesRegex(ValueError,'still exists or closure unresolved'):
                closed_containers(self.forge(),root,recipe)
        self.assertFalse((root/'OWNED_TERMINATION.json').exists())


if __name__=='__main__':unittest.main()
