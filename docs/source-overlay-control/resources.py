"""Bounded read-only runner measurements; never imply a full build fits."""
import datetime
import os
from pathlib import Path


def memory_bytes(body):
    values = {}
    for line in body.splitlines():
        fields = line.split()
        if fields and fields[0] in ('MemTotal:', 'MemAvailable:', 'SwapTotal:', 'SwapFree:'):
            if len(fields) != 3 or fields[2] != 'kB' or not fields[1].isdigit():
                raise ValueError('actual kernel memory units required')
            values[fields[0][:-1]] = int(fields[1]) * 1024
    if set(values) != {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
        raise ValueError('complete actual kernel memory counters required')
    if values['MemTotal'] <= 0 or not 0 <= values['MemAvailable'] <= values['MemTotal']:
        raise ValueError('consistent actual memory counters required')
    if not 0 <= values['SwapFree'] <= values['SwapTotal']:
        raise ValueError('consistent actual swap counters required')
    return values


def snapshot(paths):
    body = Path('/proc/meminfo').read_bytes()
    if len(body) > 65536:
        raise ValueError('bounded actual kernel memory counters required')
    measured = {}
    devices = {}
    for name, path in paths.items():
        path = Path(path)
        stat = path.stat()
        fs = os.statvfs(path)
        if fs.f_frsize <= 0 or fs.f_blocks <= 0 or fs.f_bavail < 0 or fs.f_bavail > fs.f_blocks:
            raise ValueError('consistent actual filesystem counters required')
        devices[name] = stat.st_dev
        measured[name] = {
            'capacity_bytes': fs.f_blocks * fs.f_frsize,
            'available_bytes': fs.f_bavail * fs.f_frsize,
            'available_inodes': fs.f_favail,
            'readonly': bool(fs.f_flag & os.ST_RDONLY),
        }
    pairs = [[a, b] for a in sorted(devices) for b in sorted(devices)
             if a < b and devices[a] == devices[b]]
    return {
        'schema': 'remeizu.actual-runner-readonly-resources.v1',
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'memory_bytes': memory_bytes(body.decode('ascii')),
        'available_logical_cpus': len(os.sched_getaffinity(0)),
        'filesystems': measured,
        'same_filesystem_pairs': pairs,
        'full_source_materialization_complete': False,
        'compiler_peak_measured': False,
        'full375_fit_proven': False,
    }


def admit_lower_capacity(measured, source_bytes, reserve_bytes):
    """Check a disk lower bound only; no compiler or RAM acceptance follows."""
    if type(source_bytes) is not int or source_bytes <= 0 or type(reserve_bytes) is not int or reserve_bytes < 0:
        raise ValueError('positive exact source bytes and explicit reserve required')
    if measured.get('schema') != 'remeizu.actual-runner-readonly-resources.v1':
        raise ValueError('actual measured runner snapshot required')
    disk = measured['filesystems']['runner_temp']
    available = disk['available_bytes']
    if type(available) is not int or available < 0 or disk.get('readonly') is not False:
        raise ValueError('actual writable disk counters required')
    if available < source_bytes + reserve_bytes:
        raise ValueError('actual disk lower capacity insufficient')
    return {'measured_available_disk_bytes': available,
            'source_material_bytes': source_bytes, 'reserve_bytes': reserve_bytes,
            'disk_lower_bound_pass': True, 'full375_fit_proven': False}
