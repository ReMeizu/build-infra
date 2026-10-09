"""Full kernel contract with bounded resources; preserve the shared Forge code."""
from kernel_forge import forge

forge.BUILD_ENV_CONTRACTS['component-kernel-gcc49'] = {
    'kernel_versions': ['3.18', '4.9'], 'jdk': None, 'python': 'python3',
    'tools': ['make', 'gcc', 'binutils', 'bc', 'flex', 'bison', 'pinned AOSP GCC 4.9'],
    'scope': 'full public kernel only; no ROM, proprietary firmware or flashing',
}
_original_argv = forge.build_docker_argv


def bounded_argv(recipe, output_dir, container_name):
    argv = _original_argv(recipe, output_dir, container_name)
    if recipe.build_env_key == 'component-kernel-gcc49':
        jobs = recipe.env.get('FORGE_KERNEL_JOBS')
        if jobs not in {'1', '2', '3', '4'}:
            raise ValueError('invalid component CPU bound')
        argv[2:2] = ['--cpus=' + jobs, '--memory=5g', '--memory-swap=6g', '--pids-limit=1024']
    return argv


forge.build_docker_argv = bounded_argv
if __name__ == '__main__':
    raise SystemExit(forge.main())
