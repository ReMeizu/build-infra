"""M681 full-kernel contract for the hash-checked Forge launcher."""
from kernel_forge import forge
forge.BUILD_ENV_CONTRACTS['m681-kernel-gcc49'] = {
    'kernel_versions': ['4.9'], 'jdk': None, 'python': 'python3',
    'tools': ['make', 'gcc', 'binutils', 'bc', 'flex', 'bison', 'pinned AOSP GCC 4.9'],
    'scope': 'M681 full kernel compilation only; no flash or runtime acceptance',
}
if __name__ == '__main__':
    raise SystemExit(forge.main())
