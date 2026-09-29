#!/usr/bin/env python3
"""Container-only source-to-object validation; no stock images or firmware inputs."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_bytes(source, name):
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    body = clean.split(name + '[] = {', 1)[1].split('};', 1)[0]
    pattern = r'\{\s*(\w+)\s*,\s*(\w+)\s*,\s*\{([^}]*)\}\s*\}'
    require(not re.sub(pattern, '', body).replace(',', '').strip(), 'unparsed source table')
    rows = []
    for command, count, payload in re.findall(pattern, body):
        command = {'REGFLAG_DELAY': '0xfc', 'REGFLAG_END_OF_TABLE': '0xfd'}.get(command, command)
        values = bytes(int(x.strip(), 0) for x in payload.split(',') if x.strip())
        require(len(values) <= 64, 'oversize panel command')
        rows.append(struct.pack('<IB64s3x', int(command, 0), int(count, 0), values))
    return b''.join(rows)


def elf_tables(path, names):
    data = path.read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01' and data[16:20] == b'\x01\x00\xb7\x00', 'expected AArch64 ELF64 relocatable object')
    sections = {}
    for line in subprocess.check_output(['readelf', '-SW', str(path)], text=True).splitlines():
        m = re.match(r'\s*\[\s*(\d+)\]\s+(\S+)\s+(\S+)\s+([a-fA-F0-9]+)\s+([a-fA-F0-9]+)\s+([a-fA-F0-9]+)', line)
        if m:
            sections[int(m[1])] = (m[3], int(m[4], 16), int(m[5], 16), int(m[6], 16))
    result = {}
    for line in subprocess.check_output(['readelf', '-Ws', str(path)], text=True).splitlines():
        f = line.split()
        if len(f) != 8 or f[-1] not in names:
            continue
        require(f[-1] not in result and f[3] == 'OBJECT' and f[6].isdigit(), 'ambiguous/undefined table')
        kind, base, offset, size = sections[int(f[6])]
        start, extent = int(f[1], 16) - base, int(f[2])
        require(kind != 'NOBITS' and extent > 0 and 0 <= start and start + extent <= size, 'table outside section')
        result[f[-1]] = data[offset + start:offset + start + extent]
    require(set(result) == set(names), 'missing compiled panel table')
    return result


def main():
    source, out, publish = Path('/workspace/src'), Path('/workspace/scratch/out'), Path('/workspace/out')
    require(Path('/.dockerenv').is_file() and Path(__file__).resolve() == source/'.forge/kernel_build.py', 'Forge container only')
    pins = json.loads((source/'.forge/m5s-yassy-inputs.json').read_text())
    for name, digest in pins['source_sha256'].items():
        require(sha(source/'kernel'/name) == digest, 'changed public source: ' + name)
    for name, digest in pins['toolchain_sha256'].items():
        require(sha(source/'toolchain/bin'/name) == digest, 'changed compiler: ' + name)
    require(os.environ.get('FORGE_KERNEL_JOBS') == '2', 'bounded object requires two jobs')
    require(not any(out.iterdir()), 'output is not fresh')
    base = ['make', '-C', str(source/'kernel'), 'O='+str(out), 'ARCH=arm64',
            'CROSS_COMPILE='+str(source/'toolchain/bin/aarch64-linux-android-'), 'V=0']
    log = publish/'kernel-build.log'
    with log.open('x') as stream:
        subprocess.run(base+[pins['defconfig']], check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=90)
        require(sha(out/'.config') == pins['accepted_a4_config_sha256'], 'generated config differs from accepted A4')
        # A direct leaf target bypasses parent subdir-ccflags. Carry only the
        # reviewed parent include paths and -Werror, not a new board/source patch.
        flags = '-Werror ' + ' '.join('-I'+str(source/'kernel'/p) for p in pins['inherit_include_dirs'])
        command = base+['KCFLAGS='+flags, '-j2', pins['target']]
        stream.write(json.dumps(command)+'\n'); stream.flush()
        subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=420)
    obj = out/pins['target']
    names = {'lcm_initialization_setting1':192, 'lcm_deep_sleep_mode_in_setting':5}
    tables = elf_tables(obj, names)
    c = (source/'kernel'/pins['target']).with_suffix('.c').read_text()
    for name, count in names.items():
        expected = table_bytes(c,name)
        require(len(expected) == count*72 and tables[name] == expected, 'compiled panel table differs: '+name)
    nm = subprocess.check_output(['nm', '-S', str(obj)], text=True)
    require(' ili9881_CA_hd720_dsi_vdo_yassy_lcm_drv' in nm, 'own panel descriptor absent')
    artifacts = {'yassy-lcm.o':obj, 'yassy-lcm.o.cmd':obj.with_name('.'+obj.name+'.cmd'), 'kernel.config':out/'.config'}
    for name, path in artifacts.items():
        with path.open('rb') as r, (publish/name).open('xb') as w:
            shutil.copyfileobj(r,w)
    proof = {'kind':'public-m5s-yassy-object-new-runner', 'source':pins, 'command':command,
             'tables':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in tables.items()},
             'artifact_hashes':{n:sha(publish/n) for n in artifacts},
             'config_identical_to_accepted_a4':True,
             'object_byte_identical_to_historical_a4':sha(obj)==pins['historical_object_sha256'],
             'new_environment':True, 'full_kernel_linked':False, 'boot_image_created':False, 'flash_ready':False, 'runtime_verified':False}
    (publish/'kernel-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    (publish/'tool-versions.txt').write_text(subprocess.check_output(['dpkg-query','-W'],text=True))


if __name__ == '__main__':
    main()
