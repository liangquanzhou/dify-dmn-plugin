import hashlib
import json

import pytest
import rfc8785

from evaluator import TableError
from io_contract import invoke_table
from model_identity import model_identity


def test_rfc8785_known_unicode_sorting_and_number_format():
    # RFC 8785 sorts UTF-16 units, not Python's Unicode code point order.
    value = {'\ue000': 1, '\U00010000': 2, 'a': [1.0, -0.0, 1e-7, 0.000001]}
    canonical = '{"a":[1,0,1e-7,0.000001],"𐀀":2,"\ue000":1}'.encode()
    assert rfc8785.dumps(value) == canonical
    assert model_identity(value) == hashlib.sha256(canonical).hexdigest()


def test_whitespace_property_order_escape_and_number_spelling():
    a = '{"id":"t", "hit_policy":"FIRST","rules":[{"id":"r","when":true,"output":{"a":1.0,"b":"\\u4e2d"}}]}'
    b = '{"rules":[{"output":{"b":"中","a":1},"when":true,"id":"r"}],"hit_policy":"FIRST","id":"t"}'
    outputs = [invoke_table({'table_json': raw, 'values_json': '{}'}) for raw in (a, b)]
    assert outputs[0]['model_sha256'] == outputs[1]['model_sha256']
    assert outputs[0]['table_version'] != outputs[1]['table_version']


def test_array_order_policy_and_raw_output_are_part_of_hash():
    table = {'id': 't', 'hit_policy': 'FIRST', 'rules': [{'id': 'a', 'when': True}, {'id': 'b', 'when': False}]}
    digest = model_identity(table)
    for change in [dict(table, rules=list(reversed(table['rules']))), dict(table, unknown_policy='compatible'), dict(table, note='metadata')]:
        assert model_identity(change) != digest
    table['rules'][0]['output'] = {'data': 1}
    assert model_identity(table) != digest


def test_unicode_is_not_normalized():
    assert model_identity({'id': 'é'}) != model_identity({'id': 'e\u0301'})


@pytest.mark.parametrize('expected', [None, '', '   '])
def test_empty_expected_disables_version_lock(expected):
    assert model_identity({'x': 1}, expected) == model_identity({'x': 1})


def test_matching_hash_accepts_uppercase_and_surrounding_whitespace():
    digest = model_identity({'x': 1})
    assert model_identity({'x': 1}, '  '+digest.upper()+'\n') == digest


@pytest.mark.parametrize('invalid', [False, 1, {}, [], 'a'*63, 'g'*64, 'sha256:'+'a'*64])
def test_hash_format_errors(invalid):
    with pytest.raises(TableError) as exc:
        model_identity({'x': 1}, invalid)
    assert exc.value.code == 'INVALID_INPUT'
    assert exc.value.path == '$.expected_sha256'


def test_hash_mismatch_error():
    with pytest.raises(TableError) as exc:
        model_identity({'x': 1}, '0'*64)
    assert exc.value.code == 'HASH_MISMATCH'
    assert '0'*64 not in str(exc.value)


def test_excessive_lock_text_is_rejected_before_normalization():
    with pytest.raises(TableError) as exc:
        model_identity({'x': 1}, ' ' * 1000000)
    assert exc.value.code == 'INVALID_INPUT'
