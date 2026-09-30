import hashlib
import json
from unittest.mock import patch

import pytest

from evaluator import TableError
from io_contract import MAX_TABLE_BYTES, invoke_table, parse_object


def table(when=True, **kwargs):
    return {'id': 'synthetic', 'hit_policy': 'FIRST', 'rules': [{'id': 'r1', 'when': when, **kwargs}]}


def params(model=None, values=None):
    return {'table_json': json.dumps(model if model is not None else table()),
            'values_json': json.dumps(values if values is not None else {})}


def test_output_preserves_raw_data_and_exposes_bindings():
    model = table(output={'never_execute': {'ref': 'secret'}, 'nested': [1, None, False]}, **{'载荷': 'synthetic payload'})
    result = invoke_table(params(model))
    assert set(result) == {'result', 'result_json', 'matched', 'outputs', 'evaluations', 'matched_rule_ids', 'status', 'table_id', 'table_version'}
    assert result['matched'] == model['rules']
    assert result['outputs'] == [model['rules'][0]['output']]
    assert result['result'] == json.loads(result['result_json'])
    assert result['table_version'] == hashlib.sha256(params(model)['table_json'].encode()).hexdigest()
    assert result['table_id'] == 'synthetic'
    assert result['status'] == 'matched'
    assert result['matched_rule_ids'] == ['r1']


def test_missing_output_placeholder_and_payload_preserved():
    result = invoke_table(params(table(**{'载荷': {'amount': 7}})))
    assert result['outputs'] == [None]
    assert result['matched'][0]['载荷'] == {'amount': 7}
    assert 'output' not in result['matched'][0]


def test_false_unknown_and_empty_rules_are_not_errors():
    for model in [table(False), table({'eq': ['missing', 1]}), {'id': 'empty', 'hit_policy': 'COLLECT', 'rules': []}]:
        result = invoke_table(params(model))
        assert result['status'] == 'no_match'
        assert result['matched'] == result['outputs'] == result['matched_rule_ids'] == []
    assert invoke_table(params(table(False)))['evaluations'][0]['condition'] is False
    assert invoke_table(params(table({'eq': ['missing', 1]})))['evaluations'][0]['condition'] is None


@pytest.mark.parametrize('raw', ['', ' ', None, 42, {}, '[]', 'null', '1', 'true', '"text"'])
def test_requires_json_object_string(raw):
    with pytest.raises(TableError):
        parse_object(raw, 'values_json', 10000)


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"x":{"a":1,"a":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}', '{"x":9007199254740992}', '{"x":-9007199254740992}', '{"x":1e30}', '{"x":"\\ud800"}', '{"\\udfff":1}', '{"x":'])
def test_rejects_invalid_or_unsafe_json(raw):
    with pytest.raises(TableError):
        parse_object(raw, 'values_json', 10000)


def test_js_safe_number_boundaries_and_types():
    value = parse_object('{"a":9007199254740991,"b":-9007199254740991,"c":1.25,"d":false,"e":null,"f":"9007199254740999999"}', 'values_json', 1000)
    assert type(value['a']) is int and type(value['d']) is bool
    assert value['c'] == 1.25 and value['e'] is None


def test_limits_bytes_depth_nodes_rules_and_result(monkeypatch):
    with pytest.raises(TableError):
        parse_object('{"x":"中文"}', 'values_json', 10)
    with pytest.raises(TableError):
        parse_object('{"x":' + '[' * 33 + '0' + ']' * 33 + '}', 'values_json', 10000)
    with pytest.raises(TableError):
        parse_object(json.dumps({'x': [None] * 20000}), 'values_json', 200000)
    with pytest.raises(TableError):
        invoke_table(params({'id': 't', 'hit_policy': 'FIRST', 'rules': [{'id': str(i), 'when': True} for i in range(1001)]}))
    monkeypatch.setattr('io_contract.MAX_RESULT_BYTES', 1)
    with pytest.raises(TableError):
        invoke_table(params())


def test_error_text_does_not_expose_actual_values():
    sensitive = 'SYNTHETIC_VALUE_NOT_TO_BE_LOGGED'
    with pytest.raises(TableError) as exc:
        invoke_table(params(table({'is_empty': 'x'}), {'x': {'data': sensitive}}))
    assert sensitive not in str(exc.value)


def test_hash_is_exact_snapshot_not_canonical_json():
    first = params()
    second = {**first, 'table_json': first['table_json'] + '\n'}
    a, b = invoke_table(first), invoke_table(second)
    assert a['result'] == b['result']
    assert a['table_version'] != b['table_version']


def test_execution_never_opens_network_or_file():
    # Patch after imports so ordinary Python module loading is not confused with evaluation I/O.
    with patch('socket.socket', side_effect=AssertionError('Network call forbidden')), patch('builtins.open', side_effect=AssertionError('File I/O forbidden')):
        assert invoke_table(params())['status'] == 'matched'
