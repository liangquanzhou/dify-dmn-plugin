import hashlib
import itertools
import json
from unittest.mock import patch

import pytest

from evaluator import TableError
from io_contract import invoke_table


def run(table, values=None, **kwargs):
    return invoke_table({'table_json': json.dumps(table), 'values_json': json.dumps(values or {}), **kwargs})


def model(policy='compatible', hit='FIRST'):
    return {'id': 'fallback', 'hit_policy': hit, 'unknown_policy': policy,
            'rules': [{'id': 'conditional', 'when': {'eq': ['a', 1]}, 'output': {'route': 'a'}},
                      {'id': 'fallback', 'when': True, 'output': {'route': 'fallback'}}]}


@pytest.mark.parametrize('policy,selected,status', [('compatible', ['fallback'], 'matched'), ('strict', [], 'waiting_input')])
def test_missing_input_with_true_fallback(policy, selected, status):
    out = run(model(policy))
    assert out['selected_rule_ids'] == out['matched_rule_ids'] == selected
    assert out['status'] == out['decision_status'] == status
    assert out['condition_matched_rule_ids'] == ['fallback']
    assert out['unknown_rule_ids'] == ['conditional']
    assert out['blocking_unknown_rule_ids'] == (['conditional'] if policy == 'strict' else [])
    assert [r['id'] for r in out['all_matches']] == ['fallback']
    assert [r['id'] for r in out['result']['matched']] == selected


CASES = [(states, policy, hit) for n in range(5) for states in itertools.product('FTU', repeat=n)
         for policy in ('compatible', 'strict') for hit in ('FIRST', 'COLLECT')]


@pytest.mark.parametrize('states,policy,hit', CASES)
def test_selection_truth_matrix(states, policy, hit):
    # Independent finite-state oracle: strict FIRST looks only at the prefix up
    # to its first T; COLLECT needs every condition to be known.
    first_t = next((i for i, x in enumerate(states) if x == 'T'), len(states))
    true_ids = [str(i) for i, x in enumerate(states) if x == 'T']
    unknown_ids = [str(i) for i, x in enumerate(states) if x == 'U']
    if policy == 'strict':
        blocking = unknown_ids if hit == 'COLLECT' else [str(i) for i in range(first_t) if states[i] == 'U']
    else:
        blocking = unknown_ids if not true_ids else []
    selected = [] if policy == 'strict' and blocking else true_ids[:1] if hit == 'FIRST' else true_ids
    decision_status = 'waiting_input' if blocking else 'matched' if selected else 'no_match'
    legacy_status = 'waiting_input' if policy == 'strict' and blocking else 'matched' if selected else 'no_match'
    table = {'id': 'matrix', 'hit_policy': hit, 'unknown_policy': policy,
             'rules': [{'id': str(i), 'when': {'eq': [str(i), 1]}} for i in range(len(states))]}
    values = {str(i): 1 if x == 'T' else 0 for i, x in enumerate(states) if x != 'U'}
    out = run(table, values)
    assert out['selected_rule_ids'] == out['matched_rule_ids'] == selected
    assert out['condition_matched_rule_ids'] == true_ids
    assert out['unknown_rule_ids'] == unknown_ids
    assert out['blocking_unknown_rule_ids'] == blocking
    assert out['decision_status'] == decision_status
    assert out['status'] == legacy_status
    assert [e['condition'] for e in out['evaluations']] == [{'T': True, 'F': False, 'U': None}[x] for x in states]
    assert out['decision_result'] == {
        'schema_version': '0.3.0', 'unknown_policy': policy, 'decision_status': decision_status,
        'selected_rule_ids': selected, 'condition_matched_rule_ids': true_ids,
        'unknown_rule_ids': unknown_ids, 'blocking_unknown_rule_ids': blocking,
        'model_sha256': out['model_sha256'],
    }


@pytest.mark.parametrize('invalid', [None, '', 'STRICT', 'skip', False, 1, {}, []])
def test_unknown_policy_rejects_invalid_explicit_values(invalid):
    table = model(); table['unknown_policy'] = invalid
    with pytest.raises(TableError) as exc:
        run(table)
    assert exc.value.code == 'INVALID_UNKNOWN_POLICY'


def test_omitted_policy_is_compatible_without_injecting_model_field():
    table = model(); del table['unknown_policy']
    out = run(table)
    assert out['selected_rule_ids'] == ['fallback']
    assert out['decision_result']['unknown_policy'] == 'compatible'
    assert 'unknown_policy' not in table
    assert out['model_sha256'] != run(model())['model_sha256']


def test_compatible_unknown_without_true_keeps_legacy_status():
    table = model(); table['rules'].pop()
    out = run(table)
    assert out['status'] == 'no_match'
    assert out['decision_status'] == 'waiting_input'
    assert out['matched'] == []
    assert out['blocking_unknown_rule_ids'] == ['conditional']


def test_strict_waiting_does_not_hide_later_runtime_error():
    table = model('strict')
    table['rules'].append({'id': 'wrong', 'when': {'gt': ['wrong', 1]}})
    with pytest.raises(TableError) as exc:
        run(table, {'wrong': 'not-number'})
    assert exc.value.code == 'INVALID_VALUE'


def test_hash_lock_precedes_rule_evaluation():
    table = model('strict')
    with patch('io_contract.evaluate_table', side_effect=AssertionError('Must not execute untrusted version')):
        with pytest.raises(TableError) as exc:
            run(table, expected_sha256='0' * 64)
    assert exc.value.code == 'HASH_MISMATCH'


def test_all_output_data_and_trace_are_preserved_while_waiting():
    table = model('strict'); table['rules'][1]['载荷'] = {'ref': 'do-not-execute'}
    out = run(table)
    assert out['all_matches'] == [table['rules'][1]]
    assert out['result'] == {'matched': [], 'evaluations': out['evaluations']}
    assert out['outputs'] == []
    assert out['evaluations'][0]['read_variables'] == ['a']
    assert out['evaluations'][1]['condition'] is True
