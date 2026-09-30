"""Implementation-neutral fixtures with hand-derived decisions and fixed JCS bytes."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import rfc8785

from evaluator import TableError
from io_contract import invoke_table, parse_object, MAX_TABLE_BYTES

VECTORS = json.loads((Path(__file__).parent/'vectors/v030-conformance.json').read_text())


def inputs(case):
    return {'table_json': json.dumps(case['table'], ensure_ascii=False), 'values_json': json.dumps(case['values'], ensure_ascii=False)}


def check_expected(result, expected):
    for key, value in expected.items():
        if key == 'conditions':
            actual = [e['condition'] for e in result['evaluations']]
        elif key == 'read_variables':
            actual = [e['read_variables'] for e in result['evaluations']]
        elif key == 'unknown_policy':
            actual = result['decision_result']['unknown_policy']
        elif key == 'selected_rules':
            actual = result['matched']
        else:
            actual = result[key]
        assert actual == value, key


def invariants(result, raw):
    table = json.loads(raw)
    assert set(result['result']) == {'matched', 'evaluations'}
    assert json.loads(result['result_json']) == result['result']
    assert result['result']['matched'] == result['matched']
    assert result['matched_rule_ids'] == result['selected_rule_ids']
    assert result['all_matches'] == [r for r in table['rules'] if r['id'] in result['condition_matched_rule_ids']]
    assert result['matched'] == [r for r in table['rules'] if r['id'] in result['selected_rule_ids']]
    assert result['outputs'] == [r.get('output') for r in result['matched']]
    assert len(result['evaluations']) == len(table['rules'])
    assert result['decision_result'] == {
        'schema_version': '0.3.0', 'unknown_policy': table.get('unknown_policy', 'compatible'),
        **{k: result[k] for k in ['decision_status','selected_rule_ids','condition_matched_rule_ids','unknown_rule_ids','blocking_unknown_rule_ids','model_sha256']},
    }
    assert result['table_version'] == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.parametrize('case', VECTORS['decision_cases'], ids=lambda x:x['id'])
def test_decisions(case):
    before = copy.deepcopy(case)
    parameters = inputs(case)
    result = invoke_table(parameters)
    check_expected(result, case['expected'])
    invariants(result, parameters['table_json'])
    assert case == before


@pytest.mark.parametrize('case', VECTORS['error_cases'], ids=lambda x:x['id'])
def test_errors(case):
    with pytest.raises(TableError) as exc:
        invoke_table(inputs(case))
    for key, value in case['expected_error'].items():
        assert getattr(exc.value, key) == value


@pytest.mark.parametrize('case', VECTORS['hash_cases'], ids=lambda x:x['id'])
def test_hash_vectors(case):
    parsed = parse_object(case['table_json'], 'table_json', MAX_TABLE_BYTES)
    assert rfc8785.dumps(parsed).decode() == case['expected_canonical_json']
    result = invoke_table({'table_json': case['table_json'], 'values_json': '{}'})
    assert result['model_sha256'] == case['expected_sha256']
    assert result['table_version'] == case['expected_table_version']


@pytest.mark.parametrize('case', VECTORS['pin_cases'], ids=lambda x:x['id'])
def test_pin_vectors(case):
    result = invoke_table({k:case[k] for k in ['table_json','values_json','expected_sha256'] if k in case})
    check_expected(result, case['expected'])


@pytest.mark.parametrize('case', VECTORS['input_error_cases'], ids=lambda x:x['id'])
def test_input_error_vectors(case):
    with pytest.raises(TableError) as exc:
        invoke_table(case['parameters'])
    for key,value in case['expected_error'].items():
        assert getattr(exc.value,key) == value


def test_hash_groups_and_inequalities():
    cases = {x['id']:x for x in VECTORS['hash_cases']}
    groups = {}
    for case in cases.values():
        if 'equivalence_group' in case:
            digest = groups.setdefault(case['equivalence_group'],case['expected_sha256'])
            assert case['expected_sha256'] == digest
    for a,b in VECTORS['hash_inequality_pairs']:
        assert cases[a]['expected_sha256'] != cases[b]['expected_sha256']
