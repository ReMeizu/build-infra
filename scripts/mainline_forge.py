"""Run the common kernel within the preserved Forge isolation contract."""
from kernel_forge import forge

forge.BUILD_ENV_CONTRACTS['mainline-6.18'] = {
    'kernel_versions': ['6.18'], 'jdk': None, 'python': 'python3',
    'tools': ['GCC 13', 'Clang 18', 'make', 'binutils', 'flex', 'bison'],
    'scope': 'public GPL kernel compile check; hardware acceptance pending',
}
_original_argv = forge.build_docker_argv


def bounded_argv(recipe, output_dir, container_name):
    argv = _original_argv(recipe, output_dir, container_name)
    if recipe.build_env_key == 'mainline-6.18':
        argv[2:2] = ['--cpus=2', '--memory=5g', '--memory-swap=6g', '--pids-limit=1024']
    return argv


forge.build_docker_argv = bounded_argv
if __name__ == '__main__':
    raise SystemExit(forge.main())
