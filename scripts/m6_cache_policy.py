"""Apply strict compiler cache checks after the nine retained corrections."""
import hashlib
from pathlib import Path

BEFORE_SHA = 'd2abf33541ac824572c52ea2970816be28ff87102056ce7e8f4447e5034dc9cb'


def patched(raw):
    if hashlib.sha256(raw).hexdigest() != BEFORE_SHA:
        raise ValueError('Unexpected pinned ccache.mk; do not patch by guesswork')
    old_check = b'  export CCACHE_COMPILERCHECK ?= content'
    old_sloppy = b'  # See man page, optimizations to get more cache hits\n  # implies that __DATE__ and __TIME__ are not critical for functionality.\n  # Ignore include file modification time since it will depend on when\n  # the repo was checked out\n  export CCACHE_SLOPPINESS := time_macros,include_file_mtime,file_macro'
    for needle in (old_check, old_sloppy):
        if raw.count(needle) != 1:
            raise ValueError('Pinned cache contract missing')
    raw = raw.replace(old_check, b'  override export CCACHE_COMPILERCHECK := content')
    return raw.replace(old_sloppy, b'  # Validate preprocessed inputs and compiler bytes for cross-host cache use.\n  override export CCACHE_NODIRECT := 1\n  override export CCACHE_SLOPPINESS :=')


def apply(root):
    path = Path(root) / 'build/make/core/ccache.mk'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Cache policy destination replaced')
    raw = patched(path.read_bytes())
    path.write_bytes(raw)
    return {'path': 'build/make/core/ccache.mk', 'before_sha256': BEFORE_SHA,
            'after_sha256': hashlib.sha256(raw).hexdigest(),
            'compiler_check': 'content', 'direct': False, 'sloppiness': ''}
