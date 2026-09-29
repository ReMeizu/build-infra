#!/usr/bin/env bash
# Run only on an authorized disposable cloud worker. Never formats a disk.
set -eu -o pipefail
: "${BENCHMARK_ROOT:?explicit benchmark directory required}"
installation_status=0
(
if ! /usr/bin/fio --version 2>/dev/null | /usr/bin/grep -Eq '^fio-[0-9]+([.][0-9]+)+'; then
  sudo -n timeout --signal=TERM --kill-after=5s 90s apt-get update
  sudo -n timeout --signal=TERM --kill-after=5s 90s env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends fio
fi
) || installation_status=$?
mkdir -p evidence
set +e
PATH=/usr/bin:/bin:/usr/sbin:/sbin timeout --signal=TERM --kill-after=10s 150s python3 -B scripts/cloud_benchmark.py --root "$BENCHMARK_ROOT" --file-mib 512 --seconds 8 --output evidence/benchmark.json
benchmark_status=$?
set -e
python3 - "$benchmark_status" <<'PYRESULT'
import json, pathlib, sys
output = pathlib.Path('evidence/benchmark.json')
if not output.exists():
    output.write_text(json.dumps({'schema': 1, 'measurement_complete': False, 'process_exit_code': int(sys.argv[1])}) + '\n')
data = json.loads(output.read_text())
complete = (int(sys.argv[1]) == 0 and data.get('fio', {}).get('available') is True
            and all(data.get(k, {}).get('workers_completed', 0) > 0
                    and not data[k].get('errors') for k in ('cpu_single', 'cpu_parallel', 'memory'))
            and len(data.get('disks', [])) == 1 and data['disks'][0].get('complete') is True
            and data['disks'][0].get('owned_payload_removed') is True)
pathlib.Path('evidence/benchmark-status.json').write_text(json.dumps({'measurement_complete': complete, 'process_exit_code': int(sys.argv[1])}) + '\n')
if not complete:
    raise SystemExit('Incomplete benchmark; compact evidence retained')
PYRESULT
if [ "$installation_status" -ne 0 ]; then
  exit "$installation_status"
fi
