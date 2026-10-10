"""Independent complete three-state matrix and fixed UNIQUE conformance cases."""
import copy
import itertools
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from evaluator import TableError, evaluate_table
from io_contract import compile_table_config, invoke_table
from tools.evaluate import EvaluateDMNTool, LEGACY_OUTPUT_NAMES, TableInvocationError

OUTPUT_NAMES = set(LEGACY_OUTPUT_NAMES) | {
    'selected_rule_ids', 'condition_matched_rule_ids', 'all_matches', 'unknown_rule_ids',
    'blocking_unknown_rule_ids', 'decision_status', 'model_sha256', 'decision_result',
}
VECTORS = json.loads((Path(__file__).parent / 'vectors/v050-unique-conformance.json').read_text())


def run(table, values=None, **parameters):
    return invoke_table({'table_json': json.dumps(table, ensure_ascii=False),
                         'values_json': json.dumps(values or {}, ensure_ascii=False), **parameters})


def check_invariants(result, table):
    assert set(result) == OUTPUT_NAMES
    assert set(result['result']) == {'matched', 'evaluations'}
    assert json.loads(result['result_json']) == result['result']
    assert result['matched'] == result['result']['matched']
    assert result['matched_rule_ids'] == result['selected_rule_ids']
    assert result['matched'] == [r for r in table['rules'] if r['id'] in result['selected_rule_ids']]
    assert result['all_matches'] == [r for r in table['rules'] if r['id'] in result['condition_matched_rule_ids']]
    assert result['outputs'] == [r.get('output') for r in result['matched']]
    assert result['status'] == result['decision_status']
    assert result['decision_result'] == {
        'schema_version': '0.5.0', 'unknown_policy': table.get('unknown_policy', 'compatible'),
        **{k: result[k] for k in ('decision_status', 'selected_rule_ids', 'condition_matched_rule_ids',
                                  'unknown_rule_ids', 'blocking_unknown_rule_ids', 'model_sha256')},
    }


# All 364 combinations of zero through five rules, including every permutation
# of true/false/unknown, under both explicit policies and the omitted default.
MATRIX = [(states, policy) for n in range(6) for states in itertools.product('FTU', repeat=n)
          for policy in (None, 'compatible', 'strict')]


@pytest.mark.parametrize('states,policy', MATRIX)
def test_unique_complete_truth_matrix(states, policy):
    # Independent oracle by counting fixed truths, rather than reproducing
    # evaluator selection or FIRST's prefix-based treatment of unknowns.
    true_ids = [str(i) for i, state in enumerate(states) if state == 'T']
    unknown_ids = [str(i) for i, state in enumerate(states) if state == 'U']
    if len(true_ids) >= 2:
        status, selected, blockers = 'conflict', [], []
    elif unknown_ids:
        status, selected, blockers = 'waiting_input', [], unknown_ids
    elif len(true_ids) == 1:
        status, selected, blockers = 'matched', true_ids, []
    else:
        status, selected, blockers = 'no_match', [], []
    table = {'id': 'unique-state-matrix', 'hit_policy': 'UNIQUE',
             'rules': [{'id': str(i), 'when': {'eq': [str(i), 1]}, 'output': {'chosen': i}}
                       for i in range(len(states))]}
    if policy is not None:
        table['unknown_policy'] = policy
    values = {str(i): 1 if state == 'T' else 0 for i, state in enumerate(states) if state != 'U'}
    before = copy.deepcopy((table, values))
    result = run(table, values)
    assert result['decision_status'] == status
    assert result['selected_rule_ids'] == selected
    assert result['condition_matched_rule_ids'] == true_ids
    assert result['unknown_rule_ids'] == unknown_ids
    assert result['blocking_unknown_rule_ids'] == blockers
    assert [e['condition'] for e in result['evaluations']] == [{'T': True, 'F': False, 'U': None}[s] for s in states]
    assert evaluate_table(table, values)['matched'] == result['matched']
    check_invariants(result, table)
    assert (table, values) == before


@pytest.mark.parametrize('case', VECTORS['decision_cases'], ids=lambda c: c['id'])
def test_unique_fixed_vectors(case):
    before = copy.deepcopy(case)
    result = run(case['table'], case['values'])
    for key, value in case['expected'].items():
        actual = [e['condition'] for e in result['evaluations']] if key == 'conditions' else result[key]
        assert actual == value, key
    check_invariants(result, case['table'])
    assert case == before


@pytest.mark.parametrize('case', VECTORS['error_cases'], ids=lambda c: c['id'])
def test_unique_fixed_error_vectors(case):
    with pytest.raises(TableError) as exc:
        run(case['table'], case['values'])
    assert exc.value.code == case['expected_error']['code']
    assert exc.value.path == case['expected_error']['path']


@pytest.mark.parametrize('prefix', [[True, True], [True, {'eq': ['missing', 1]}]])
def test_unique_conflict_or_waiting_never_hides_later_errors(prefix):
    table = {'id': 'no-short-circuit', 'hit_policy': 'UNIQUE',
             'rules': [{'id': str(i), 'when': condition} for i, condition in enumerate(prefix)] +
                      [{'id': 'invalid', 'when': {'gt': ['x', 1]}}]}
    stream = EvaluateDMNTool.from_credentials({})._invoke({'table_json': json.dumps(table), 'values_json': '{"x":"PRIVATE"}'})
    with pytest.raises(TableInvocationError) as exc:
        next(stream)
    assert json.loads(str(exc.value))['code'] == 'INVALID_VALUE'
    assert 'PRIVATE' not in str(exc.value)


@pytest.mark.parametrize('case', VECTORS['decision_cases'], ids=lambda c: c['id'])
def test_unique_sdk_keeps_seventeen_outputs_and_nine_field_json(case):
    messages = list(EvaluateDMNTool.from_credentials({})._invoke({
        'table_json': json.dumps(case['table']), 'values_json': json.dumps(case['values'])}))
    assert len(messages) == 18
    variables = {m.message.variable_name: m.message.variable_value for m in messages[:-1]}
    assert set(variables) == OUTPUT_NAMES
    assert all(m.type.value == 'variable' for m in messages[:-1])
    assert messages[-1].type.value == 'json'
    assert messages[-1].message.json_object == {key: variables[key] for key in LEGACY_OUTPUT_NAMES}
    assert variables['decision_status'] == case['expected']['decision_status']
    check_invariants(variables, case['table'])


def test_unique_compiler_pins_policy_and_rejects_tampering_before_evaluation():
    table = {'id': 'pin', 'hit_policy': 'UNIQUE', 'rules': [{'id': 'one', 'when': True}]}
    config = compile_table_config(json.dumps(table))
    assert invoke_table({**config, 'values_json': '{}'})['selected_rule_ids'] == ['one']
    table['hit_policy'] = 'FIRST'
    with patch('io_contract.evaluate_table', side_effect=AssertionError('must reject changed model')):
        with pytest.raises(TableError) as exc:
            run(table, expected_sha256=config['expected_sha256'])
    assert exc.value.code == 'HASH_MISMATCH'


@pytest.mark.parametrize('policy', [None, '', 'STRICT', 'skip', False, 1, {}, []])
def test_unique_does_not_ignore_invalid_unknown_policy(policy):
    with pytest.raises(TableError) as exc:
        run({'id': 'invalid-policy', 'hit_policy': 'UNIQUE', 'unknown_policy': policy, 'rules': []})
    assert exc.value.code == 'INVALID_UNKNOWN_POLICY'
