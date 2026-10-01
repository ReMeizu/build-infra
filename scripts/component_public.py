#!/usr/bin/env python3
"""Anonymous immutable-source preflight; never reads credentials or builds code."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def get_json(url, frontend=False, direct=False):
    argv = ['curl', '--silent', '--show-error', '--fail', '--proto', '=https',
            '--connect-timeout', '5', '--max-time', '20',
            '-H', 'Accept: application/vnd.github+json']
    if direct:
        argv += ['--noproxy', '*']
    if frontend:
        # Changes transport routing only; TLS still verifies api.github.com.
        argv += ['-4', '--tls-max', '1.2', '--connect-to',
                 'api.github.com:443:github.com:443']
    result = subprocess.run(argv + [url], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def check_public_source(url, commit, tree, frontend=False, direct=False):
    if frontend and direct:
        raise ValueError('conflicting transport routes')
    match = re.fullmatch(r'https://github[.]com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)[.]git', url)
    if not match or not all(re.fullmatch(r'[0-9a-f]{40}', x) for x in (commit, tree)):
        raise ValueError('invalid immutable GitHub source identity')
    name = '/'.join(match.groups())
    base = 'https://api.github.com/repos/' + name
    repository = get_json(base, frontend, direct)
    if repository.get('full_name') != name or repository.get('private') is not False or repository.get('visibility') != 'public':
        raise ValueError('source repository is not anonymously verified public')
    source = get_json(base + '/git/commits/' + commit, frontend, direct)
    if source.get('sha') != commit or source.get('tree', {}).get('sha') != tree:
        raise ValueError('anonymous commit/tree identity differs from manifest')
    return {'schema': 1, 'url': url, 'commit': commit, 'tree': tree,
            'anonymous_repository_verified': True, 'anonymous_commit_tree_verified': True,
            'credentials_used': False, 'compiler_started': False,
            'transport_frontend_route': frontend, 'transport_direct_route': direct}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('commit')
    parser.add_argument('tree')
    route = parser.add_mutually_exclusive_group()
    route.add_argument('--github-frontend-route', action='store_true')
    route.add_argument('--direct-route', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    proof = check_public_source(args.url, args.commit, args.tree, args.github_frontend_route, args.direct_route)
    data = json.dumps(proof, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(data)
    else:
        print(data, end='')


if __name__ == '__main__':
    main()
