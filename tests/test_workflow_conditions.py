import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).parents[1]


class WorkflowConditionTest(unittest.TestCase):
    def test_github_step_references_resolve_inside_the_same_job(self):
        # Job boundaries and step IDs use fixed indentation in this workflow.
        workflow = (ROOT / '.github/workflows/blacksmith.yml').read_text()
        jobs = workflow.split('\njobs:\n', 1)[1]
        sections = re.split(r'^  ([A-Za-z_][A-Za-z0-9_-]*):\n', jobs, flags=re.M)
        self.assertEqual(set(sections[1::2]), {'budget', 'runner'})
        for job_name, body in zip(sections[1::2], sections[2::2]):
            identities = re.findall(r'^        id: ([A-Za-z_][A-Za-z0-9_-]*)$', body, re.M)
            self.assertEqual(len(identities), len(set(identities)), job_name)
            references = set(re.findall(r'\bsteps\.([A-Za-z_][A-Za-z0-9_-]*)\.', body))
            self.assertFalse(references - set(identities), (job_name, references, identities))

    def test_regression_wrong_job_checkout_id_is_rejected(self):
        workflow = (ROOT / '.github/workflows/blacksmith.yml').read_text()
        budget, runner = workflow.split('\n  runner:\n', 1)
        self.assertNotIn('id: runner_checkout', budget)
        self.assertIn('id: runner_checkout', runner)
        self.assertIn("steps.runner_checkout.outcome == 'success'", runner)


if __name__ == '__main__':
    unittest.main()
