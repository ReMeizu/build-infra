#!/usr/bin/env python3
"""Authenticated streaming checkpoint encryption; the key never enters artifacts."""
import os
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

if __name__=='__main__':
    import io
    from cryptography.exceptions import InvalidTag
    key=os.urandom(32); data=os.urandom(2*1024*1024+29)
    out=io.BytesIO(); encrypt(io.BytesIO(data),out,key)
    plain=io.BytesIO(); decrypt(io.BytesIO(out.getvalue()),plain,key)
    assert plain.getvalue()==data
    altered=bytearray(out.getvalue()); altered[100]^=1
    try: decrypt(io.BytesIO(altered),io.BytesIO(),key)
    except InvalidTag: pass
    else: raise AssertionError('Modified ciphertext accepted')
    print('PASS: checkpoint round trip and tamper rejection')
