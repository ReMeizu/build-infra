#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
cd "$(dirname "$0")"
test ! -e worker-started
touch worker-started
export PATH="$PWD/fio-fio-3.39:$PATH"
timeout -k 5 120 curl -fL --connect-timeout 15 --max-time 115 https://codeload.github.com/axboe/fio/tar.gz/refs/tags/fio-3.39 -o fio-source.tar.gz > download.log 2>&1
sha256sum fio-source.tar.gz > fio-source.sha256
tar -xzf fio-source.tar.gz
grep -q 'GENERAL PUBLIC LICENSE' fio-fio-3.39/COPYING
(cd fio-fio-3.39; timeout -k 5 180 sh configure --disable-native > ../fio-configure.log 2>&1; timeout -k 5 180 nice -n 10 make -j2 > ../fio-build.log 2>&1)
fio --version > fio-version.txt
python3 -c 'import platform,ssl,json,os; print(json.dumps({"platform":platform.platform(),"openssl":ssl.OPENSSL_VERSION,"load":os.getloadavg()}))' > environment.json
for attempt in 1 2 3; do
  timeout -k 5 150 nice -n 10 ionice -c 2 -n 7 python3 -B cloud_benchmark.py --max-workers 4 --root "$PWD" --file-mib 512 --seconds 8 --output "run-$attempt.json"
done
date -u +%FT%TZ > completed.txt
