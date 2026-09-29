#!/usr/bin/env python3
"""Reject compiler reuse after input/image changes or unresolved container cleanup."""
import json,tempfile
from pathlib import Path
from crdroid9_resume import validate_identity

with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    proof={'git_head':'a','working_tree_sha256':'b'}
    old={'image_id':'sha256:abc','command':['build'],'idempotency_key':'job-10','timeout_seconds':1800}
    new={**old,'idempotency_key':'job-11','timeout_seconds':1500}
    validate_identity(proof,proof,old,new,root)
    def rejected(current,recipe):
        try: validate_identity(proof,current,old,recipe,root)
        except AssertionError: return
        raise AssertionError('Unsafe continuation accepted')
    rejected({**proof,'working_tree_sha256':'changed'},new)
    rejected(proof,{**new,'image_id':'sha256:different'})
    state=root/'evidence/hash/.forge-container/attempt.json'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'cleanup_needed':True}))
    rejected(proof,new)
    state.write_text(json.dumps({'cleanup_needed':False}))
    validate_identity(proof,proof,old,new,root)
print('PASS: same inputs accepted; changed source/image and live cleanup rejected')
