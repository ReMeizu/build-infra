"""Exact A11 GN syntax correction, preserving the admitted source cohort."""
import hashlib
import json
from pathlib import Path

CORRECTION={'path':'inputs/LIBHYBRIS_GN_PREPEND_PROOF.a12.json',
            'sha256':'6f3638c36a21c60f63fd5c552c2f91e9bbf0b8867ec98c9028bea7c4f32bc374'}
OLD_PATCH={'path':'inputs/19-A13_HEADER_GN.patch',
           'sha256':'151744bbd90fe24b992417fc8ea0a4ca344fa7c96b35b94f7230ac9e71975259',
           'target':'third_party/libhybris'}
NEW_PATCH={'path':'inputs/19-A13_HEADER_GN_PREPEND.a12.patch',
           'sha256':'b40f52b5209b987579669f15b68694d148b275e3e25df2c004d10adfc609bfcf',
           'target':'third_party/libhybris'}

def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_patch_source_correction(lock,inputs,thin):
    if lock.get('patch_source_correction')!=CORRECTION or digest(thin/CORRECTION['path'])!=CORRECTION['sha256']:
        raise ValueError('reviewed libhybris GN correction proof differs')
    proof=json.loads((thin/CORRECTION['path']).read_text())
    if (proof.get('schema')!='remeizu.libhybris-gn-list-prepend-source-correction.v1' or
            proof.get('parent_gn_inputs_sha256')!='3a2b05b6d5c2e0493b494d816fa52ea5b2d82042b464ad8b47e0655fd5ea90eb' or
            proof.get('parent_public_lock_sha256')!='adc7e7ed1cc120c06cffcec30ad713efa5b35a0d414c52e48310ce6e99c8db6e' or
            proof.get('original_patch_row')!=OLD_PATCH or proof.get('corrected_patch_row')!=NEW_PATCH or
            proof.get('selected_cohort_proof')!=lock['cohort_proof']):
        raise ValueError('actual libhybris correction parent or source binding differs')
    for row in (OLD_PATCH,NEW_PATCH):
        path=thin/row['path']
        if path.is_symlink() or not path.is_file() or digest(path)!=row['sha256']:
            raise ValueError('actual original/corrected libhybris patch bytes differ')
    patches=inputs['patches']
    if patches.count(NEW_PATCH)!=1 or OLD_PATCH in patches:
        raise ValueError('actual libhybris patch substitution differs')
    restored=[OLD_PATCH if row==NEW_PATCH else row for row in patches]
    if canonical(restored)!='b7048ee44fbf61cd4e441106179e87906558bc88b5665d9834f95cc71c2677b0':
        raise ValueError('other source patch rows or patch order changed')
    if canonical({row['path']:row for row in inputs['source_files']})!='0d0c87444c1aa5137b8fdb1b98aec9704d8a1e743dde5acdfa838ed87948a0bf':
        raise ValueError('A11 source136 member rows changed during GN correction')
    if canonical(inputs['projects'])!='e7b3938e6f32facb5936d705d12633f9285d6f41465dd4604573411b11ad2b0c':
        raise ValueError('A11 source136 project rows changed during GN correction')
    return proof
