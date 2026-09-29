#!/usr/bin/env bash
# Retry the failed pre-container provenance check without rewriting Git indices.
set -uo pipefail
cd /home/circleci/m6-runtime
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/mnt/forge-circle-m6/recipe.json')
r=json.loads(p.read_text())
r['idempotency_key']='crdroid-pie-m6-circle-attempt2-readonly-git'
r['timeout_seconds']=420
r['env']['GIT_OPTIONAL_LOCKS']='0'
Path('/home/circleci/m6-private/recipe2.json').write_text(json.dumps(r,indent=2)+'\n')
PY
sudo env FORGE_EPHEMERAL_BASE=/mnt/forge-circle-m6/evidence \
    GIT_OPTIONAL_LOCKS=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*' \
    python3 vendor/forge/forge_ephemeral_build.py --recipe /home/circleci/m6-private/recipe2.json --verbose
result=$?
printf '{"forge_exit":%s}\n' "$result" > /home/circleci/m6-private/result2.json
sudo tar -C /mnt/forge-circle-m6 -I 'zstd -T2 -1' -cf /home/circleci/m6-attempt2-checkpoint.tar.zst.partial . || exit 2
sudo chown circleci:circleci /home/circleci/m6-attempt2-checkpoint.tar.zst.partial
mv /home/circleci/m6-attempt2-checkpoint.tar.zst.partial /home/circleci/m6-attempt2-checkpoint.tar.zst
sha256sum /home/circleci/m6-attempt2-checkpoint.tar.zst > /home/circleci/m6-private/checkpoint2.sha256
exit "$result"
