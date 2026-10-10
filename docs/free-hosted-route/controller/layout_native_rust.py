#!/usr/bin/env python3
"""Materialize official Rust component manifest payloads in a fresh Forge RAM prefix.

Uses the file/dir and default bin/lib/share prefix rules of the admitted official
install.sh, without its uninstall/backup/remove behavior. No arbitrary host tool
is installed and no unlisted extracted file can be consumed.
"""
from pathlib import Path
import shutil
from native_gn_worker import safe_path, sha, verify_file


def project_manifest(root, package, members):
    inventory = {m['path']: m for m in members if 'sha256' in m}
    components_path = package + '/components'
    components = verify_file(root, inventory[components_path]).read_text().splitlines()
    output = {}
    for component in components:
        safe_path(component)
        name = package + '/' + component + '/manifest.in'
        manifest = verify_file(root, inventory[name]).read_text().splitlines()
        for line in manifest:
            kind, relative = line.split(':', 1)
            safe_path(relative)
            if relative.split('/')[0] not in ('bin', 'lib', 'share', 'etc'):
                raise ValueError('unproven official Rust prefix directive')
            source = package + '/' + component + '/' + relative
            if kind == 'file':
                selected = [source] if source in inventory else []
            elif kind == 'dir':
                selected = [x for x in inventory if x.startswith(source + '/')]
            else:
                raise ValueError('unknown official Rust manifest directive')
            if not selected:
                raise ValueError('official Rust manifest payload missing')
            for path in selected:
                destination = path[len(package + '/' + component + '/'):]
                safe_path(destination)
                item = inventory[path]
                if destination in output and output[destination]['sha256'] != item['sha256']:
                    raise ValueError('conflicting official Rust component payloads')
                output[destination] = dict(item, destination=destination)
    return components, list(output.values())


def install(root, package, members, target):
    components, projection = project_manifest(root, package, members)
    # A host and AArch64 std archive share one fresh prefix. Existing bytes may
    # only be identical admitted payloads; never remove/overwrite stale tools.
    target.mkdir(parents=True, exist_ok=True)
    for item in projection:
        original = verify_file(root, item)
        dst = target/item['destination']
        if dst.is_symlink():
            raise ValueError('Rust payload target is a symlink')
        if dst.exists():
            if not dst.is_file() or sha(dst) != item['sha256']:
                raise ValueError('Rust payload target collision')
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, dst)
        mode = 0o755 if item['destination'].startswith('bin/') or item.get('mode', 0) & 0o111 else 0o644
        dst.chmod(mode)
        if sha(dst) != item['sha256']:
            raise ValueError('Rust payload differs from admitted archive member')
    return {'components': components, 'files': len(projection),
            'native_path': str(target), 'layout': 'official manifest default prefix; no uninstall/backup',
            'payload_sha256': {x['destination']: x['sha256'] for x in projection}}
