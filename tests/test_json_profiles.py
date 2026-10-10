"""Independent public-contract vectors. No reference implementation is executed."""
import itertools
import json

import pytest
from json_profiles import evaluate_json_table, canonical_digest, decode_object, JsonProfileError
from io_contract import invoke_table


def table(conditions=None, policy='FIRST', output='hit'):
    return {'format': 'json-table-v1', 'id': 'independent', 'version': '1', 'hit_policy': policy,
            'rules': [{'id': 'r', 'when': conditions or [], 'output': output}]}


def condition(op, value, path=None):
    return {'path': path or ['x'], 'op': op, 'value': value}


@pytest.mark.parametrize('actual,expected,match', [
    (True, 1, False), (False, 0, False), (1, 1.0, True), ('1', 1, False), (None, None, True),
    ({'a': [True, 1, None]}, {'a': [True, 1.0, None]}, True), ({'a': 1}, {'a': True}, False),
    ([1, 2], [2, 1], False), ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}, True)])
def test_json_type_sensitive_equality(actual, expected, match):
    result = evaluate_json_table(table([condition('eq', expected)]), {'x': actual})
    assert result['status'] == 'SUCCEEDED'
    assert result['outcome'] == ('MATCHED' if match else 'NO_MATCH')


@pytest.mark.parametrize('op,operand,inputs,state', [
    ('eq', None, {}, 'WAITING_INPUT'), ('eq', None, {'x': None}, 'SUCCEEDED'),
    ('exists', False, {}, 'SUCCEEDED'), ('is_null', False, {}, 'WAITING_INPUT'),
    ('lt', 2, {'x': True}, 'WAITING_INPUT'), ('in', [1, None], {'x': None}, 'SUCCEEDED'),
    ('lt', '\U0001f601', {'x': '\U0001f600'}, 'SUCCEEDED')])
def test_missing_null_types_and_unicode(op, operand, inputs, state):
    result = evaluate_json_table(table([condition(op, operand)]), inputs)
    assert result['status'] == state
    if state == 'SUCCEEDED':
        assert result['outcome'] == 'MATCHED'


def test_paths_are_keys_not_dots_or_array_indexes():
    assert evaluate_json_table(table([condition('eq', 9, ['a.b'])]), {'a.b': 9})['outcome'] == 'MATCHED'
    assert evaluate_json_table(table([condition('eq', 9, ['a', 'b'])]), {'a.b': 9})['status'] == 'WAITING_INPUT'
    assert evaluate_json_table(table([condition('eq', 9, ['a', '0'])]), {'a': [9]})['status'] == 'WAITING_INPUT'


def test_false_dominates_unknown_and_null_output_has_match_identity():
    result = evaluate_json_table(table([condition('eq', 1), condition('eq', 0, ['y'])]), {'y': 2})
    assert result['outcome'] == 'NO_MATCH'
    result = evaluate_json_table(table(output=None), {})
    assert result['outcome'] == 'MATCHED' and result['result'] is None and result['selected_rule_ids'] == ['r']


@pytest.mark.parametrize('policy,states', itertools.product(['FIRST', 'COLLECT', 'UNIQUE'], itertools.product('TFU', repeat=3)))
def test_exhaustive_selection(policy, states):
    model = table(policy=policy)
    model['rules'] = [{'id': str(i), 'when': [condition('eq', 1, [str(i)])], 'output': i} for i in range(3)]
    inputs = {str(i): 1 if state == 'T' else 0 for i, state in enumerate(states) if state != 'U'}
    response = evaluate_json_table(model, inputs)
    true = [i for i, state in enumerate(states) if state == 'T']
    unknown = [i for i, state in enumerate(states) if state == 'U']
    assert response['matched_rule_ids'] == list(map(str, true))
    if policy == 'UNIQUE' and len(true) > 1:
        assert response['status'] == 'FAILED' and response['error']['code'] == 'UNIQUE_HIT_CONFLICT'
    elif unknown and (policy != 'FIRST' or not true or min(unknown) < min(true)):
        assert response['status'] == 'WAITING_INPUT' and response['selected_rule_ids'] == [] and response['result'] is None
    else:
        assert response['status'] == 'SUCCEEDED'
        assert response['selected_rule_ids'] == list(map(str, true[:1] if policy == 'FIRST' else true))
    assert len(response['trace']) == 3


def test_old_profile_semantics_are_not_rewritten():
    original = {'id': 'flat', 'hit_policy': 'FIRST', 'rules': [{'id': 'r', 'when': {'eq': ['x', None]}, 'output': 1}]}
    assert invoke_table({'table_json': json.dumps(original), 'values_json': '{"x":null}'})['unknown_rule_ids'] == ['r']
    assert evaluate_json_table(table([condition('eq', None)]), {'x': None})['outcome'] == 'MATCHED'


def test_digest_is_stable_and_content_pin_is_enforced():
    model = table()
    digest = canonical_digest(model)
    assert evaluate_json_table(json.dumps(model), '{}', digest)['status'] == 'SUCCEEDED'
    model['rules'][0]['output'] = 42
    assert evaluate_json_table(model, {}, digest)['error']['code'] == 'MODEL_DIGEST_MISMATCH'


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '{"x":9007199254740992}', '{"constructor":1}', '"{}"', '{"x":"\\ud800"}'])
def test_strict_profile_boundary(raw):
    assert evaluate_json_table(table(), raw)['status'] == 'FAILED'


def test_profile_owns_its_depth_budget_not_legacy_depth_32():
    assert decode_object('{"x":' + '[' * 40 + '1' + ']' * 40 + '}', 'input')
    assert evaluate_json_table(table(), '{"x":' + '[' * 65 + '1' + ']' * 65 + '}')['status'] == 'FAILED'


def test_cycles_foreign_types_and_oversize_are_rejected():
    cycle = {}; cycle['x'] = cycle
    for value in (cycle, {'x': b'bytes'}, {'x': 's' * 262144}, {1: 'numeric-key'}):
        assert evaluate_json_table(table(), value)['status'] == 'FAILED'


def test_errors_do_not_retain_previous_success():
    good = evaluate_json_table(table(), {})
    bad = evaluate_json_table(table(), '{')
    assert good['result'] == 'hit'
    assert bad['result'] is None and bad['selected_rule_ids'] == []
