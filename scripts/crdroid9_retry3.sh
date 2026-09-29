#!/usr/bin/env bash
set -uo pipefail
cd /home/circleci/m6-runtime
python3 scripts/crdroid9_scope_kernel.py || exit 2
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('/mnt/forge-circle-m6/recipe.json').read_text())
r['idempotency_key']='crdroid-pie-m6-circle-attempt3-kernel-subtree'
r['timeout_seconds']=240
r['env']['GIT_OPTIONAL_LOCKS']='0'
Path('/home/circleci/m6-private/recipe3.json').write_text(json.dumps(r,indent=2)+'\n')
PY
sudo env FORGE_EPHEMERAL_BASE=/mnt/forge-circle-m6/evidence \
    GIT_OPTIONAL_LOCKS=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*' \
    python3 vendor/forge/forge_ephemeral_build.py --recipe /home/circleci/m6-private/recipe3.json --verbose
result=$?
printf '{"forge_exit":%s}\n' "$result" > /home/circleci/m6-private/result3.json
sudo tar -C /mnt/forge-circle-m6 -I 'zstd -T2 -1' -cf /home/circleci/m6-attempt3-checkpoint.tar.zst.partial . || exit 2
sudo chown circleci:circleci /home/circleci/m6-attempt3-checkpoint.tar.zst.partial
mv /home/circleci/m6-attempt3-checkpoint.tar.zst.partial /home/circleci/m6-attempt3-checkpoint.tar.zst
sha256sum /home/circleci/m6-attempt3-checkpoint.tar.zst > /home/circleci/m6-private/checkpoint3.sha256
exit "$result"
