#!/usr/bin/env python3
"""Parallelize independent Git snapshots within each original Forge proof pass."""
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
import threading

def warm_metadata(forge,source_root):
    """Finish initial Git/LFS metadata normalization before the two proof passes."""
    progress=forge._SourceProvenanceProgress(Path(source_root),0)
    try:
        forge._source_provenance_snapshot(Path(source_root),progress)
    except BaseException:
        progress.finish('failed')
        raise
    progress.finish('prepared')
    # Never accept or reuse this result. Forge computes both fresh checks itself.

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
            # Git/LFS may briefly create metadata locks even with optional
            # index refresh disabled. Finish Git readers before the original
            # root traversal inventories .repo metadata and hashes its files.
            wait(futures.values())
            # The original algorithm still encodes every path in its original order.
            # Each consumed child receives the unchanged original snapshot result.
            return original(path,progress)
        finally:
            local.cache=None
            for future in futures.values(): future.cancel()
            pool.shutdown(wait=True,cancel_futures=True)
    forge._source_provenance_snapshot=snapshot
    return original
