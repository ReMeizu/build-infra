"""Measured admission for a j2 native intermediate; no full375 claims."""
import json
import os
from pathlib import Path
import shutil

GIB = 1024 ** 3
RAM_BYTES = 10 * GIB

def require(value, message):
    if not value:
        raise ValueError(message)

def snapshot(output):
    mem = next(int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    cg = Path('/sys/fs/cgroup')
    cpu = (cg / 'cpu.max').read_text().split() if (cg / 'cpu.max').exists() else None
    cap = (cg / 'memory.max').read_text().strip() if (cg / 'memory.max').exists() else None
    if cap and cap != 'max':
        mem = min(mem, max(0, int(cap) - int((cg / 'memory.current').read_text())))
    return {'available_bytes': mem, 'cpu_affinity': len(os.sched_getaffinity(0)),
            'cpu_quota': None if not cpu or cpu[0] == 'max' else int(cpu[0]) / int(cpu[1]),
            'memory_max': cap, 'tmpfs_free_bytes': shutil.disk_usage(output).free}

def admit_values(row, phase, source_bytes, rust_bytes):
    require(phase in ('prepare', 'libraries', 'images'), 'unknown resource phase')
    require(type(source_bytes) is int and 0 < source_bytes < 4 * GIB and type(rust_bytes) is int and 0 <= rust_bytes < GIB,
            'measured native source/Rust bound missing')
    require(row['cpu_affinity'] >= 2 and (row['cpu_quota'] is None or row['cpu_quota'] >= 2), 'actual two-job CPU allowance required')
    mem_floor = 12 * GIB if phase == 'prepare' else 3 * GIB
    free_floor = source_bytes + rust_bytes + 6 * GIB if phase == 'prepare' else (5 * GIB if phase == 'images' else 4 * GIB)
    require(row['available_bytes'] >= mem_floor, 'actual native memory headroom below selected phase floor')
    require(row['tmpfs_free_bytes'] >= free_floor, 'actual native tmpfs capacity below selected phase floor')
    return dict(row, phase=phase, jobs=2, source_bytes=source_bytes, rust_layout_bytes=rust_bytes,
                memory_floor_bytes=mem_floor, free_floor_bytes=free_floor,
                full375_phone=False, runtime=False)

def admit(output, phase, inputs):
    require(inputs.get('free_hosted_intermediate') is True, 'explicit public intermediate resource successor required')
    require(os.statvfs(output).f_fsid != os.statvfs('/').f_fsid, 'distinct RAM output mount required')
    mounts = Path('/proc/mounts').read_text().splitlines()
    require(any(line.split()[1] == str(output) and line.split()[2] == 'tmpfs' for line in mounts) or
            any(str(output).startswith(line.split()[1].rstrip('/') + '/') and line.split()[2] == 'tmpfs' for line in mounts), 'tmpfs compilation output required')
    row = admit_values(snapshot(output), phase, inputs['source_bytes'], inputs['free_hosted_rust_layout_bytes'])
    target = Path(output) / ('FREE_HOSTED_RESOURCE.' + phase + '.json')
    target.write_text(json.dumps(row, indent=2) + '\n')
    return row
