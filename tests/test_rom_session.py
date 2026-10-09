import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('rom_session', Path(__file__).parents[1] / 'scripts/rom_session.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SessionTest(unittest.TestCase):
    def test_ninety_minute_rom_job_keeps_cleanup_reserve(self):
        limit = worker.session_budget(90 - 15)
        self.assertEqual(limit, 75 * 60)
        self.assertEqual(worker.expiration(limit, 0, limit, limit), 'session_deadline')
        self.assertIsNone(worker.expiration(limit - 1, 0, limit - 1, limit))
        workflow = (Path(__file__).parents[1] / '.github/workflows/blacksmith.yml').read_text()
        self.assertIn('          - rom-90\n', workflow)
        self.assertEqual(workflow.count("inputs.mode == 'rom-90'"), 4)
        self.assertIn('session_minutes=$((ROM_JOB_MINUTES - 15))', workflow)
        self.assertIn('process_minutes=$((session_minutes + 3))', workflow)

    def test_short_session_heartbeat_cannot_extend_reserved_deadline(self):
        limit = worker.session_budget(165)
        self.assertEqual(worker.expiration(limit, 0, limit, limit), 'session_deadline')
        self.assertIsNone(worker.expiration(limit - 1, 0, limit - 1, limit))
        for minutes in (0, 346):
            with self.assertRaises(ValueError):
                worker.session_budget(minutes)

    def test_six_hour_job_reserves_fifteen_minutes_for_cleanup(self):
        limit = worker.session_budget(345)
        self.assertEqual(limit, (360 - 15) * 60)
        self.assertIsNone(worker.expiration(limit - 1, 0, limit - 1, limit))
        self.assertEqual(worker.expiration(limit, 0, limit, limit), 'session_deadline')

    def test_activity_cannot_extend_hard_deadline(self):
        self.assertEqual(worker.expiration(worker.MAX_SECONDS, 0, worker.MAX_SECONDS), 'session_deadline')

    def test_idle_worker_expires(self):
        self.assertEqual(worker.expiration(worker.IDLE_SECONDS, 0, 0), 'idle_deadline')
        self.assertIsNone(worker.expiration(worker.IDLE_SECONDS, 0, 1))

    def test_artifacts_must_be_collected_before_completion(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'finished.json'
            p.write_text(json.dumps({'status': 'completed', 'artifacts_collected': False}))
            with self.assertRaises(ValueError):
                worker.read_completion(p)
            p.write_text(json.dumps({'status': 'completed', 'artifacts_collected': True}))
            self.assertEqual(worker.read_completion(p)['status'], 'completed')

    def test_marker_cannot_redirect_or_contain_commands(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'source.json'
            p = Path(td) / 'finished.json'
            target.write_text('{"status":"completed","artifacts_collected":true}')
            p.symlink_to(target)
            with self.assertRaises(ValueError):
                worker.read_completion(p)
            target.write_text('{"status":"completed","artifacts_collected":true,"command":"ignored"}')
            with self.assertRaises(ValueError):
                worker.read_completion(target)
