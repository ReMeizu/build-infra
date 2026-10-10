#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
SOURCE_ROOT="$PWD"
BENCH_ROOT=$(mktemp -d "${RUNNER_TEMP:-/tmp}/remeizu-bench-20261010.XXXXXX")
mkdir -p evidence
cp scripts/cloud_benchmark.py scripts/farm-worker.sh "$BENCH_ROOT/"
if ! test -f /usr/include/libaio.h; then
  sudo -n timeout -k 5 90 apt-get update
  sudo -n timeout -k 5 90 env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libaio-dev
fi
set +e
timeout -k 10 600 bash "$BENCH_ROOT/farm-worker.sh"
suite_status=$?
set -e
cp "$BENCH_ROOT"/run-*.json "$BENCH_ROOT"/environment.json "$BENCH_ROOT"/fio-version.txt evidence/ 2>/dev/null || true
printf '%s\n' "$suite_status" > evidence/suite-exit.txt
cd "$BENCH_ROOT"
curl -4 -fL --connect-timeout 15 --max-time 150 https://geekbench-cdn.b-cdn.net/Geekbench-7.1.0-Linux.tar.gz -o geekbench.tar.gz
echo '411b72a9c851b69e6f91d390649d419e2e625f475e3983880169651ca27a8672  geekbench.tar.gz' | sha256sum -c -
tar -xzf geekbench.tar.gz
cd Geekbench-7.1.0-Linux
./geekbench7 --help > "$SOURCE_ROOT/evidence/geekbench-help.txt" 2>&1 || true
set +e
timeout -k 10 480 ./geekbench7 --cpu > "$SOURCE_ROOT/evidence/geekbench.txt" 2>&1
geek_status=$?
set -e
printf '%s\n' "$geek_status" > "$SOURCE_ROOT/evidence/geekbench-exit.txt"
cd "$SOURCE_ROOT"
python3 - <<'PY'
import json,pathlib,re,datetime
p=pathlib.Path('evidence')
t=(p/'geekbench.txt').read_text(errors='replace')
links=re.findall(r'https://browser\.geekbench\.com/[^\s]+',t)
single=re.search(r'Single-Core Score\s+(\d+)',t)
multi=re.search(r'Multi-Core Score\s+(\d+)',t)
(p/'geekbench-result.json').write_text(json.dumps({'version':'7.1.0','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit':int((p/'geekbench-exit.txt').read_text()),'single':int(single[1]) if single else None,'multi':int(multi[1]) if multi else None,'links':links},indent=2)+'\n')
PY
test "$suite_status" -eq 0
test "$geek_status" -eq 0
