"""Independent plan vectors built from public JSON I/O documentation."""
from copy import deepcopy
import json

import pytest

from json_plan import execute_json_plan
from json_profiles import canonical_digest


def table(output=None, when=None, policy='FIRST'):
    return {'format': 'json-table-v1', 'id': 'synthetic-table', 'version': '1',
            'hit_policy': policy, 'rules': [{'id': 'rule-1', 'when': [] if when is None else when,
                                          'output': {'route': 'ADVICE'} if output is None else output}]}


def decision(step_id='decide', **changes):
    value = {'id': step_id, 'kind': 'decision', 'depends_on': [],
             'model_id': 'gate', 'hit_policy': 'FIRST', 'inputs': {}}
    value.update(changes)
    return value


def query(step_id='ticket', **changes):
    value = {'id': step_id, 'kind': 'query', 'depends_on': [], 'capability_id': 'demo.ticket_lookup',
             'input_contract': 'demo.ticket_lookup.input.v1', 'output_contract': 'demo.ticket_lookup.output.v1',
             'parameters': {'ticket_id': {'from': ['inputs', 'ticket_id']}}}
    value.update(changes)
    return value


def make_request(model=None, steps=None, outputs=None):
    model = table() if model is None else model
    return {'plan': {'format': 'json-plan-v1', 'id': 'synthetic-locate', 'version': '0.3.0',
                     'flow': 'locate_problem', 'phases': [{'id': 'LOCATE', 'steps': [decision()] if steps is None else steps}],
                     'outputs': {'route': {'from': ['steps', 'decide', 'result', 'route']}} if outputs is None else outputs},
            'models': {'gate': {'table': model, 'sha256': canonical_digest(model)}}, 'inputs': {}}


def error(result):
    return result['error']['code']


def test_success_identity_digest_and_advisory_status():
    request = make_request()
    result = execute_json_plan(request)
    assert result['status'] == 'SUCCEEDED' and result['outcome'] == 'COMPLETED'
    assert result['outputs'] == {'route': 'ADVICE'}
    assert result['request_sha256'] == canonical_digest(request)
    assert result['plan_sha256'] == canonical_digest(request['plan'])
    assert result['provenance']['execution_authority'] == 'ADVISORY_ONLY'
    assert result['provenance']['environment'] == 'SYNTHETIC'
    assert result['steps'][0]['response']['selected_rule_ids'] == ['rule-1']


def test_query_then_decision_with_declared_binding_and_raw_response():
    model = table(when=[{'path': ['order'], 'op': 'eq', 'value': 'O-100'}])
    request = make_request(model, [query(), decision(depends_on=['ticket'], inputs={'order': {'from': ['steps', 'ticket', 'outputs', 'order_id']}})])
    request['inputs']['ticket_id'] = 'T-100'
    result = execute_json_plan(request)
    assert result['status'] == 'SUCCEEDED'
    assert result['steps'][0]['response']['outputs']['order_id'] == 'O-100'
    assert result['steps'][0]['response']['provenance']['mock'] is True


def test_same_phase_stable_topological_sort():
    request = make_request(steps=[decision('last', depends_on=['middle']), decision('middle', depends_on=['first']), decision('first')], outputs={})
    result = execute_json_plan(request)
    assert result['status'] == 'SUCCEEDED'
    assert [step['id'] for step in result['steps']] == ['first', 'middle', 'last']


@pytest.mark.parametrize('change,expected', [
    (lambda r: r['plan'].update(version='0.4.0'), 'INVALID_PLAN'),
    (lambda r: r['plan'].update(flow='business'), 'INVALID_PHASES'),
    (lambda r: r['plan']['phases'][0].update(id='P6'), 'INVALID_PHASES'),
    (lambda r: r['plan']['phases'][0].update(steps=[]), 'INVALID_PHASE'),
    (lambda r: r['plan']['phases'][0].update(steps=[query()]), 'INVALID_PHASE'),
    (lambda r: r['plan']['phases'][0]['steps'].append(decision()), 'DUPLICATE_STEP'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(depends_on=['missing']), 'INVALID_DEPENDENCY'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(depends_on=['decide']), 'DEPENDENCY_CYCLE'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(depends_on=['x', 'x']), 'INVALID_DEPENDENCY'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(model_id='absent'), 'MISSING_MODEL'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(hit_policy='COLLECT'), 'HIT_POLICY_MISMATCH'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(inputs={'x': {'from': ['steps', 'not-declared', 'result']}}), 'UNDECLARED_DEPENDENCY'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(inputs={'x': {'expression': '1+1'}}), 'INVALID_BINDING'),
    (lambda r: r['plan']['phases'][0]['steps'][0].update(inputs={'x': {'from': ['steps', 'decide', 'result']}}), 'UNDECLARED_DEPENDENCY'),
    (lambda r: r['models']['gate'].update(sha256='0'*64), 'MODEL_HASH_MISMATCH'),
])
def test_plan_validation_precedes_any_execution(change, expected, monkeypatch):
    request = make_request()
    change(request)
    def unexpected(*args, **kwargs):
        raise AssertionError('Validation must occur before execution')
    monkeypatch.setattr('json_plan.evaluate_json_table', unexpected)
    result = execute_json_plan(request)
    assert result['status'] == 'FAILED' and error(result) == expected
    assert result['steps'] == [] and result['outputs'] is None


def test_all_models_checked_even_when_unreferenced_or_terminated():
    request = make_request()
    request['models']['unused'] = {'table': table(), 'sha256': '0' * 64}
    assert error(execute_json_plan(request)) == 'MODEL_HASH_MISMATCH'


def test_request_pin_and_object_string_inputs():
    request = make_request()
    assert execute_json_plan(json.dumps(request), canonical_digest(request))['status'] == 'SUCCEEDED'
    assert error(execute_json_plan(request, '0' * 64)) == 'REQUEST_HASH_MISMATCH'
    assert error(execute_json_plan('"{}"')) == 'INVALID_INPUT'


def test_missing_input_omitted_but_explicit_null_preserved():
    model = table(when=[{'path': ['x'], 'op': 'exists', 'value': False}])
    request = make_request(model, [decision(inputs={'x': {'from': ['inputs', 'x']}})], outputs={})
    assert execute_json_plan(request)['steps'][0]['response']['outcome'] == 'MATCHED'
    request['inputs']['x'] = None
    response = execute_json_plan(request)['steps'][0]['response']
    assert response['outcome'] == 'NO_MATCH' and response['status'] == 'SUCCEEDED'


def test_unknown_blocks_remaining_steps_and_clears_final_outputs():
    model = table(when=[{'path': ['x'], 'op': 'eq', 'value': True}])
    request = make_request(model, [decision('first'), decision('second', depends_on=['first'])], outputs={})
    result = execute_json_plan(request)
    assert result['status'] == 'WAITING_INPUT' and result['outputs'] is None
    assert [step['status'] for step in result['steps']] == ['WAITING_INPUT', 'BLOCKED']
    assert result['steps'][1]['response'] is None


@pytest.mark.parametrize('identifier,status', [('', 'WAITING_INPUT'), ('T-UNKNOWN', 'WAITING_INPUT'), ('T-TIMEOUT', 'FAILED'), ('T-ERROR', 'FAILED')])
def test_query_non_success_blocks_later_decision(identifier, status):
    request = make_request(steps=[query(), decision(depends_on=['ticket'])])
    request['inputs']['ticket_id'] = identifier
    result = execute_json_plan(request)
    assert result['status'] == status
    assert result['steps'][1]['status'] == 'BLOCKED'


def test_technical_decision_failure_cannot_be_terminated_to_success():
    model = table(policy='UNIQUE')
    model['rules'].append({'id': 'rule-2', 'when': [], 'output': {'route': 'ADVICE'}})
    request = make_request(model, [decision(hit_policy='UNIQUE', terminate_when={'value': {'literal': True}, 'equals': True, 'outputs': {}})])
    result = execute_json_plan(request)
    assert result['status'] == 'FAILED' and result['terminated_by'] is None
    assert result['outputs'] is None


def test_termination_skips_remaining_and_uses_exclusive_outputs():
    gate = decision(terminate_when={'value': {'from': ['steps', 'decide', 'result', 'route']}, 'equals': 'ADVICE',
                                    'outputs': {'message': {'literal': 'SYNTHETIC human review'}}})
    request = make_request(steps=[gate, decision('later', depends_on=['decide'])])
    request['plan']['outputs'] = {'missing': {'from': ['inputs', 'absent']}}
    result = execute_json_plan(request)
    assert result['status'] == 'SUCCEEDED' and result['outcome'] == 'TERMINATED'
    assert result['outputs'] == {'message': 'SYNTHETIC human review'}
    assert result['terminated_by'] == 'decide' and result['steps'][1]['status'] == 'SKIPPED'


@pytest.mark.parametrize('equal,terminates', [(1, True), (1.0, True), (True, False), ('1', False)])
def test_termination_equality_is_json_type_sensitive(equal, terminates):
    request = make_request(steps=[decision(terminate_when={'value': {'literal': 1}, 'equals': equal, 'outputs': {}})], outputs={})
    assert (execute_json_plan(request)['outcome'] == 'TERMINATED') is terminates


@pytest.mark.parametrize('what', ['value', 'outputs'])
def test_missing_termination_projection_waits_and_blocks(what):
    termination = {'value': {'literal': True}, 'equals': True, 'outputs': {}}
    termination[what] = {'from': ['inputs', 'absent']} if what == 'value' else {'x': {'from': ['inputs', 'absent']}}
    request = make_request(steps=[decision(terminate_when=termination), decision('later')], outputs={})
    result = execute_json_plan(request)
    assert result['status'] == 'WAITING_INPUT' and result['outputs'] is None
    assert result['steps'][1]['status'] == 'BLOCKED'


def test_missing_final_output_is_waiting_not_null():
    request = make_request(outputs={'x': {'from': ['inputs', 'absent']}})
    assert execute_json_plan(request)['status'] == 'WAITING_INPUT'
    request['inputs']['absent'] = None
    assert execute_json_plan(request)['outputs'] == {'x': None}


def test_array_index_length_and_transitive_dependency_binding():
    request = make_request(table(output=[{'code': 'A'}, {'code': 'B'}]),
                           [decision('first'), decision('middle', depends_on=['first']),
                            decision('last', depends_on=['middle'], inputs={'count': {'from': ['steps', 'first', 'result', 'length']}})],
                           {'code': {'from': ['steps', 'first', 'result', '1', 'code']},
                            'count': {'from': ['steps', 'first', 'result', 'length']}})
    result = execute_json_plan(request)
    assert result['status'] == 'SUCCEEDED' and result['outputs'] == {'code': 'B', 'count': 2}


def test_all_five_phases_and_empty_skip():
    request = make_request(outputs={})
    request['plan']['flow'] = 'solve_problem'
    request['plan']['phases'] = [{'id': f'P{i}', 'steps': [decision(f's{i}', depends_on=[] if i == 1 else [f's{i-1}'])]} for i in range(1, 5)]
    request['plan']['phases'].append({'id': 'P5', 'steps': [], 'skip_reason': 'SYNTHETIC no additional advice'})
    result = execute_json_plan(request)
    assert result['status'] == 'SUCCEEDED'
    assert [phase['status'] for phase in result['phases']] == ['SUCCEEDED'] * 4 + ['SKIPPED']
    request['plan']['phases'][0]['steps'][0]['depends_on'] = ['s4']
    assert error(execute_json_plan(request)) == 'INVALID_DEPENDENCY'


def test_step_limit_and_output_limit_clear_large_trace(monkeypatch):
    request = make_request(steps=[decision(str(i)) for i in range(65)], outputs={})
    assert error(execute_json_plan(request)) == 'INVALID_PHASE'
    request = make_request()
    monkeypatch.setattr('json_plan.MAX_PLAN_RESPONSE_BYTES', 200)
    result = execute_json_plan(request)
    assert result['status'] == 'FAILED' and result['outputs'] is None
    assert result['steps'] == [] and result['trace_truncated'] is True


def test_mutating_an_invocation_result_does_not_change_next_run():
    request = make_request()
    result = execute_json_plan(request)
    result['steps'][0]['response']['result']['route'] = 'MUTATED'
    assert execute_json_plan(request)['outputs'] == {'route': 'ADVICE'}


def test_real_sdk_plan_wrapper():
    from tools.execute_json_plan import ExecuteJsonPlanTool
    request = make_request()
    messages = list(ExecuteJsonPlanTool.from_credentials({})._invoke({'request_json': json.dumps(request)}))
    assert len(messages) == 4
    assert messages[-1].message.json_object == execute_json_plan(request)


@pytest.mark.parametrize('mode,expected', [('success', 'SUCCEEDED'), ('unknown', 'WAITING_INPUT'),
    ('invalid', 'FAILED'), ('no_match', 'SUCCEEDED'), ('termination', 'SUCCEEDED')])
def test_plan_sdk_variables_never_emit_top_level_null(mode, expected):
    from tools.execute_json_plan import ExecuteJsonPlanTool
    request = make_request()
    if mode == 'unknown':
        request = make_request(table(when=[{'path': ['absent'], 'op': 'eq', 'value': 1}]))
    elif mode == 'invalid':
        request['models']['gate']['sha256'] = '0' * 64
    elif mode == 'no_match':
        request = make_request(table(when=[{'path': ['absent'], 'op': 'exists', 'value': True}]),
                               outputs={'result': {'from': ['steps', 'decide', 'result']}})
    elif mode == 'termination':
        request = make_request(steps=[decision(terminate_when={'value': {'literal': True}, 'equals': True, 'outputs': {}})])
    messages = list(ExecuteJsonPlanTool.from_credentials({})._invoke({'request_json': request}))
    variables = {m.message.variable_name: m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert all(value is not None for value in variables.values())
    assert variables['status'] == expected
    if expected != 'SUCCEEDED':
        assert variables['outputs'] == {} and variables['results']['outputs'] is None
    assert messages[-1].message.json_object == variables['results']


@pytest.mark.parametrize('replacement', ['encoded_valid', 'encoded_invalid', 'array', 'null'])
def test_nested_plan_table_requires_object_without_tool_crash(replacement, monkeypatch):
    from tools.execute_json_plan import ExecuteJsonPlanTool
    request = make_request()
    original = request['models']['gate']['table']
    request['models']['gate']['table'] = {
        'encoded_valid': json.dumps(original), 'encoded_invalid': 'not-json',
        'array': [], 'null': None}[replacement]
    def unexpected(*args, **kwargs):
        raise AssertionError('Invalid model must fail before execution')
    monkeypatch.setattr('json_plan.evaluate_json_table', unexpected)
    result = execute_json_plan(request)
    assert result['status'] == 'FAILED' and error(result) == 'INVALID_MODEL'
    assert result['steps'] == [] and result['outputs'] is None
    messages = list(ExecuteJsonPlanTool.from_credentials({})._invoke({'request_json': request}))
    assert messages[-1].message.json_object == result
