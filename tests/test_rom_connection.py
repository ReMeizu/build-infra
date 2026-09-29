import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('connection',Path(__file__).resolve().parents[1]/'scripts/rom_connection.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ConnectionTest(unittest.TestCase):
 def test_provider_runner_name_with_uppercase_runner(self):
  runner='blacksmith-16vcpu-ubuntu-2404-Runner-665d263527'
  got=m.endpoint({'ROM_RUNNER_NAME':runner},'ssh -p 64000 runner@'+runner+'.vm.blacksmith.sh')
  self.assertEqual(got['status'],'ready')
  self.assertEqual(got['host'],runner.lower()+'.vm.blacksmith.sh')
  self.assertEqual(got['port'],64000)
 def test_literal_endpoint_does_not_copy_secret(self):
  env={'ROM_RUNNER_NAME':'blacksmith-test-16vcpu','GH_TOKEN':'private'}
  got=m.endpoint(env,'secret=private\necho "ssh -p 64000 runner@blacksmith-test-16vcpu.vm.blacksmith.sh"')
  self.assertEqual(got['port'],64000);self.assertNotIn('private',str(got))
 def test_assignment(self):
  self.assertEqual(m.endpoint({'ROM_RUNNER_NAME':'blacksmith-test'},'SSH_PORT="64000"\n')['port'],64000)
 def test_ambiguous_or_foreign(self):
  env={'ROM_RUNNER_NAME':'blacksmith-test','SSH_PORT':'64001'}
  self.assertEqual(m.endpoint(env,'SSH_PORT=64002')['status'],'endpoint_not_found')
  self.assertEqual(m.endpoint({'ROM_RUNNER_NAME':'blacksmith-test'},'ssh -p 64000 runner@foreign.vm.blacksmith.sh')['status'],'endpoint_not_found')
