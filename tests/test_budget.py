import base64
import copy
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
import urllib.error


SPEC = importlib.util.spec_from_file_location('budget', Path(__file__).parents[1] / 'scripts/budget.py')
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


def utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def seed():
    return {'schema_version': B.LEDGER_SCHEMA, 'repository': B.REPOSITORY, 'months': {}}


def reservation(mode='probe', month='2026-09'):
    spec = B.MODES[mode]
    return {'mode': mode, 'vcpu': spec['vcpu'], 'timeout_minutes': spec['timeout_minutes'],
            'overhead_minutes': 3, 'reserved_normalized_minutes': spec['reserved_normalized_minutes'],
            'reserved_at': month + '-01T00:00:00Z'}


class MemoryREST:
    """Exercise the real contents encoding, SHA validation and CAS request body."""
    def __init__(self, ledger):
        self.raw = json.dumps(ledger).encode()
        self.calls = []
        self.conflict = False
        self.bad_readback = False

    def request(self, method, url, payload=None):
        self.calls.append((method, url, copy.deepcopy(payload)))
        expected = 'https://api.github.com/repos/ReMeizu/build-infra/contents/ledger.json'
        if method == 'GET':
            if url != expected + '?ref=blacksmith-budget':
                raise AssertionError('unscoped GET')
            raw = self.raw
            if self.bad_readback and len(self.calls) > 1:
                raw = json.dumps(seed()).encode()
            return {'type': 'file', 'path': 'ledger.json', 'encoding': 'base64',
                    'content': base64.b64encode(raw).decode(), 'sha': B.blob_sha(raw)}
        if method != 'PUT' or url != expected or payload['branch'] != 'blacksmith-budget':
            raise AssertionError('unscoped write')
        if self.conflict or payload['sha'] != B.blob_sha(self.raw):
            raise B.BudgetError('ledger CAS rejected; reservation not authorized')
        self.raw = base64.b64decode(payload['content'], validate=True)
        return {'content': {'sha': B.blob_sha(self.raw), 'path': 'ledger.json'}}


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.policy = B.read_policy()
        # Legacy fixtures continue to verify the old unrenewed lifetime cap.
        self.policy['lifetime_reservation_limit'] = 9000
        self.env = {'GITHUB_REPOSITORY': B.REPOSITORY, 'GITHUB_RUN_ID': '999999',
                    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_ACTIONS': 'true',
                    'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GH_TOKEN': 'DO-NOT-LOG-THIS-SECRET'}
        self.now = utc('2026-09-29T12:00:00Z')
        self.transport = MemoryREST(seed())
        self.api = B.GitHubContents(self.env['GH_TOKEN'], self.policy)
        self.api.request = self.transport.request

    def call(self, mode='probe', now=None):
        return B.reserve(mode, self.env, self.policy, self.api, lambda: now or self.now)

    def populate(self, kernels=0, probes=0, month='2026-09'):
        ledger = seed()
        rows = {}
        for i in range(kernels + probes):
            rows[str(i + 1)] = reservation('kernel' if i < kernels else 'probe', month)
        ledger['months'][month] = {'reservations': rows}
        self.transport.raw = json.dumps(ledger).encode()
        return ledger

    def test_existing_mx6_ledger_row_is_accounted_but_cannot_be_reused(self):
        old = seed()
        row = {'mode': 'mx6-kernel', 'vcpu': 4, 'timeout_minutes': 40,
               'overhead_minutes': 3, 'reserved_normalized_minutes': 86,
               'reserved_at': '2026-09-30T13:39:24.867873Z'}
        old['months']['2026-09'] = {'reservations': {'36723209887': row}}
        self.transport.raw = json.dumps(old).encode()
        self.policy = B.read_policy()
        result = self.call('rom-long', utc('2026-10-02T12:00:00Z'))
        self.assertEqual(result['lifetime_reserved_normalized_minutes'], '2990')
        self.assertEqual(json.loads(self.transport.raw)['months']['2026-09'], old['months']['2026-09'])
        with self.assertRaisesRegex(B.BudgetError, 'unknown mode'):
            self.call('mx6-kernel')
        bad = copy.deepcopy(old)
        bad['months']['2026-09']['reservations']['36723209888'] = row
        with self.assertRaisesRegex(B.BudgetError, 'unknown legacy'):
            B.validate_ledger(bad, self.policy)
        bad = copy.deepcopy(old)
        bad['months']['2026-09']['reservations']['36723209887']['reserved_normalized_minutes'] = 85
        with self.assertRaisesRegex(B.BudgetError, 'invalid reserved cost'):
            B.validate_ledger(bad, self.policy)

    def test_october_renewal_retains_september_and_reserves_six_hour_rom(self):
        old = self.populate(kernels=17, probes=53)
        self.policy = B.read_policy()
        result = self.call('rom-long', utc('2026-10-02T12:00:00Z'))
        self.assertEqual(result['timeout_minutes'], '360')
        self.assertEqual(result['monthly_reserved_normalized_minutes'], '2904')
        self.assertEqual(result['lifetime_reserved_normalized_minutes'], '11896')
        observed = json.loads(self.transport.raw)
        self.assertEqual(observed['months']['2026-09'], old['months']['2026-09'])
        before = self.transport.raw
        self.env['GITHUB_RUN_ID'] = '1000000'
        with self.assertRaisesRegex(B.BudgetError, 'renewal unverified'):
            self.call('rom-long', utc('2026-11-02T12:00:00Z'))
        self.assertEqual(self.transport.raw, before)

    def test_three_long_roms_fit_month_and_fourth_is_denied(self):
        self.policy = B.read_policy()
        for run in range(3):
            self.env['GITHUB_RUN_ID'] = str(1000000 + run)
            result = self.call('rom-long', utc('2026-10-02T12:00:00Z'))
        self.assertEqual(result['monthly_reserved_normalized_minutes'], '8712')
        before = self.transport.raw
        self.env['GITHUB_RUN_ID'] = '1000003'
        with self.assertRaisesRegex(B.BudgetError, 'monthly local stop'):
            self.call('rom-long', utc('2026-10-02T12:00:00Z'))
        self.assertEqual(self.transport.raw, before)

    def test_probe_records_exact_cost_then_verifies_readback(self):
        result = self.call()
        self.assertEqual(result['authorized'], 'true')
        self.assertEqual(result['runner'], 'blacksmith-2vcpu-ubuntu-2404')
        self.assertEqual(result['reserved_normalized_minutes'], '8')
        self.assertEqual(result['timeout_minutes'], '5')
        self.assertEqual([c[0] for c in self.transport.calls], ['GET', 'PUT', 'GET'])
        self.assertEqual(json.loads(self.transport.raw)['months']['2026-09']['reservations']['999999']['mode'], 'probe')

    def test_kernel_cost_is_16vcpu_divided_by_2_times_63_minutes(self):
        result = self.call('kernel')
        self.assertEqual(result['runner'], 'blacksmith-16vcpu-ubuntu-2404')
        self.assertEqual(result['reserved_normalized_minutes'], '504')
        self.assertEqual(result['timeout_minutes'], '60')

    def test_benchmark_reserves_88_and_preserves_existing_ledger_rows(self):
        original = self.populate(kernels=1, probes=2)
        result = self.call('benchmark')
        self.assertEqual(result['runner'], 'blacksmith-16vcpu-ubuntu-2404')
        self.assertEqual(result['timeout_minutes'], '8')
        self.assertEqual(result['reserved_normalized_minutes'], '88')
        self.assertEqual(result['monthly_reserved_normalized_minutes'], '608')
        observed = json.loads(self.transport.raw)['months']['2026-09']['reservations']
        for run_id, row in original['months']['2026-09']['reservations'].items():
            self.assertEqual(observed[run_id], row)
        self.assertEqual([c[0] for c in self.transport.calls], ['GET', 'PUT', 'GET'])

    def test_existing_modes_accept_new_benchmark_rows_under_updated_policy(self):
        self.call('benchmark')
        expected = 88
        for index, mode in enumerate(('kernel', 'probe', 'rom')):
            with self.subTest(mode=mode):
                self.env['GITHUB_RUN_ID'] = str(1000000 + index)
                result = self.call(mode)
                expected += B.MODES[mode]['reserved_normalized_minutes']
                self.assertEqual(int(result['monthly_reserved_normalized_minutes']), expected)
                self.assertEqual(json.loads(self.transport.raw)['months']['2026-09']['reservations']['999999']['mode'], 'benchmark')

    def test_old_policy_rejects_benchmark_rows_fail_closed(self):
        self.call('benchmark')
        ledger = json.loads(self.transport.raw)
        old_policy = copy.deepcopy(self.policy)
        del old_policy['modes']['benchmark']
        with self.assertRaisesRegex(B.BudgetError, 'unknown reserved mode'):
            B.validate_ledger(ledger, old_policy)

    def test_benchmark_exact_monthly_ceiling_then_denies_without_write(self):
        self.populate(kernels=17, probes=43)  # 8912 + 88 == 9000
        self.assertEqual(self.call('benchmark')['monthly_reserved_normalized_minutes'], '9000')
        before = self.transport.raw
        self.env['GITHUB_RUN_ID'] = '1000000'
        with self.assertRaisesRegex(B.BudgetError, 'monthly local stop'):
            self.call('benchmark')
        self.assertEqual(self.transport.raw, before)

    def test_benchmark_lifetime_ceiling_and_utc_boundary_remain_guarded(self):
        self.populate(kernels=17, probes=43, month='2026-08')
        self.assertEqual(self.call('benchmark')['lifetime_reserved_normalized_minutes'], '9000')
        before = self.transport.raw
        self.env['GITHUB_RUN_ID'] = '1000000'
        with self.assertRaisesRegex(B.BudgetError, 'lifetime grant stop'):
            self.call('benchmark')
        self.assertEqual(self.transport.raw, before)
        self.transport.calls.clear()
        with self.assertRaisesRegex(B.BudgetError, 'month boundary'):
            self.call('benchmark', utc('2026-09-30T23:49:00Z'))
        self.assertEqual(self.transport.calls, [])

    def test_rom_reserves_full_four_hour_session_before_allocation(self):
        result = self.call('rom')
        self.assertEqual(result['runner'], 'blacksmith-16vcpu-ubuntu-2404')
        self.assertEqual(result['reserved_normalized_minutes'], '1944')
        self.assertEqual(result['timeout_minutes'], '240')

    def test_rom_cannot_exceed_existing_budget(self):
        self.populate(kernels=15)
        before = self.transport.raw
        with self.assertRaisesRegex(B.BudgetError, 'monthly local stop'):
            self.call('rom')
        self.assertEqual(self.transport.raw, before)

    def test_short_rom_preserves_old_reservations_and_stays_under_existing_cap(self):
        original = self.populate(kernels=10, probes=58)
        original['months']['2026-09']['reservations']['700'] = reservation('rom')
        self.transport.raw = json.dumps(original).encode()
        result = self.call('rom-short')
        self.assertEqual(result['timeout_minutes'], '180')
        self.assertEqual(result['reserved_normalized_minutes'], '1464')
        self.assertEqual(result['monthly_reserved_normalized_minutes'], '8912')
        observed = json.loads(self.transport.raw)['months']['2026-09']['reservations']
        for run_id, row in original['months']['2026-09']['reservations'].items():
            self.assertEqual(observed[run_id], row)
        before = self.transport.raw
        self.env['GITHUB_RUN_ID'] = '1000000'
        with self.assertRaisesRegex(B.BudgetError, 'monthly local stop'):
            self.call('rom-short')
        self.assertEqual(self.transport.raw, before)

    def test_exact_limit_allowed_but_following_reservation_denied(self):
        self.populate(kernels=17, probes=53)  # 8992 normalized minutes
        result = self.call()
        self.assertEqual(result['monthly_reserved_normalized_minutes'], '9000')
        before = self.transport.raw
        self.env['GITHUB_RUN_ID'] = '1000000'
        with self.assertRaisesRegex(B.BudgetError, 'monthly local stop'):
            self.call()
        self.assertEqual(self.transport.raw, before)

    def test_kernel_overspend_is_not_reserved(self):
        self.populate(kernels=17)
        before = self.transport.raw
        with self.assertRaisesRegex(B.BudgetError, 'monthly local stop'):
            self.call('kernel')
        self.assertEqual(self.transport.raw, before)
        self.assertEqual([c[0] for c in self.transport.calls], ['GET'])

    def test_lifetime_stop_blocks_new_month_without_verified_renewal(self):
        self.populate(kernels=17, month='2026-08')
        with self.assertRaisesRegex(B.BudgetError, 'lifetime grant stop'):
            self.call('kernel')
        self.assertNotIn('2026-09', json.loads(self.transport.raw)['months'])

    def test_new_month_keeps_old_reservations_and_total(self):
        prior = self.populate(probes=1, month='2026-08')
        result = self.call('kernel')
        self.assertEqual(result['lifetime_reserved_normalized_minutes'], '512')
        self.assertEqual(result['monthly_reserved_normalized_minutes'], '504')
        self.assertEqual(json.loads(self.transport.raw)['months']['2026-08'], prior['months']['2026-08'])

    def test_duplicate_run_rejected_even_in_different_month(self):
        self.call()
        before = self.transport.raw
        with self.assertRaisesRegex(B.BudgetError, 'already reserved'):
            self.call(now=utc('2026-10-01T12:00:00Z'))
        self.assertEqual(self.transport.raw, before)

    def test_rerun_unknown_mode_repo_or_automatic_event_rejected_before_api(self):
        for key, value in [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_RUN_ATTEMPT', ''),
                           ('GITHUB_REPOSITORY', 'another/repo'), ('GITHUB_EVENT_NAME', 'push'),
                           ('GITHUB_ACTIONS', 'false'), ('GITHUB_RUN_ID', '../bad')]:
            with self.subTest(key=key, value=value), patch.dict(self.env, {key: value}):
                with self.assertRaises(B.BudgetError):
                    self.call()
        with self.assertRaisesRegex(B.BudgetError, 'unknown mode'):
            self.call('unbounded')
        self.assertEqual(self.transport.calls, [])

    def test_cas_conflict_is_not_retried_or_authorized(self):
        self.transport.conflict = True
        before = self.transport.raw
        with self.assertRaisesRegex(B.BudgetError, 'CAS rejected'):
            self.call()
        self.assertEqual([c[0] for c in self.transport.calls], ['GET', 'PUT'])
        self.assertEqual(self.transport.raw, before)

    def test_uncertain_write_readback_burns_reservation_and_denies(self):
        self.transport.bad_readback = True
        with self.assertRaisesRegex(B.BudgetError, 'readback mismatch'):
            self.call()
        self.assertIn('999999', json.loads(self.transport.raw)['months']['2026-09']['reservations'])

    def test_exact_month_boundary_and_nearby_start(self):
        with self.assertRaisesRegex(B.BudgetError, 'month boundary'):
            self.call('kernel', utc('2026-09-30T22:57:00Z'))
        self.assertEqual(self.transport.calls, [])
        result = self.call('kernel', utc('2026-09-30T22:56:59Z'))
        self.assertEqual(result['latest_start_utc'], '2026-09-30T22:57:00Z')

    def test_december_rollover_uses_next_year(self):
        month, latest = B.check_window(utc('2026-12-15T00:00:00Z'), B.MODES['probe'], self.policy)
        self.assertEqual(month, '2026-12')
        self.assertEqual(B.timestamp(latest), '2026-12-31T23:52:00Z')

    def test_month_changes_during_readback_denies_but_keeps_spent_reservation(self):
        times = iter([utc('2026-09-30T22:00:00Z'), utc('2026-09-30T22:00:01Z'), utc('2026-10-01T00:00:00Z')])
        with self.assertRaisesRegex(B.BudgetError, 'month changed after'):
            B.reserve('kernel', self.env, self.policy, self.api, lambda: next(times))
        self.assertIn('999999', json.loads(self.transport.raw)['months']['2026-09']['reservations'])

    def test_malformed_ledger_cost_unknown_fields_duplicate_ids_fail_closed(self):
        valid = self.populate(probes=1)
        variants = []
        bad = copy.deepcopy(valid); bad['months']['2026-09']['reservations']['1']['reserved_normalized_minutes'] = 0; variants.append(bad)
        bad = copy.deepcopy(valid); bad['months']['2026-09']['reservations']['1']['vcpu'] = True; variants.append(bad)
        bad = copy.deepcopy(valid); bad['extra'] = 'unknown'; variants.append(bad)
        bad = copy.deepcopy(valid); bad['months']['2026-09']['reservations']['1']['mode'] = 'rom'; variants.append(bad)
        bad = copy.deepcopy(valid); bad['months']['2026-08'] = {'reservations': {'1': reservation(month='2026-08')}}; variants.append(bad)
        bad = copy.deepcopy(valid); bad['months']['2026-09']['reservations']['1']['reserved_at'] = '2026-08-01T00:00:00Z'; variants.append(bad)
        for ledger in variants:
            with self.subTest(ledger=ledger):
                with self.assertRaises(B.BudgetError):
                    B.validate_ledger(ledger, self.policy)
        with self.assertRaisesRegex(B.BudgetError, 'duplicate JSON key'):
            B.parse_json('{"months":{},"months":{}}')

    def test_malformed_blob_hash_and_missing_ledger_fail_closed(self):
        with patch.object(self.api, 'request', return_value={'type': 'file', 'path': 'ledger.json',
                'encoding': 'base64', 'content': base64.b64encode(b'{}').decode(), 'sha': 'a' * 40}):
            with self.assertRaisesRegex(B.BudgetError, 'hash mismatch'):
                self.api.get()
        for code in (404, 403, 409, 422, 500):
            api = B.GitHubContents('secret', self.policy)
            error = urllib.error.HTTPError(api.url, code, 'DO-NOT-LOG-THIS-SECRET', {}, None)
            with self.subTest(status=code), patch.object(B.urllib.request, 'urlopen', side_effect=error):
                with self.assertRaises(B.BudgetError) as caught:
                    api.get()
                self.assertNotIn('DO-NOT-LOG', str(caught.exception))

    def test_cli_denial_writes_false_without_token_or_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'github-output'
            self.env['GITHUB_OUTPUT'] = str(output)
            self.transport.conflict = True
            stderr, stdout = io.StringIO(), io.StringIO()
            with patch.object(B, 'GitHubContents', return_value=self.api), redirect_stderr(stderr), redirect_stdout(stdout):
                self.assertEqual(B.main(['--mode', 'probe'], self.env), 1)
            self.assertEqual(output.read_text(), 'authorized=false\n')
            self.assertNotIn(self.env['GH_TOKEN'], stdout.getvalue() + stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
