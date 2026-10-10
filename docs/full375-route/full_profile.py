"""Exact source-backed canonical full phone profile; no runtime acceptance."""
import hashlib
import json
from pathlib import Path

COVERAGE_NAME = 'canonical_full_phone_coverage.json'
COVERAGE_SHA = 'abb1da10781915964ed0307fc5f2642054b2b6cb1a4843211698cd4beaf139a7'


def require_profile(inputs, controller=None):
    if inputs.get('full_phone_profile_kind') != 'canonical-full-gui-a2':
        raise ValueError('explicit source-backed canonical full GUI profile required')
    if inputs.get('full_phone_source_closed') is not True or inputs.get('canonical_full_phone_source_bindings_verified') is not True:
        raise ValueError('complete production sources and canonical binding admission required')
    controller = Path('/workspace/src') if controller is None else Path(controller)
    path = controller / COVERAGE_NAME
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != COVERAGE_SHA:
        raise ValueError('exact reviewed original request coverage bytes required')
    coverage = json.loads(path.read_text())
    if coverage['original_requested_count'] != 375 or coverage['actual_canonical_component_count'] != 365 or coverage['actual_parsed_selected_count_including_dynamic2'] != 366:
        raise ValueError('actual canonical and historical counts differ')
    if coverage['source_default_guard_review_complete'] is not True or coverage['canonical_full_phone_source_bindings_verified'] is not True or coverage['new_alias_groups_or_target_stubs'] is not False:
        raise ValueError('real provider/API/default binding proof required')
    actual = inputs.get('actual_selected_parts', {})
    if actual != coverage['actual_selected_parts']:
        raise ValueError('actual selection differs from complete canonical phone profile')
    if inputs.get('original375_selected_parts') != coverage['original375_requests']:
        raise ValueError('original375 request history differs')
    if inputs.get('original_dynamic_parts') != coverage['original_dynamic_parts'] or any(key not in actual for key in coverage['original_dynamic_parts']):
        raise ValueError('both real dynamic providers must be registered')
    from nonproduction_scope import validate
    validate(inputs, controller)
    return {'original_requests': 375, 'canonical_components': 365, 'actual_selected_parts': 366,
            'coverage_sha256': COVERAGE_SHA, 'source_bindings_verified': True,
            'native_GN_or_images_proven_by_profile': False, 'runtime': False}
