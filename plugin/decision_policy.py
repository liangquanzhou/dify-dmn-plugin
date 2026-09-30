"""Additive selection policy over unchanged v0.2.0 condition evaluations."""
from typing import Any

from evaluator import TableError


def unknown_policy(table: dict[str, Any]) -> str:
    policy = table.get('unknown_policy', 'compatible')
    if policy not in ('compatible', 'strict'):
        raise TableError('INVALID_UNKNOWN_POLICY', '$.table_json.unknown_policy', 'unknown_policy must be compatible or strict')
    return policy


def apply_policy(table: dict[str, Any], legacy_result: dict[str, Any], policy: str, model_sha256: str) -> dict[str, Any]:
    evaluations = legacy_result['evaluations']
    rules = table['rules']
    true_indexes = [i for i, value in enumerate(evaluations) if value['condition'] is True]
    unknown_indexes = [i for i, value in enumerate(evaluations) if value['condition'] is None]
    all_matches = [rules[i] for i in true_indexes]
    blockers = []
    if policy == 'strict':
        if table['hit_policy'] == 'COLLECT':
            blockers = unknown_indexes
        else:
            first_true = true_indexes[0] if true_indexes else len(rules)
            blockers = [i for i in unknown_indexes if i < first_true]
    elif not true_indexes:
        blockers = unknown_indexes
    waiting = bool(blockers)
    selected = [] if policy == 'strict' and waiting else legacy_result['matched']
    decision_status = 'waiting_input' if waiting else 'matched' if selected else 'no_match'
    selected_ids = [rule['id'] for rule in selected]
    matched_ids = [rule['id'] for rule in all_matches]
    unknown_ids = [rules[i]['id'] for i in unknown_indexes]
    blocker_ids = [rules[i]['id'] for i in blockers]
    decision_result = {
        'schema_version': '0.3.0',
        'unknown_policy': policy,
        'decision_status': decision_status,
        'selected_rule_ids': selected_ids,
        'condition_matched_rule_ids': matched_ids,
        'unknown_rule_ids': unknown_ids,
        'blocking_unknown_rule_ids': blocker_ids,
        'model_sha256': model_sha256,
    }
    return {
        'result': {'matched': selected, 'evaluations': evaluations},
        'status': 'waiting_input' if policy == 'strict' and waiting else 'matched' if selected else 'no_match',
        'selected_rule_ids': selected_ids,
        'condition_matched_rule_ids': matched_ids,
        'all_matches': all_matches,
        'unknown_rule_ids': unknown_ids,
        'blocking_unknown_rule_ids': blocker_ids,
        'decision_status': decision_status,
        'model_sha256': model_sha256,
        'decision_result': decision_result,
    }
