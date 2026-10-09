#!/usr/bin/env python3
"""Stream approved public-source native outputs into integrity-protected ciphertext.

This helper never creates releases or uploads anything. Plaintext output remains
in actual tmpfs; only explicitly classified producer outputs are accepted.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import threading

MAX_ASSET = 2 * 1024**3 - 1024**2


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def ram(path):
    path = path.resolve(strict=True)
    kind = subprocess.check_output(['findmnt', '-n', '-T', str(path), '-o', 'FSTYPE'], timeout=5).strip()
    if kind != b'tmpfs':
        raise ValueError('plaintext, crypto work and ciphertext outputs require actual RAM')
    return path


def safe(name):
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or '..' in path.parts or str(path) != name
            or any(p in ('.git', '.ssh', '.gnupg') or '.private' in p for p in path.parts)):
        raise ValueError('unsafe or private carrier path rejected')
    return name


def gpg(home, args, **kwargs):
    return subprocess.run(['gpg', '--batch', '--no-tty', '--homedir', str(home), *args],
                          capture_output=True, check=True, timeout=30, **kwargs)


def keyring(work, key_file):
    home = work / 'keyring'
    home.mkdir(mode=0o700)
    gpg(home, ['--import', str(key_file)])
    listing = gpg(home, ['--with-colons', '--list-keys']).stdout.decode().splitlines()
    primary = []
    expect = False
    for line in listing:
        fields = line.split(':')
        if fields[0] == 'pub':
            expect = True
        elif fields[0] == 'fpr' and expect:
            primary.append(fields[9])
            expect = False
    if len(primary) != 1:
        raise ValueError('exact single task recipient required')
    return home, primary[0]


def policy_files(policy):
    if (policy.get('schema') != 'remeizu.public-native-output-policy.v1' or
            policy.get('plaintext_scope') != 'public-source-native-build-only' or
            policy.get('private_inputs_admitted') is not False or
            not re.fullmatch('[0-9a-f]{64}', policy.get('source_lock_sha256', ''))):
        raise ValueError('reviewed public-source native input policy required')
    files = policy['outputs']
    if not files or len(files) > 10000 or len({f['path'] for f in files}) != len(files):
        raise ValueError('bounded explicit unique output allowlist required')
    for row in files:
        name = safe(row['path'])
        if row['kind'] not in ('native-elf', 'native-image', 'public-producer-evidence'):
            raise ValueError('unknown or private Android output class rejected')
        if not re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) or type(row.get('bytes')) is not int or row['bytes'] < 0:
            raise ValueError('actual producer output digest and size required')
    return files


def admitted_files(root, policy):
    files = policy_files(policy)
    for row in files:
        name = safe(row['path'])
        item = root / name
        if item.is_symlink() or any(p.is_symlink() for p in item.parents) or not item.is_file():
            raise ValueError('regular canonical producer output required')
        item.resolve().relative_to(root)
        if item.stat().st_size != row['bytes'] or sha(item) != row['sha256']:
            raise ValueError('actual producer output SHA/size differs from allowlist')
    return files


def seal(root, policy_file, policy_sha, public_key, recipient, output, part_bytes):
    root, output = ram(root), ram(output)
    if not 1024 <= part_bytes <= MAX_ASSET:
        raise ValueError('each ciphertext release asset must be under 2 GiB')
    if sha(policy_file) != policy_sha:
        raise ValueError('reviewed output policy SHA mismatch')
    if b'PRIVATE KEY' in public_key.read_bytes():
        raise ValueError('private key must never enter hosted encryption inputs')
    policy = json.loads(policy_file.read_text())
    files = admitted_files(root, policy)
    home, actual = keyring(output, public_key)
    if actual != recipient:
        raise ValueError('task recipient fingerprint mismatch')
    log = output / 'gpg-encrypt.private.log'
    errors = []
    with log.open('wb') as stderr:
        proc = subprocess.Popen(['gpg', '--batch', '--no-tty', '--homedir', str(home),
            '--trust-model', 'always', '--compress-algo', 'none', '--cipher-algo', 'AES256',
            '--force-mdc', '--no-emit-version', '--status-fd', '2', '--recipient', recipient,
            '--encrypt'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)

        def feed():
            try:
                with tarfile.open(fileobj=proc.stdin, mode='w|gz') as archive:
                    body = policy_file.read_bytes()
                    info = tarfile.TarInfo('NATIVE_OUTPUT_POLICY.json')
                    info.size, info.mode = len(body), 0o600
                    archive.addfile(info, io.BytesIO(body))
                    for row in files:
                        item = root / row['path']
                        info = tarfile.TarInfo(row['path'])
                        info.size, info.mode = row['bytes'], item.stat().st_mode & 0o777
                        with item.open('rb') as source:
                            archive.addfile(info, source)
                proc.stdin.close()
            except Exception as error:
                errors.append(type(error).__name__)
                proc.stdin.close()

        writer = threading.Thread(target=feed)
        writer.start()
        parts, combined = [], hashlib.sha256()
        index = 0
        while True:
            block = proc.stdout.read(min(1024**2, part_bytes))
            if not block:
                break
            name = 'native-output.pgp.part-' + str(index).zfill(4)
            item = output / name
            digest, count = hashlib.sha256(), 0
            with item.open('xb') as dest:
                while block:
                    remaining = part_bytes - count
                    chunk, block = block[:remaining], block[remaining:]
                    dest.write(chunk); digest.update(chunk); combined.update(chunk)
                    count += len(chunk)
                    if count == part_bytes:
                        break
                    block = proc.stdout.read(min(1024**2, part_bytes - count))
            parts.append({'name': name, 'bytes': count, 'sha256': digest.hexdigest()})
            index += 1
            if index >= 999:
                raise ValueError('ciphertext plus manifest exceeds release asset count')
        proc.stdout.close()
        writer.join(timeout=60)
        if writer.is_alive() or proc.wait(timeout=60) != 0 or errors or not parts:
            raise ValueError('ciphertext producer failed; partial assets are not admitted')
    if b'[GNUPG:] END_ENCRYPTION' not in log.read_bytes():
        raise ValueError('actual encryption completion status absent')
    admitted_files(root, policy)  # Before/after source identity remains exact.
    manifest = {'schema': 'remeizu.encrypted-public-native-retention.v1',
                'algorithm': 'OpenPGP AES256 with forced MDC; verify before extracting',
                'recipient_fingerprint': recipient, 'policy_sha256': policy_sha,
                'source_lock_sha256': policy['source_lock_sha256'], 'parts': parts,
                'ciphertext_sha256': combined.hexdigest(),
                'plaintext_scope': 'public-source-native-build-only', 'uploads_performed': False}
    (output / 'CIPHERTEXT_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def restore(parts_root, manifest_file, private_key, output, max_bytes):
    output = ram(output)
    manifest = json.loads(manifest_file.read_text())
    if manifest['schema'] != 'remeizu.encrypted-public-native-retention.v1':
        raise ValueError('unknown ciphertext manifest')
    cipher = output / 'combined.pgp'
    combined = hashlib.sha256()
    with cipher.open('xb') as dest:
        for row in manifest['parts']:
            name = safe(row['name'])
            item = parts_root / name
            if item.stat().st_size != row['bytes'] or sha(item) != row['sha256']:
                raise ValueError('downloaded ciphertext asset hash/size mismatch')
            with item.open('rb') as source:
                for block in iter(lambda: source.read(4 * 1024**2), b''):
                    dest.write(block); combined.update(block)
    if combined.hexdigest() != manifest['ciphertext_sha256']:
        raise ValueError('complete ciphertext hash mismatch')
    home, fingerprint = keyring(output, private_key)
    if fingerprint != manifest['recipient_fingerprint']:
        raise ValueError('private recipient identity mismatch')
    plain = output / 'plaintext.tar.gz.partial'
    log = output / 'gpg-decrypt.private.log'
    with log.open('wb') as stderr, plain.open('xb') as dest:
        os.chmod(plain, 0o600)
        proc = subprocess.Popen(['gpg', '--batch', '--no-tty', '--homedir', str(home),
            '--status-fd', '2', '--decrypt', str(cipher)], stdout=subprocess.PIPE, stderr=stderr)
        count = 0
        for block in iter(lambda: proc.stdout.read(4 * 1024**2), b''):
            count += len(block)
            if count > max_bytes:
                proc.terminate()
                proc.wait(timeout=10)
                raise ValueError('decrypted RAM archive exceeds admitted size cap')
            dest.write(block)
        proc.stdout.close()
        code = proc.wait(timeout=60)
    status = log.read_bytes()
    if code or b'[GNUPG:] GOODMDC' not in status or b'[GNUPG:] DECRYPTION_OKAY' not in status:
        raise ValueError('authenticated decryption failed; plaintext is not admitted')
    # No archive member is inspected or extracted before integrity acceptance.
    with tarfile.open(plain) as archive:
        members = archive.getmembers()
        for member in members:
            safe(member.name)
            if not member.isfile():
                raise ValueError('encrypted output carrier links/special files rejected')
        rows = [m for m in members if m.name == 'NATIVE_OUTPUT_POLICY.json']
        if len(rows) != 1:
            raise ValueError('single encrypted output policy required')
        policy_bytes = archive.extractfile(rows[0]).read()
        if hashlib.sha256(policy_bytes).hexdigest() != manifest['policy_sha256']:
            raise ValueError('encrypted policy differs from original reviewed producer policy')
        policy = json.loads(policy_bytes)
        policy_files(policy)
        if policy['source_lock_sha256'] != manifest['source_lock_sha256'] or policy['plaintext_scope'] != manifest['plaintext_scope']:
            raise ValueError('encrypted source scope differs from accepted manifest')
        expected = {r['path']: r for r in policy['outputs']}
        if len(expected) != len(policy['outputs']) or {m.name for m in members} != set(expected) | {'NATIVE_OUTPUT_POLICY.json'}:
            raise ValueError('encrypted archive allowlist coverage mismatch')
        if sum(r['bytes'] for r in expected.values()) > max_bytes:
            raise ValueError('expanded restored outputs exceed admitted RAM size cap')
        for member in members:
            if member.name in expected and member.size != expected[member.name]['bytes']:
                raise ValueError('archive member size differs from producer witness')
        extracted = output / 'accepted'
        extracted.mkdir(mode=0o700)
        for member in members:
            if member.name not in expected:
                continue
            row = expected[member.name]
            dest = extracted / safe(member.name)
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with dest.open('xb') as target:
                shutil.copyfileobj(archive.extractfile(member), target)
            if dest.stat().st_size != row['bytes'] or sha(dest) != row['sha256']:
                raise ValueError('restored native output differs from actual producer witness')
            dest.chmod(member.mode)
    result = {'schema': 'remeizu.authenticated-native-output-restore.v1',
              'authenticated_decryption_pass': True, 'all_producer_output_sha_pass': True,
              'restored_output_count': len(expected), 'output_root': str(extracted)}
    (output / 'RESTORE_RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    seal_args = sub.add_parser('seal')
    for name in ('root', 'policy', 'public-key', 'output'):
        seal_args.add_argument('--' + name, type=Path, required=True)
    seal_args.add_argument('--expected-policy-sha256', required=True)
    seal_args.add_argument('--recipient', required=True)
    seal_args.add_argument('--part-bytes', type=int, default=512 * 1024**2)
    restore_args = sub.add_parser('restore')
    for name in ('parts-root', 'manifest', 'private-key', 'output'):
        restore_args.add_argument('--' + name, type=Path, required=True)
    restore_args.add_argument('--max-plain-bytes', type=int, default=8 * 1024**3)
    args = parser.parse_args()
    if args.action == 'seal':
        result = seal(args.root, args.policy, args.expected_policy_sha256,
                      args.public_key, args.recipient, args.output, args.part_bytes)
    else:
        result = restore(args.parts_root, args.manifest, args.private_key, args.output, args.max_plain_bytes)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
