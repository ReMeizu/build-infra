#!/usr/bin/env python3
"""Publish only the ephemeral provider endpoint, never runner configuration."""
import json
import os
from pathlib import Path
import re


def endpoint(env, setup):
    runner = env.get('ROM_RUNNER_NAME', '')
    if not re.fullmatch(r'blacksmith-[A-Za-z0-9-]+', runner):
        raise ValueError('unexpected runner identity')
    host = runner.lower() + '.vm.blacksmith.sh'
    ports = set()
    literal = re.compile(r'ssh\s+-p\s+([0-9]{1,5})\s+runner@' + re.escape(host) + r'(?![a-z0-9.-])', re.IGNORECASE)
    ports.update(int(x) for x in literal.findall(setup))
    for key, value in env.items():
        if re.fullmatch(r'(?:BLACKSMITH_)?SSH_PORT', key) and re.fullmatch(r'[0-9]{1,5}', value):
            ports.add(int(value))
    ports.update(int(x) for x in re.findall(r'(?m)^\s*(?:export\s+)?(?:BLACKSMITH_)?SSH_PORT=[\"\x27]?([0-9]{1,5})[\"\x27]?\s*$', setup))
    ports = {x for x in ports if 1 <= x <= 65535}
    if len(ports) != 1:
        return {'status': 'endpoint_not_found', 'runner': runner}
    port = ports.pop()
    return {'status': 'ready', 'host': host, 'port': port, 'user': 'runner',
            'command': f'ssh -p {port} runner@{host}'}


if __name__ == '__main__':
    setup = Path('/setup.sh')
    data = endpoint(os.environ, setup.read_text() if setup.is_file() else '')
    target = Path('connection/ssh.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + '\n')
    print('Provider endpoint report: ' + data['status'])
