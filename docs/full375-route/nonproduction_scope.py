"""Admit only the exact source-proven unused runtime-core tools pointer."""
import hashlib
import json
from pathlib import Path

NAME = 'runtime_core_nonproduction_scope.json'
SHA = '0c8d98b1e3aad5d888b6056684a3cc067875e0f6692b1d414e98510788fd6d7a'


def validate(inputs, controller=None):
    rows = inputs.get('uninitialized_gitlinks', [])
    if not rows:
        return []
    controller = Path('/workspace/src') if controller is None else Path(controller)
    path = controller / NAME
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != SHA:
        raise ValueError('exact reviewed nonproduction source scope required')
    proof = json.loads(path.read_text())
    if len(rows) != 1:
        raise ValueError('no additional uninitialized source pointer admitted')
    actual = dict(rows[0]);mode = actual.pop('directory_mode', 493)
    if actual != proof['gitlink'] or mode != 493:
        raise ValueError('uninitialized pointer is not the exact original unused tools child')
    project = next((row for row in inputs['projects'] if row['path'] == proof['parent_project']), None)
    if project is None or project['head'] != proof['parent_head'] or project['git_tree'] != proof['parent_git_tree']:
        raise ValueError('original runtime-core parent identity differs')
    if proof['actual_enabled_default_plugins'] != ['ets'] or proof['selected_standalone_overrides'] or proof['tools_plugins_references_found'] or proof['nonproduction_path_scope_proven_from_exact_source'] is not True:
        raise ValueError('real selected-source routing scope not preserved')
    if 'arkcompiler:ets_runtime' not in inputs['actual_selected_parts']:
        raise ValueError('real JavaScript runtime must remain selected')
    wanted = {row['path']: row['sha256'] for row in proof['source_route_witnesses']}
    found = {row['path']: row.get('sha256') for row in inputs['source_files'] if row['path'] in wanted}
    if found != wanted:
        raise ValueError('exact original source route/default witnesses differ')
    return rows
