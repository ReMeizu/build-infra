import pathlib
import re
import json
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parents[1]


class WorkflowConditionTest(unittest.TestCase):
    def test_github_step_references_resolve_inside_the_same_job(self):
        # Job boundaries and step IDs use fixed indentation in this workflow.
        workflow = (ROOT / '.github/workflows/blacksmith.yml').read_text()
        jobs = workflow.split('\njobs:\n', 1)[1]
        sections = re.split(r'^  ([A-Za-z_][A-Za-z0-9_-]*):\n', jobs, flags=re.M)
        self.assertEqual(set(sections[1::2]), {'budget', 'runner', 'component'})
        for job_name, body in zip(sections[1::2], sections[2::2]):
            identities = re.findall(r'^        id: ([A-Za-z_][A-Za-z0-9_-]*)$', body, re.M)
            self.assertEqual(len(identities), len(set(identities)), job_name)
            references = set(re.findall(r'\bsteps\.([A-Za-z_][A-Za-z0-9_-]*)\.', body))
            self.assertFalse(references - set(identities), (job_name, references, identities))

    def test_circle_wrapper_exit_trap_retains_failure_and_existing_evidence(self):
        wrapper = (ROOT / 'scripts/cloud_benchmark_job.sh').read_text()
        function = wrapper.split('ensure_compact_evidence() {', 1)[1].split('trap ensure_compact_evidence EXIT', 1)[0]
        script = 'ensure_compact_evidence() {' + function + 'trap ensure_compact_evidence EXIT\nexit 42\n'
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(['bash', '-c', script], cwd=folder, capture_output=True)
            self.assertEqual(result.returncode, 42)
            evidence = pathlib.Path(folder) / 'evidence'
            self.assertEqual(json.loads((evidence / 'benchmark.json').read_text())['process_exit_code'], 42)
            self.assertFalse(json.loads((evidence / 'benchmark-status.json').read_text())['measurement_complete'])
            (evidence / 'benchmark.json').write_text('preserved original')
            result = subprocess.run(['bash', '-c', script], cwd=folder, capture_output=True)
            self.assertEqual(result.returncode, 42)
            self.assertEqual((evidence / 'benchmark.json').read_text(), 'preserved original')

    def test_regression_wrong_job_checkout_id_is_rejected(self):
        workflow = (ROOT / '.github/workflows/blacksmith.yml').read_text()
        budget, runner = workflow.split('\n  runner:\n', 1)
        self.assertNotIn('id: runner_checkout', budget)
        self.assertIn('id: runner_checkout', runner)
        self.assertIn("steps.runner_checkout.outcome == 'success'", runner)

    def test_public_kernel_job_does_not_reserve_blacksmith(self):
        workflow = (ROOT / '.github/workflows/blacksmith.yml').read_text()
        budget = workflow.split('\n  budget:\n', 1)[1].split('\n  runner:\n', 1)[0]
        component = workflow.split('\n  component:\n', 1)[1]
        self.assertIn("inputs.mode != 'component'", budget)
        self.assertIn('github.event.repository.private == false', component)
        self.assertIn('runs-on: ubuntu-24.04', component)
        self.assertNotIn('needs: budget', component)
        self.assertNotIn('contents: write', component)


if __name__ == '__main__':
    unittest.main()
