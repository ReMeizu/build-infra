#!/usr/bin/env python3
"""Bounded Linux CPU/RAM/fio measurements; only unique temporary regular files.

Example: python3 run_benchmark.py --mount /mnt/build --output results.json
No packages are installed. --no-disk is safe for local validation.
"""
import argparse
import ctypes
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

MIB = 1024 ** 2
GIB = 1024 ** 3
SCRIPT = Path(__file__).resolve() if '__file__' in globals() and __file__ != '<stdin>' else None


class InterruptedBenchmark(Exception):
    pass


def interrupt(_signum, _frame):
    raise InterruptedBenchmark('benchmark interrupted')


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def command(argv, timeout):
    """Kill and reap the entire owned process group on bounded timeout."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=max(.1, timeout))
        return proc.returncode, stdout, stderr[-2000:]
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return 124, stdout, 'owned process group timed out and was killed'
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise


def limits():
    affinity = sorted(os.sched_getaffinity(0))
    cgroup_lines = (read('/proc/self/cgroup') or '').splitlines()
    v2 = next((x.split(':', 2)[2] for x in cgroup_lines if x.startswith('0::')), '/')
    group = Path('/sys/fs/cgroup') / v2.lstrip('/')
    quota, memory_max = [], []
    # Read effective ancestor limits; the leaf alone may report "max".
    while group == Path('/sys/fs/cgroup') or Path('/sys/fs/cgroup') in group.parents:
        cpu = read(group / 'cpu.max')
        if cpu:
            fields = cpu.split()
            if len(fields) == 2 and fields[0] != 'max':
                quota.append(int(fields[0]) / int(fields[1]))
        mem = read(group / 'memory.max')
        if mem and mem != 'max':
            used = int(read(group / 'memory.current') or '0')
            memory_max.append(max(0, int(mem) - used))
        if group == Path('/sys/fs/cgroup'):
            break
        group = group.parent
    # cgroup v1: locate real controller mounts rather than assume mount names.
    if not any(x.startswith('0::') for x in cgroup_lines):
        memberships = {}
        for line in cgroup_lines:
            parts = line.split(':', 2)
            if len(parts) == 3:
                for controller in parts[1].split(','):
                    memberships[controller] = parts[2]
        for line in (read('/proc/self/mountinfo') or '').splitlines():
            if ' - cgroup ' not in line:
                continue
            before, after = line.split(' - ', 1)
            fields, post = before.split(), after.split()
            controllers = post[2].split(',')
            for controller in ('cpu', 'memory'):
                if controller not in controllers or controller not in memberships:
                    continue
                membership = memberships[controller]
                mount_root = fields[3].rstrip('/')
                base = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4]))
                relative = membership[len(mount_root):].lstrip('/') if membership.startswith(mount_root + '/') or membership == mount_root else ''
                leaf = base / relative
                while leaf == base or base in leaf.parents:
                    if controller == 'cpu':
                        q, period = read(leaf / 'cpu.cfs_quota_us'), read(leaf / 'cpu.cfs_period_us')
                        if q and period and int(q) > 0:
                            quota.append(int(q) / int(period))
                    else:
                        maximum, used = read(leaf / 'memory.limit_in_bytes'), read(leaf / 'memory.usage_in_bytes')
                        if maximum and int(maximum) < 1 << 60:
                            memory_max.append(max(0, int(maximum) - int(used or '0')))
                    if leaf == base:
                        break
                    leaf = leaf.parent
    info = read('/proc/meminfo') or ''
    match = re.search(r'^MemAvailable:\s+(\d+) kB', info, re.M)
    available = int(match.group(1)) * 1024 if match else 256 * MIB
    if memory_max:
        available = min(available, min(memory_max))
    effective = min(len(affinity), min(quota) if quota else len(affinity))
    cpuinfo = read('/proc/cpuinfo') or ''
    model = re.search(r'^(?:model name|Hardware)\s*:\s*(.+)', cpuinfo, re.M)
    return {'affinity_cpu_count': len(affinity), 'cpu_quota_cores': min(quota) if quota else None,
            'effective_cpu_cores': effective, 'cpu_model': model.group(1) if model else None,
            'available_memory_bytes': available, 'cgroup_version': 2 if any(x.startswith('0::') for x in cgroup_lines) else 'v1_or_none',
            'load_average': list(os.getloadavg()), 'affinity': affinity}


def worker(kind, seconds):
    if kind == 'cpu':
        block = b'remeizu-benchmark' * (MIB // 16)
        count = 0
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            hashlib.sha256(block).digest()
            count += len(block)
    else:
        # Two 64MiB buffers: 128MiB payload/process, below the 256MiB cap.
        source, target = bytearray(64 * MIB), bytearray(64 * MIB)
        source[::4096] = b'\xa5' * (len(source) // 4096)
        src = (ctypes.c_char * len(source)).from_buffer(source)
        dst = (ctypes.c_char * len(target)).from_buffer(target)
        count = 0
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            ctypes.memmove(dst, src, len(source))
            count += len(source)
        if target[0] != 0xa5 or target[-4096] != 0xa5:
            raise RuntimeError('memcpy verification failed')
    elapsed = time.monotonic() - start
    return {'bytes_processed': count, 'elapsed_seconds': elapsed,
            'bytes_per_second': count / elapsed, 'payload_memory_bytes': MIB if kind == 'cpu' else 128 * MIB}


def parallel_measure(kind, workers, seconds, affinity):
    procs = []
    start = time.monotonic()
    context = multiprocessing.get_context('fork')

    def run_child(connection, cpu):
        try:
            os.sched_setaffinity(0, {cpu})
            connection.send({'result': worker(kind, seconds)})
        except BaseException as exc:
            connection.send({'error': type(exc).__name__})
        finally:
            connection.close()

    for index in range(workers):
        reader, writer = context.Pipe(duplex=False)
        proc = context.Process(target=run_child, args=(writer, affinity[index % len(affinity)]))
        proc.start()
        writer.close()
        procs.append((proc, reader))
    results, errors = [], []
    deadline = start + seconds + 6
    for proc, reader in procs:
        try:
            if not reader.poll(max(.1, deadline - time.monotonic())):
                raise TimeoutError()
            message = reader.recv()
            if 'result' in message:
                results.append(message['result'])
            else:
                errors.append(message)
        except (TimeoutError, EOFError):
            errors.append({'timeout': True})
        finally:
            if proc.is_alive():
                proc.join(timeout=.3)
            if proc.is_alive():
                proc.kill()
            proc.join()
            reader.close()
    return {'workers': workers, 'worker_seconds': seconds, 'elapsed_wall_seconds': time.monotonic() - start,
            'aggregate_bytes_per_second': sum(x['bytes_per_second'] for x in results),
            'workers_completed': len(results), 'errors': errors, 'method': 'OpenSSL SHA256 via hashlib' if kind == 'cpu' else 'native memcpy, bytes copied (memory traffic roughly twice this)'}


def topology(mount):
    device = mount.stat().st_dev
    major, minor = os.major(device), os.minor(device)
    fstype = 'unknown'
    for line in (read('/proc/self/mountinfo') or '').splitlines():
        fields = line.split()
        if len(fields) > 6 and fields[2] == f'{major}:{minor}' and ' - ' in line:
            fstype = line.split(' - ', 1)[1].split()[0]
    sysdev = Path(f'/sys/dev/block/{major}:{minor}')
    flags = []
    if sysdev.exists():
        resolved = sysdev.resolve()
        for candidate in [resolved, resolved.parent] + list((resolved / 'slaves').glob('*')):
            value = read(candidate / 'queue/rotational')
            if value in ('0', '1'):
                flags.append(int(value))
    return {'filesystem': fstype, 'device_major_minor': f'{major}:{minor}',
            'kernel_rotational_flags': sorted(set(flags)),
            'physical_ssd_hdd': 'unknown: virtual/cloud devices do not prove physical backing',
            'memory_filesystem': fstype in ('tmpfs', 'ramfs', 'devtmpfs')}


def fio_tool():
    tool = shutil.which('fio')
    if not tool:
        return None, {'available': False, 'reason': 'fio executable absent; no buffered fallback'}
    rc, stdout, _ = command([tool, '--version'], 3)
    version = stdout.strip()
    if rc or not re.fullmatch(r'fio-\d+(?:\.\d+)+(?:[-+].*)?', version):
        return None, {'available': False, 'reason': 'executable is not verified Flexible I/O Tester (possible Fiona CLI)'}
    return tool, {'available': True, 'version': version}


def disk_measure(mount, size, seconds, tool, budget):
    start = time.monotonic()
    result = {'mount': str(mount), 'size_bytes': size, 'direct_io': True,
              'ioengine': 'libaio', 'per_case_seconds': seconds, 'cases': []}
    path = None
    identity = None
    try:
        mount = mount.resolve(strict=True)
        if not mount.is_dir() or any(x in str(mount) for x in (':', '\n', '\r')):
            raise ValueError('mount must be an existing directory without fio filename separators')
        result['topology'] = topology(mount)
        if result['topology']['memory_filesystem']:
            raise ValueError('memory filesystem is not a disk test target')
        free = shutil.disk_usage(mount).free
        result['free_before_bytes'] = free
        if free <= size + 5 * GIB:
            raise ValueError('free space must exceed payload plus 5GiB reserve')
        path = mount / ('.remeizu-benchmark-' + uuid.uuid4().hex + '.payload')
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ValueError('payload is not a regular file')
            identity = (st.st_dev, st.st_ino)
            # fio with allow_file_create=0 must find the declared size already
            # present. Sparse sizing is preparation only: prime below must
            # really write every byte before any read measurement is allowed.
            os.ftruncate(fd, size)
        finally:
            os.close(fd)
        common = [tool, '--filename=' + str(path), '--allow_file_create=0', '--overwrite=1',
                  '--unlink=0', '--size=' + str(size), '--direct=1', '--ioengine=libaio',
                  '--numjobs=1', '--group_reporting=1', '--output-format=json', '--eta=never',
                  '--refill_buffers=1', '--randrepeat=0', '--end_fsync=1']
        # Real one-pass writing prevents sparse/unwritten extents faking read results.
        rc, stdout, stderr = command(common + ['--name=prime', '--rw=write', '--bs=1M', '--iodepth=32'], min(25, budget - (time.monotonic() - start)))
        if rc:
            raise RuntimeError('direct fio prefill failed (exit %d): %s' % (rc, stderr[:500]))
        prime = json.loads(stdout)
        if any(j.get('error', 0) for j in prime.get('jobs', [])):
            raise RuntimeError('fio prefill reported a job error')
        if sum(j.get('write', {}).get('io_bytes', 0) for j in prime.get('jobs', [])) < size:
            raise RuntimeError('prefill did not write the complete payload')
        result['prefill_complete'] = True
        cases = [('seq_read', 'read', '1M', 32), ('seq_write', 'write', '1M', 32),
                 ('rand_read_qd1', 'randread', '4k', 1), ('rand_write_qd1', 'randwrite', '4k', 1),
                 ('rand_read_qd32', 'randread', '4k', 32), ('rand_write_qd32', 'randwrite', '4k', 32)]
        for name, rw, bs, depth in cases:
            remaining = budget - (time.monotonic() - start)
            if remaining < seconds + 3:
                result['budget_exhausted'] = True
                break
            rc, stdout, stderr = command(common + ['--name=' + name, '--rw=' + rw, '--bs=' + bs,
                      '--iodepth=' + str(depth), '--time_based=1', '--runtime=' + str(seconds)], min(seconds + 5, remaining))
            case = {'name': name, 'rw': rw, 'block_size': bs, 'queue_depth': depth, 'exit_code': rc}
            if not rc:
                parsed = json.loads(stdout)
                jobs = parsed.get('jobs', [])
                case['fio_job_errors'] = [j.get('error', 0) for j in jobs]
                for direction in ('read', 'write'):
                    data = jobs[0].get(direction, {}) if jobs else {}
                    case[direction] = {k: data[k] for k in ('io_bytes', 'bw_bytes', 'iops', 'runtime') if k in data}
                    case[direction]['completion_latency_ns'] = data.get('clat_ns', {})
                case['iodepth_level_percent'] = jobs[0].get('iodepth_level', {}) if jobs else {}
            else:
                # Keep errors compact; filenames and host identities are omitted.
                case['error'] = stderr.replace(str(path), '<owned-payload>')[:500]
            result['cases'].append(case)
            if rc:
                break
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        result['error'] = str(exc).replace(str(path), '<owned-payload>') if path else str(exc)
    finally:
        if path is not None and identity is not None:
            try:
                st = path.lstat()
                if stat.S_ISREG(st.st_mode) and (st.st_dev, st.st_ino) == identity:
                    path.unlink()
                    result['owned_payload_removed'] = True
                else:
                    result['cleanup_error'] = 'payload identity changed; replacement left untouched'
            except FileNotFoundError:
                result['owned_payload_removed'] = True
            except OSError as exc:
                result['cleanup_error'] = type(exc).__name__
        result['elapsed_wall_seconds'] = time.monotonic() - start
        result['complete'] = (len(result['cases']) == 6 and not result.get('error') and
                              all(c['exit_code'] == 0 and not any(c.get('fio_job_errors', []))
                                  for c in result['cases']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mount', '--root', action='append', default=[], type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--no-disk', action='store_true')
    parser.add_argument('--max-workers', type=int, choices=range(1, 17), default=4)
    parser.add_argument('--file-mib', type=int, choices=range(128, 2049), default=512)
    parser.add_argument('--seconds', type=int, choices=range(8, 13), default=8)
    parser.add_argument('--worker', choices=['cpu', 'memory'], help=argparse.SUPPRESS)
    # Worker duration is internal and uses the same parser, independently bounded.
    if '--worker' in sys.argv:
        parser._option_string_actions['--seconds'].choices = range(1, 9)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, min(args.seconds, 8))))
        return 0
    if not args.no_disk and not args.mount:
        parser.error('explicit --mount is required for disk tests, or use --no-disk')
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    host_limits = limits()
    affinity = host_limits.pop('affinity')
    workers = max(1, min(args.max_workers, len(affinity), math.ceil(host_limits['effective_cpu_cores'])))
    result = {'schema': 1, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'script_sha256': hashlib.sha256(SCRIPT.read_bytes()).hexdigest() if SCRIPT else None,
              'script_input': 'file' if SCRIPT else 'stdin (record transferred script hash externally)',
            'limits': host_limits, 'cpu_worker_cap': args.max_workers,
              'cpu_single': parallel_measure('cpu', 1, 4, affinity),
              'cpu_parallel': parallel_measure('cpu', workers, 4, affinity)}
    memory_workers = min(2, workers, host_limits['available_memory_bytes'] // (256 * MIB))
    result['memory'] = parallel_measure('memory', memory_workers, 3, affinity) if memory_workers else {'unavailable': True, 'reason': 'less than 256MiB available after cgroup limits'}
    tool, result['fio'] = fio_tool() if not args.no_disk else (None, {'skipped': True})
    result['disks'] = [disk_measure(m, args.file_mib * MIB, args.seconds, tool, 100) for m in args.mount] if tool and not args.no_disk else []
    result['limitations'] = ['Short shared-VM samples; load, throttling, virtual storage and writeback policies affect results.',
                            'No physical SSD/HDD conclusion from virtual block-device flags.',
                            'CPU uses SHA256 rather than compiler throughput; no compiler/packages required.']
    result['load_average_after'] = list(os.getloadavg())
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        # Refuse overwriting any existing output evidence or symlink.
        with args.output.open('x') as stream:
            stream.write(rendered)
    else:
        print(rendered, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
