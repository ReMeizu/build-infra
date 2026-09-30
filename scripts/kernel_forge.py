#!/usr/bin/env python3
"""Add only a kernel-toolchain contract to the preserved Forge launcher."""
import hashlib
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / 'vendor/forge'
EXPECTED = '9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8'
if hashlib.sha256((VENDOR / 'forge_ephemeral_build.py').read_bytes()).hexdigest() != EXPECTED:
    raise SystemExit('vendored Forge differs from reviewed source')
sys.path.insert(0, str(VENDOR))
import forge_ephemeral_build as forge
forge.BUILD_ENV_CONTRACTS['kernel-gcc49'] = {
    'kernel_versions': ['3.18', '4.9'], 'jdk': None, 'python': 'python3',
    'tools': ['make', 'gcc', 'binutils', 'bc', 'flex', 'bison', 'pinned AOSP GCC 4.9'],
    'scope': 'kernel objects or full kernel; no Android ROM or firmware package',
}
if __name__ == '__main__':
    raise SystemExit(forge.main())
