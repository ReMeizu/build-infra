#!/usr/bin/env python3
"""Preserve Forge checks and record source identity alongside a private checkpoint."""
import hashlib,json,os,sys
from pathlib import Path
vendor=Path(__file__).resolve().parents[1]/'vendor/forge'
assert hashlib.sha256((vendor/'forge_ephemeral_build.py').read_bytes()).hexdigest()=='9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8'
sys.path.insert(0,str(vendor))
import forge_ephemeral_build as forge
original=forge.current_source_provenance
def recorded_source_identity(path):
    proof=original(path)
    Path(os.environ['FORGE_SOURCE_PROOF_PATH']).write_text(json.dumps(proof,indent=2)+'\n')
    return proof
forge.current_source_provenance=recorded_source_identity
raise SystemExit(forge.main())
