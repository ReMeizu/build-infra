import json
from pathlib import Path
import unittest
import nonproduction_scope as scope


class NonproductionScopeTests(unittest.TestCase):
    def fixture(self):
        root = Path(scope.__file__).parent;proof=json.loads((root/scope.NAME).read_text())
        return root, {'uninitialized_gitlinks':[dict(proof['gitlink'],directory_mode=493)],
                      'projects':[{'path':proof['parent_project'],'head':proof['parent_head'],'git_tree':proof['parent_git_tree']}],
                      'actual_selected_parts':{'arkcompiler:ets_runtime':{}},
                      'source_files':[{'path':p,'sha256':h} for p,h in {r['path']:r['sha256'] for r in proof['source_route_witnesses']}.items()]}

    def test_exact_original_unused_pointer_is_honest_and_not_materialized(self):
        root, inputs=self.fixture();rows=scope.validate(inputs,root)
        self.assertFalse(rows[0]['materialized']);self.assertFalse(rows[0]['recursive_source_closure'])

    def test_extra_pointer_changed_origin_or_route_or_JS_runtime_refuses(self):
        root, inputs=self.fixture()
        changes=[{'uninitialized_gitlinks':inputs['uninitialized_gitlinks']*2},
                 {'projects':[dict(inputs['projects'][0],head='0'*40)]},
                 {'source_files':[]},{'actual_selected_parts':{}}]
        for change in changes:
            with self.assertRaises(ValueError):scope.validate(dict(inputs,**change),root)


if __name__=='__main__':unittest.main(verbosity=2)
