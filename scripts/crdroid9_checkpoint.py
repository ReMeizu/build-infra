#!/usr/bin/env python3
"""Authenticated streaming checkpoint encryption; the key never enters artifacts."""
import os
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'RMZC1'
def encrypt(source, target, key):
    assert len(key)==32
    nonce=os.urandom(12)
    engine=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
    engine.authenticate_additional_data(MAGIC)
    target.write(MAGIC+nonce)
    while data:=source.read(1024*1024): target.write(engine.update(data))
    target.write(engine.finalize())
    target.write(engine.tag)

def decrypt(source, target, key):
    assert len(key)==32 and source.read(len(MAGIC))==MAGIC
    nonce=source.read(12)
    source.seek(-16,2)
    end=source.tell()
    tag=source.read(16)
    source.seek(len(MAGIC)+12)
    engine=Cipher(algorithms.AES(key),modes.GCM(nonce,tag)).decryptor()
    engine.authenticate_additional_data(MAGIC)
    while source.tell()<end:
        target.write(engine.update(source.read(min(1024*1024,end-source.tell()))))
    target.write(engine.finalize())

def decrypt_stream(source,target,key,expected_sha256):
    """Authenticate a non-seekable download; caller publishes plaintext only afterward."""
    header=source.read(len(MAGIC)+12)
    assert len(key)==32 and len(header)==len(MAGIC)+12 and header.startswith(MAGIC)
    digest=hashlib.sha256(header)
    engine=Cipher(algorithms.AES(key),modes.GCM(header[len(MAGIC):])).decryptor()
    engine.authenticate_additional_data(MAGIC)
    footer=b''
    while data:=source.read(1024*1024):
        digest.update(data)
        footer+=data
        if len(footer)>16:
            target.write(engine.update(footer[:-16]))
            footer=footer[-16:]
    assert len(footer)==16
    target.write(engine.finalize_with_tag(footer))
    assert digest.hexdigest()==expected_sha256,'checkpoint ciphertext hash mismatch'

if __name__=='__main__':
    import io
    from cryptography.exceptions import InvalidTag
    key=os.urandom(32); data=os.urandom(2*1024*1024+29)
    out=io.BytesIO(); encrypt(io.BytesIO(data),out,key)
    plain=io.BytesIO(); decrypt(io.BytesIO(out.getvalue()),plain,key)
    assert plain.getvalue()==data
    stream_plain=io.BytesIO()
    decrypt_stream(io.BytesIO(out.getvalue()),stream_plain,key,hashlib.sha256(out.getvalue()).hexdigest())
    assert stream_plain.getvalue()==data
    altered=bytearray(out.getvalue()); altered[100]^=1
    try: decrypt(io.BytesIO(altered),io.BytesIO(),key)
    except InvalidTag: pass
    else: raise AssertionError('Modified ciphertext accepted')
    try: decrypt_stream(io.BytesIO(altered),io.BytesIO(),key,hashlib.sha256(altered).hexdigest())
    except InvalidTag: pass
    else: raise AssertionError('Modified stream accepted')
    print('PASS: checkpoint round trip and tamper rejection')
