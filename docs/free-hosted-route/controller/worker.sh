#!/bin/bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
python3 /workspace/src/native_gn_worker.py
