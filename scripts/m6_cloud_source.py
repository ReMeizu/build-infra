#!/usr/bin/env python3
"""Bounded public-only source preparation on the admitted CircleCI worker."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parents[1]
ROOT = Path('/home/circleci/m6-public-pinned')
EVIDENCE = HERE / 'evidence/m6-cloud-source'
MANIFEST_SHA = '5d415160af39512a9d708def634244cb9707a90704880d4f176aa7c92eb7baa1'
MANIFEST_COMMIT = 'b6d768250babf86854c5b0ff61547b111f05e48e'
LAUNCHER_SHA = '1211b57b57e4122a9c546295a59b37d24068f1164d0e87bef096d5323c413e4f'
MIN_FREE = 35 * 2**30


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or
            str(path) != value or '\\' in value or ':' in value):
        raise ValueError('Unsafe manifest path: ' + value)
    return value


def inventory(raw, count=701):
    tree = ET.fromstring(raw)
    if tree.tag != 'manifest' or tree.find('include') is not None:
        raise ValueError('Manifest must be fully resolved')
    remotes = {r.attrib['name']: r.attrib['fetch'] for r in tree.findall('remote')}
    default = tree.find('default').attrib['remote']
    projects, generated = {}, {}
    for project in tree.findall('project'):
        path = relative(project.get('path', project.attrib['name']))
        revision = project.attrib['revision']
        fetch = remotes[project.get('remote', default)]
        if fetch not in ('https://android.googlesource.com', 'https://github.com/',
                         'https://github.com/nomorecoolnicknames/', '..'):
            raise ValueError('Project is not on an approved public remote')
        if path in projects or not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('Duplicate or unpinned project')
        if path.split('/')[0] in ('.repo', '.forge', 'out') or path == 'vendor/meizu':
            raise ValueError('Non-public source path')
        projects[path] = revision
        for child in list(project):
            if child.tag in ('copyfile', 'linkfile'):
                dest = relative(child.attrib['dest'])
                src = relative(child.attrib['src'])
                if dest in generated:
                    raise ValueError('Duplicate generated path')
                generated[dest] = (child.tag, path + '/' + src)
    if len(projects) != count:
        raise ValueError('Unexpected project count')
    return projects, generated


def public_boundary(root, projects, generated):
    """Reject foreign/private root paths without traversing complete repositories."""
    allowed = set(projects) | set(generated) | {'.repo', 'sync-status.json'}
    prefixes = {str(parent) for path in allowed for parent in
                PurePosixPath(path).parents if str(parent) != '.'}
    def visit(directory):
        for entry in directory.iterdir():
            rel = entry.relative_to(root).as_posix()
            if rel in projects:
                if entry.is_symlink() or not entry.is_dir():
                    raise ValueError('Project root replaced: ' + rel)
            elif rel in generated:
                kind, source = generated[rel]
                if kind == 'linkfile':
                    if not entry.is_symlink() or entry.resolve() != (root / source).resolve():
                        raise ValueError('Manifest link replaced: ' + rel)
                elif entry.is_symlink() or not entry.is_file():
                    raise ValueError('Manifest copy replaced: ' + rel)
                elif entry.read_bytes() != (root / source).read_bytes():
                    raise ValueError('Manifest copy changed: ' + rel)
            elif rel == '.repo':
                if entry.is_symlink() or not entry.is_dir():
                    raise ValueError('Repo metadata replaced')
                local = entry / 'local_manifests'
                if local.exists() and any(local.iterdir()):
                    raise ValueError('Additional manifests forbidden')
            elif rel == 'sync-status.json':
                if entry.is_symlink() or not entry.is_file():
                    raise ValueError('Receipt path replaced')
            elif rel in prefixes and not entry.is_symlink() and entry.is_dir():
                visit(entry)
            else:
                raise ValueError('Foreign path in public cache: ' + rel)
    visit(root)


def environment():
    env = dict(os.environ)
    env.update(GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1',
               GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_COUNT='3',
               GIT_CONFIG_KEY_0='user.name', GIT_CONFIG_VALUE_0='ReMeizu CI',
               GIT_CONFIG_KEY_1='user.email', GIT_CONFIG_VALUE_1='ci@users.noreply.github.com',
               GIT_CONFIG_KEY_2='credential.helper', GIT_CONFIG_VALUE_2='')
    return env


def stop_owned(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def bounded(command, deadline, log, env):
    if time.monotonic() >= deadline:
        raise TimeoutError('Source preparation deadline reached')
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        while process.poll() is None:
            free = shutil.disk_usage(ROOT).free
            print('Public source preparation: free GiB=', free // 2**30, flush=True)
            if free < MIN_FREE:
                raise RuntimeError('Public source disk reserve reached')
            if time.monotonic() >= deadline:
                raise TimeoutError('Source preparation deadline reached')
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if process.returncode:
            raise RuntimeError('Public source command failed: ' + str(process.returncode))
    finally:
        stop_owned(process)


def main():
    # This script has no local/n8n execution mode and no private input handoff.
    if (os.environ.get('CIRCLECI') != 'true' or
            os.environ.get('CIRCLE_PROJECT_USERNAME') != 'ReMeizu' or
            os.environ.get('CIRCLE_PROJECT_REPONAME') != 'build-infra' or
            os.environ.get('CIRCLE_BRANCH') != 'm6-circle-cloud-only'):
        raise RuntimeError('Cloud worker outside authorized preparation scope')
    manifest = HERE / 'inputs/crdroid9-m6-resolved.xml'
    if digest(manifest) != MANIFEST_SHA or digest(HERE / 'scripts/repo-launcher') != LAUNCHER_SHA:
        raise RuntimeError('Pinned public input checksum mismatch')
    projects, generated = inventory(manifest.read_bytes())
    ROOT.mkdir(parents=True, exist_ok=True)
    public_boundary(ROOT, projects, generated)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    # At most 35 minutes here, leaving 25 minutes of the Free job for cache IO.
    job_start = float(Path('/home/circleci/m6-source-ci-start').read_text())
    deadline = time.monotonic() + max(0, 2100 - (time.time() - job_start))
    env = environment()
    repo = [sys.executable, str(HERE / 'scripts/repo-launcher')]
    status = {'sync_complete': False, 'public_revisions_verified': 0,
              'lfs_payloads_verified': False, 'rom_started': False,
              'resolved_manifest_sha256': MANIFEST_SHA, 'manifest_commit': MANIFEST_COMMIT,
              'infra_commit': os.environ.get('CIRCLE_SHA1'), 'job': os.environ.get('CIRCLE_BUILD_NUM')}
    with (EVIDENCE / 'sync.log').open('wb') as log:
        try:
            init = repo + ['init', '-u', 'https://github.com/crdroidandroid/android.git',
                           '-b', MANIFEST_COMMIT, '--depth=1', '--no-clone-bundle',
                           '-g', 'all', '--repo-rev=stable']
            bounded(init, deadline, log, env)
            shutil.copyfile(manifest, ROOT / '.repo/manifests/m6-pinned.xml')
            bounded(init + ['-m', 'm6-pinned.xml'], deadline, log, env)
            bounded(repo + ['sync', '-c', '-j4', '--no-tags', '--no-clone-bundle',
                            '--fail-fast', '--retry-fetches=2'], deadline, log, env)
            actual = (ROOT / '.repo/project.list').read_text().splitlines()
            if len(actual) != 701 or set(actual) != set(projects):
                raise RuntimeError('Actual project inventory differs from pinned manifest')
            for path, revision in projects.items():
                value = subprocess.check_output(['git', '-C', str(ROOT / path),
                                                 'rev-parse', 'HEAD'], env=env,
                                                timeout=10, text=True).strip()
                if value != revision:
                    raise RuntimeError('Wrong revision: ' + path)
                status['public_revisions_verified'] += 1
            status['sync_complete'] = True
            # Public LFS only. Private overlay/corrections are applied after this cache.
            hydrate = dict(env)
            hydrate.pop('GIT_LFS_SKIP_SMUDGE', None)
            for path in projects:
                bounded(['git', '-C', str(ROOT / path), 'lfs', 'pull'], deadline, log, hydrate)
                bounded(['git', '-C', str(ROOT / path), 'lfs', 'fsck'], deadline, log, hydrate)
            status['lfs_payloads_verified'] = True
        except (RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
            status['error'] = str(error)
    public_boundary(ROOT, projects, generated)
    for path in projects:
        project = ROOT / path
        if (project / '.git').exists():
            dirty = subprocess.check_output(['git', '-C', str(project), 'status',
                                             '--porcelain', '--untracked-files=all'],
                                            env=env, timeout=15)
            if dirty:
                raise RuntimeError('Modified project cannot enter public cache: ' + path)
    status['free_bytes'] = shutil.disk_usage(ROOT).free
    raw = json.dumps(status, indent=2) + '\n'
    (ROOT / 'sync-status.json').write_text(raw)
    (EVIDENCE / 'status.json').write_text(raw)
    print(raw, flush=True)
    # Partial public Git downloads may be cached. The final CI check still fails.


if __name__ == '__main__':
    main()
