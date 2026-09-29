#!/usr/bin/env python3
"""Fail-closed, append-only monthly Blacksmith reservation gate using GitHub CAS.

Run this on the free GitHub-hosted gate before scheduling a Blacksmith job.
The repository owner must seed ledger.json on blacksmith-budget separately.
Reservations are never refunded. This repository gate is not a provider cap.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'ReMeizu/build-infra'
POLICY_PATH = Path(__file__).resolve().parents[1] / 'config/blacksmith-policy.json'
LEDGER_SCHEMA = 'remeizu.blacksmith-budget.v1'
MAX_BYTES = 1024 * 1024
MODES = {
    'probe': {'runner': 'blacksmith-2vcpu-ubuntu-2404', 'vcpu': 2,
              'timeout_minutes': 5, 'reserved_normalized_minutes': 8},
    'kernel': {'runner': 'blacksmith-16vcpu-ubuntu-2404', 'vcpu': 16,
               'timeout_minutes': 60, 'reserved_normalized_minutes': 504},
}


class BudgetError(Exception):
    """Messages contain fixed diagnostics, never API response bodies/tokens."""


def require(condition, message):
    if not condition:
        raise BudgetError(message)


def exact_keys(value, keys, message):
    require(isinstance(value, dict) and set(value) == set(keys), message)


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_timestamp(value):
    require(isinstance(value, str) and value.endswith('Z'), 'invalid reservation timestamp')
    try:
        result = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        raise BudgetError('invalid reservation timestamp') from None
    require(result.utcoffset() == timedelta(0), 'reservation timestamp must be UTC')
    return result


def parse_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise BudgetError('invalid JSON') from None


def read_policy(path=POLICY_PATH):
    try:
        data = path.read_bytes()
    except OSError:
        raise BudgetError('policy unavailable') from None
    require(len(data) <= MAX_BYTES, 'policy too large')
    policy = parse_json(data)
    exact_keys(policy, ('schema_version', 'provider', 'repository', 'ledger_branch', 'ledger_path',
                       'allowance_normalized_minutes', 'local_stop_normalized_minutes',
                       'lifetime_reservation_limit', 'billing_unit_vcpus', 'overhead_minutes', 'modes'), 'unknown policy schema')
    expected = {'schema_version': 'remeizu.blacksmith-policy.v1', 'provider': 'blacksmith',
                'repository': REPOSITORY, 'ledger_branch': 'blacksmith-budget', 'ledger_path': 'ledger.json',
                'allowance_normalized_minutes': 10000, 'local_stop_normalized_minutes': 9000,
                'lifetime_reservation_limit': 9000,
                'billing_unit_vcpus': 2, 'overhead_minutes': 3, 'modes': MODES}
    # An altered grant, repository, runner or timeout needs a reviewed gate change.
    require(policy == expected, 'policy differs from the reviewed allowance/scope/modes')
    for key in ('allowance_normalized_minutes', 'local_stop_normalized_minutes', 'lifetime_reservation_limit',
                'billing_unit_vcpus', 'overhead_minutes'):
        require(type(policy[key]) is int, 'policy minutes must be integers')
    for mode in policy['modes'].values():
        require(all(type(mode[k]) is int for k in ('vcpu', 'timeout_minutes', 'reserved_normalized_minutes')),
                'mode costs must be integers')
    return policy


def validate_ledger(ledger, policy):
    exact_keys(ledger, ('schema_version', 'repository', 'months'), 'unknown ledger schema')
    require(ledger['schema_version'] == LEDGER_SCHEMA and ledger['repository'] == REPOSITORY,
            'ledger scope/schema mismatch')
    require(isinstance(ledger['months'], dict), 'invalid month buckets')
    all_runs, totals = set(), {}
    for month, bucket in ledger['months'].items():
        require(isinstance(month, str) and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', month), 'invalid month')
        exact_keys(bucket, ('reservations',), 'unknown month bucket schema')
        reservations = bucket['reservations']
        require(isinstance(reservations, dict), 'invalid reservations')
        total = 0
        for run_id, row in reservations.items():
            require(isinstance(run_id, str) and re.fullmatch(r'[1-9][0-9]{0,19}', run_id), 'invalid run ID')
            require(run_id not in all_runs, 'duplicate run ID across months')
            all_runs.add(run_id)
            exact_keys(row, ('mode', 'vcpu', 'timeout_minutes', 'overhead_minutes',
                             'reserved_normalized_minutes', 'reserved_at'), 'unknown reservation schema')
            require(isinstance(row['mode'], str) and row['mode'] in policy['modes'], 'unknown reserved mode')
            mode = policy['modes'][row['mode']]
            for key in ('vcpu', 'timeout_minutes', 'reserved_normalized_minutes'):
                require(type(row[key]) is int and row[key] == mode[key], 'invalid reserved cost')
            require(type(row['overhead_minutes']) is int and row['overhead_minutes'] == policy['overhead_minutes'],
                    'invalid reserved overhead')
            require(parse_timestamp(row['reserved_at']).strftime('%Y-%m') == month, 'reservation/month mismatch')
            total += row['reserved_normalized_minutes']
        require(total <= policy['local_stop_normalized_minutes'], 'ledger already exceeds local stop')
        totals[month] = total
    require(sum(totals.values()) <= policy['lifetime_reservation_limit'], 'ledger already exceeds lifetime stop')
    return totals, all_runs


def check_window(now, mode, policy):
    require(now.tzinfo is not None and now.utcoffset() == timedelta(0), 'clock must be UTC')
    next_month = (now.replace(day=28, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=4)).replace(day=1)
    latest_start = next_month - timedelta(minutes=mode['timeout_minutes'] + policy['overhead_minutes'])
    require(now < latest_start, 'timeout plus overhead would cross the UTC month boundary')
    return now.strftime('%Y-%m'), latest_start


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


class GitHubContents:
    def __init__(self, token, policy):
        require(isinstance(token, str) and bool(token.strip()), 'GH_TOKEN missing')
        self.token = token
        self.branch = policy['ledger_branch']
        self.path = policy['ledger_path']
        self.url = 'https://api.github.com/repos/' + REPOSITORY + '/contents/' + self.path

    def request(self, method, url, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json',
            'User-Agent': 'remeizu-blacksmith-budget-gate',
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                require(response.status == 200, 'unexpected GitHub API status')
                raw = response.read(MAX_BYTES * 2 + 1)
                require(len(raw) <= MAX_BYTES * 2, 'GitHub response too large')
        except urllib.error.HTTPError as error:
            if error.code in (409, 422):
                raise BudgetError('ledger CAS rejected; reservation not authorized') from None
            raise BudgetError('GitHub API rejected request') from None
        except (urllib.error.URLError, OSError, TimeoutError):
            raise BudgetError('GitHub API unavailable; reservation not authorized') from None
        return parse_json(raw)

    def get(self):
        response = self.request('GET', self.url + '?ref=' + urllib.parse.quote(self.branch, safe=''))
        require(isinstance(response, dict) and response.get('type') == 'file'
                and response.get('path') == self.path and response.get('encoding') == 'base64',
                'ledger missing or invalid GitHub contents response')
        sha, content = response.get('sha'), response.get('content')
        require(isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{40}', sha), 'invalid GitHub blob SHA')
        require(isinstance(content, str), 'ledger content missing')
        try:
            raw = base64.b64decode(content.replace('\n', ''), validate=True)
        except (ValueError, UnicodeError):
            raise BudgetError('invalid ledger encoding') from None
        require(len(raw) <= MAX_BYTES and blob_sha(raw) == sha, 'ledger blob content/hash mismatch')
        return parse_json(raw), sha

    def put(self, old_sha, raw, run_id, mode):
        response = self.request('PUT', self.url, {
            'message': 'Reserve Blacksmith minutes for run ' + run_id + ' (' + mode + ')',
            'content': base64.b64encode(raw).decode('ascii'), 'sha': old_sha, 'branch': self.branch,
        })
        require(isinstance(response, dict) and isinstance(response.get('content'), dict)
                and response['content'].get('sha') == blob_sha(raw)
                and response['content'].get('path') == self.path, 'reservation write receipt mismatch')


def reserve(mode_name, env, policy, api, now_fn=utc_now):
    require(mode_name in policy['modes'], 'unknown mode')
    require(env.get('GITHUB_REPOSITORY') == REPOSITORY, 'repository outside approved scope')
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'only manual GitHub Actions dispatch is authorized')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1', 'reruns are not authorized')
    run_id = env.get('GITHUB_RUN_ID', '')
    require(re.fullmatch(r'[1-9][0-9]{0,19}', run_id), 'invalid GitHub run ID')
    mode = policy['modes'][mode_name]
    month, latest_start = check_window(now_fn(), mode, policy)
    ledger, old_sha = api.get()
    totals, runs = validate_ledger(ledger, policy)
    require(run_id not in runs, 'run ID already reserved; no refunds or duplicate authorization')
    cost = mode['reserved_normalized_minutes']
    total = totals.get(month, 0) + cost
    require(total <= policy['local_stop_normalized_minutes'], 'monthly local stop would be exceeded')
    lifetime_total = sum(totals.values()) + cost
    require(lifetime_total <= policy['lifetime_reservation_limit'], 'lifetime grant stop would be exceeded; renewal unverified')
    now = now_fn()
    require(check_window(now, mode, policy)[0] == month, 'month changed during reservation')
    ledger['months'].setdefault(month, {'reservations': {}})['reservations'][run_id] = {
        'mode': mode_name, 'vcpu': mode['vcpu'], 'timeout_minutes': mode['timeout_minutes'],
        'overhead_minutes': policy['overhead_minutes'], 'reserved_normalized_minutes': cost,
        'reserved_at': timestamp(now),
    }
    raw = (json.dumps(ledger, sort_keys=True, indent=2) + '\n').encode('utf-8')
    require(len(raw) <= MAX_BYTES, 'ledger capacity reached; manual review required')
    api.put(old_sha, raw, run_id, mode_name)  # One CAS attempt; never retry a conflict.
    observed, observed_sha = api.get()
    require(observed_sha == blob_sha(raw) and observed == ledger, 'reservation readback mismatch')
    validate_ledger(observed, policy)
    require(check_window(now_fn(), mode, policy)[0] == month, 'month changed after reservation; retain reservation')
    return {'authorized': 'true', 'mode': mode_name, 'runner': mode['runner'],
            'timeout_minutes': str(mode['timeout_minutes']), 'vcpu': str(mode['vcpu']),
            'reserved_normalized_minutes': str(cost), 'monthly_reserved_normalized_minutes': str(total),
            'lifetime_reserved_normalized_minutes': str(lifetime_total),
            'reservation_id': run_id, 'month': month, 'latest_start_utc': timestamp(latest_start),
            'ledger_blob_sha': observed_sha}


def emit_outputs(path, values):
    require(bool(path), 'GITHUB_OUTPUT missing')
    with open(path, 'a', encoding='utf-8') as stream:
        for key, value in values.items():
            require('\n' not in value and '\r' not in value, 'invalid output value')
            stream.write(key + '=' + value + '\n')
        stream.flush()


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True)
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    try:
        require(bool(env.get('GITHUB_OUTPUT')), 'GITHUB_OUTPUT missing')
        policy = read_policy()
        result = reserve(args.mode, env, policy, GitHubContents(env.get('GH_TOKEN'), policy))
        emit_outputs(env['GITHUB_OUTPUT'], result)
    except (BudgetError, OSError, ValueError, TypeError, KeyError) as error:
        # API bodies, tokens and untrusted ledger text must never reach logs.
        try:
            emit_outputs(env.get('GITHUB_OUTPUT'), {'authorized': 'false'})
        except (BudgetError, OSError):
            pass
        reason = str(error) if isinstance(error, BudgetError) else 'invalid or unavailable budget input'
        print('Blacksmith budget authorization denied: ' + reason + '. No paid job may start.', file=sys.stderr)
        return 1
    print('Blacksmith reservation recorded: ' + result['reservation_id'] + ', ' + result['month']
          + ', ' + result['reserved_normalized_minutes'] + ' normalized minutes.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
