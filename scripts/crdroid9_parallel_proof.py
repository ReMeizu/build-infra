#!/usr/bin/env python3
"""Parallelize independent Git snapshots within each original Forge proof pass."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

class Counter:
    def __init__(self): self.files=0; self.bytes_read=0
    def visit(self,path): pass
    def read(self,size): self.bytes_read+=size
    def file_done(self): self.files+=1

def install(forge,source_root,workers=4):
    original=forge._source_provenance_snapshot
    local=threading.local()
    root=Path(source_root).resolve()
    def worker(path):
        local.worker=True
        counter=Counter()
        try: return original(path,counter),counter
        finally: local.worker=False
    def snapshot(path,progress=None):
        resolved=Path(path).resolve()
        if getattr(local,'worker',False): return original(path,progress)
        cache=getattr(local,'cache',None)
        if cache is not None and resolved in cache:
            proof,counter=cache[resolved].result()
            if progress is not None:
                progress.files+=counter.files
                progress.bytes_read+=counter.bytes_read
            return proof
        listing=root/'.repo/project.list'
        if resolved!=root or not listing.is_file(): return original(path,progress)
        projects=[]
        for rel in listing.read_text().splitlines():
            candidate=(root/rel).resolve()
            assert candidate.is_relative_to(root) and candidate!=root
            if (candidate/'.git').exists(): projects.append(candidate)
        pool=ThreadPoolExecutor(max_workers=workers)
        futures={p:pool.submit(worker,p) for p in projects}
        local.cache=futures
        try:
            # The original algorithm still encodes every path in its original order.
            # Each consumed child receives the unchanged original snapshot result.
            return original(path,progress)
        finally:
            local.cache=None
            for future in futures.values(): future.cancel()
            pool.shutdown(wait=True,cancel_futures=True)
    forge._source_provenance_snapshot=snapshot
    return original
