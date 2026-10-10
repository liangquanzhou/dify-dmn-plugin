"""Independent architecture-v2 query boundary vectors; no company connection."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from json_profiles import canonical_digest
from json_query import QueryDeployment, compile_query_plan, digest
from json_query_node import (QueryNodeDeployment, QueryNodeRegistration,
                             VerifiedQueryNode, execute_query_node)
from test_json_decision import fixture as decision_fixture
from test_json_query import compile_fixture, page, public_plan_fixture


def fixture(output=None, not_found_when=None):
    bundle, ref, _, context = decision_fixture()
    ref['node_id'] = 'query'
    parameters = {'subject_id': context['subject_scope_ref']}
    compiled = compile_fixture()
    if output is not None:
        plan, registry = public_plan_fixture()
        plan['outputs'] = {name: {'literal': value} for name, value in output.items()}
        compiled = compile_query_plan(plan, registry, capability_id='test.read', definition_sha256='a' * 64,
            input_schema=compiled.capability.input_schema,
            output_schema={'type': 'object', 'properties': {name: {} for name in output}, 'required': list(output), 'additionalProperties': False},
            subject_input='subject_id', source_refs={'read': ['synthetic-source']}, not_found_when=not_found_when)
    step = bundle['workflows'][0]['phases'][0]['steps'][0]
    graph = step['graph']
    graph['nodes'].insert(1, {'node_id': 'query', 'name': 'Read facts', 'category': 'EXECUTION', 'kind': 'QUERY',
        'ports': ['ok', 'blocked', 'error', 'unknown', 'cancelled'], 'capability_ref': 'test.read',
        'requires_intent': False, 'input_bindings': {'subject_id': {'from': {'source': 'context', 'path': ['subject_id']}}}})
    graph['edges'][0]['target'] = 'query'
    graph['edges'] += [dict(edge_id='query-' + port, source='query', source_port=port, target='decide' if port == 'ok' else 'stop')
                       for port in ('ok', 'blocked', 'error', 'unknown', 'cancelled')]
    bundle['capabilities']['test.read'] = {'kind': 'QUERY', 'read_only': True, 'implementation': 'QUERY_PLAN',
        'input_schema': deepcopy(compiled.capability.input_schema), 'output_schema': deepcopy(compiled.capability.output_schema),
        'query_plan_ref': 'synthetic.plan'}
    bundle['asset_locks'] = {
        'synthetic.plan': {'kind': 'QUERY_PLAN', 'path': 'query.json', 'digest_kind': 'SHA256_BYTES', 'sha256': compiled.query_plan_bytes_sha256},
        'synthetic.registry': {'kind': 'OPERATION_REGISTRY', 'path': 'operations.json', 'digest_kind': 'SHA256_BYTES', 'sha256': compiled.operation_registry_bytes_sha256}}
    compiled = replace(compiled, capability=replace(compiled.capability, definition_sha256=canonical_digest(bundle)))
    calls = []
    def read(payload, **kwargs):
        calls.append(deepcopy(payload))
        return page(subject_id=context['subject_scope_ref'])
    query = QueryDeployment({'test.read': compiled.capability}, {'read': read}, compiled.operation_registry,
        lambda _: True, environment='SYNTHETIC', now=lambda: datetime(2026, 10, 9, 12, tzinfo=timezone.utc))
    registration = QueryNodeRegistration(deepcopy(ref), compiled, 'synthetic.plan', 'synthetic.registry')
    def verify(prepared):
        return VerifiedQueryNode(deepcopy(context), {'context': deepcopy(parameters)}, ('synthetic:input',))
    deployment = QueryNodeDeployment(query, (registration,), verify)
    return bundle, ref, {'parameters': parameters, 'source_refs': ['synthetic:input']}, context, deployment, calls


def invoke(parts, deployment='fixture'):
    bundle, ref, inputs, context, configured, _ = parts
    return execute_query_node(bundle, ref, canonical_digest(bundle), inputs, context,
                              deployment=configured if deployment == 'fixture' else deployment)


def error(result):
    return result['diagnostics'][0]['code']


def repin(parts):
    bundle, _, _, _, deployment, _ = parts
    compiled = replace(deployment.registrations[0].compiled,
                       capability=replace(deployment.registrations[0].compiled.capability, definition_sha256=canonical_digest(bundle)))
    registration = replace(deployment.registrations[0], compiled=compiled)
    query = replace(deployment.query, capabilities={'test.read': compiled.capability})
    return parts[:4] + (replace(deployment, query=query, registrations=(registration,)), parts[5])


def test_fixed_query_node_success_rebinds_inputs_and_projects_one_node_result():
    parts = fixture()
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED', result
    assert result['outputs']['query']['data'] == {'answer': 'READY'}
    assert result['outputs']['query']['outcome'] == 'FOUND'
    assert result['outputs']['query']['completeness'] == 'COMPLETE'
    assert result['outputs']['query']['provenance']['mock'] is True
    assert result['outputs']['query']['provenance']['atomic_snapshot'] is False
    assert result['node_ref'] == parts[1]
    assert result['node_run_id'] == parts[3]['node_run_id']
    assert result['run_ref']['attempt_id'] == parts[3]['attempt_id']
    assert result['trace']['operations'] == ['load']
    assert len(parts[-1]) == 1


def test_fixed_query_node_without_connection_never_falls_back():
    parts = fixture()
    result = invoke(parts, deployment=None)
    assert result['execution_status'] == 'BLOCKED'
    assert error(result) == 'QUERY_CONNECTION_NOT_CONFIGURED'
    assert result['outputs'] == {'query': None} and parts[-1] == []


@pytest.mark.parametrize('expected,actual', [(True, 1), (False, 0)])
@pytest.mark.parametrize('constraint', ['const', 'enum'])
def test_operation_asset_comparison_preserves_json_boolean_number_identity(expected, actual, constraint):
    parts = fixture()
    plan, registry = public_plan_fixture()
    schema = registry['operations']['read']['output_schema']
    schema['properties']['flag'] = {constraint: [expected] if constraint == 'enum' else expected}
    schema['required'].append('flag')
    compiled = compile_fixture(plan, registry)
    parts[0]['asset_locks']['synthetic.registry']['sha256'] = compiled.operation_registry_bytes_sha256
    changed = deepcopy(compiled.operation_registry)
    changed['read']['output_schema']['properties']['flag'][constraint] = [actual] if constraint == 'enum' else actual
    assert changed == compiled.operation_registry  # Python equality erases this JSON distinction.
    calls = []

    def read(payload, **kwargs):
        calls.append(payload)
        return page(subject_id=parts[3]['subject_scope_ref'], facts={'state': 'READY', 'flag': actual})

    query = replace(parts[4].query, operation_registry=changed, transports={'read': read})
    registration = replace(parts[4].registrations[0], compiled=compiled)
    parts = repin(parts[:4] + (replace(parts[4], query=query, registrations=(registration,)), parts[5]))
    result = invoke(parts)
    assert result['execution_status'] == 'BLOCKED'
    assert error(result) == 'QUERY_ASSET_LOCK_MISMATCH'
    assert result['outputs'] == {'query': None} and calls == []


@pytest.mark.parametrize('mutation,expected', [
    (lambda p: p[0]['asset_locks']['synthetic.plan'].update(sha256='b' * 64), 'QUERY_ASSET_LOCK_MISMATCH'),
    (lambda p: p[0]['asset_locks']['synthetic.registry'].update(sha256='b' * 64), 'QUERY_ASSET_LOCK_MISMATCH'),
    (lambda p: p[0]['capabilities']['test.read']['input_schema'].update(minProperties=1), 'QUERY_ASSET_LOCK_MISMATCH'),
    (lambda p: p[1].update(node_id='decide'), 'NODE_TYPE_MISMATCH'),
    (lambda p: p[2]['parameters'].update(subject_id='other'), 'QUERY_SUBJECT_MISMATCH'),
    (lambda p: p[2].update(source_refs=['caller-invented']), 'QUERY_NOT_AUTHORIZED'),
    (lambda p: p[3].update(activation_ref=''), 'SCHEMA_INVALID'),
])
def test_node_asset_source_subject_type_activation_checks_precede_io(mutation, expected):
    parts = fixture()
    mutation(parts)
    parts = repin(parts)
    result = invoke(parts)
    assert error(result) == expected, result
    assert result['outputs'] == {'query': None} and parts[-1] == []


@pytest.mark.parametrize('verified', [None, True, {'verified': True}])
def test_node_host_claims_need_typed_independent_evidence(verified):
    parts = fixture()
    deployment = replace(parts[4], verify_node=lambda _: verified)
    assert error(invoke(parts, deployment)) == 'QUERY_NOT_AUTHORIZED'
    assert parts[-1] == []


def test_node_authenticated_binding_and_context_are_rechecked_online():
    parts = fixture()
    good = parts[4].verify_node({})
    for evidence in (replace(good, context={**good.context, 'attempt_id': 'old'}),
                     replace(good, sources={'context': {'subject_id': 'forged'}}),
                     replace(good, sources={})):
        assert error(invoke(parts, replace(parts[4], verify_node=lambda _, item=evidence: item))) == 'QUERY_NOT_AUTHORIZED'
        assert parts[-1] == []
    counts = []
    def revoke(_):
        counts.append(1)
        return good if len(counts) < 3 else None
    result = invoke(parts, replace(parts[4], verify_node=revoke))
    assert error(result) == 'QUERY_NOT_AUTHORIZED' and result['outputs'] == {'query': None}
    assert len(parts[-1]) == 1


def test_node_selected_query_intent_is_an_independent_host_gate():
    parts = fixture()
    good = parts[4].verify_node({})
    selected = {'kind': 'QUERY', 'intent_id': 'selected', 'target_node_id': 'query',
                'parameters': deepcopy(parts[2]['parameters'])}
    valid = replace(parts[4], verify_node=lambda _: replace(good, selected_intent=selected))
    assert invoke(parts, valid)['execution_status'] == 'SUCCEEDED'
    parts[-1].clear()
    for change in ({'target_node_id': 'another'}, {'parameters': {}}, {'kind': 'BUSINESS'}):
        bad = replace(parts[4], verify_node=lambda _, change=change: replace(good, selected_intent={**selected, **change}))
        assert error(invoke(parts, bad)) == 'QUERY_NOT_AUTHORIZED'
        assert parts[-1] == []


def test_node_plan_asset_bytes_are_not_interchangeable_with_canonical_content_digest():
    parts = fixture()
    registration = parts[4].registrations[0]
    altered = replace(registration.compiled, plan_bytes=registration.compiled.plan_bytes + b'\n')
    deployment = replace(parts[4], registrations=(replace(registration, compiled=altered),))
    assert error(invoke(parts, deployment)) == 'QUERY_ASSET_LOCK_MISMATCH'
    assert parts[-1] == []


def test_node_sdk_exact_fields_and_success_then_failure_clear_outputs(monkeypatch):
    from tools.execute_query import ExecuteQueryTool
    import json_query_node
    parts = fixture()
    monkeypatch.setattr(json_query_node, 'SDK_NODE_DEPLOYMENT', parts[4])
    params = dict(zip(('definition_bundle_json', 'node_ref', 'expected_definition_sha256', 'inputs_json', 'execution_context_json'),
                     (parts[0], parts[1], canonical_digest(parts[0]), parts[2], parts[3])))
    tool = ExecuteQueryTool.from_credentials({})
    messages = list(tool._invoke(params))
    assert messages[-1].message.json_object['execution_status'] == 'SUCCEEDED'
    monkeypatch.setattr(json_query_node, 'SDK_NODE_DEPLOYMENT', None)
    messages = list(tool._invoke(params))
    values = {m.message.variable_name: m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert values['execution_status'] == 'BLOCKED'
    assert values['outputs'] == {'query': None} and all(v is not None for v in values.values())
    assert messages[-1].message.json_object == values['results']
    params['request_json'] = {}
    assert list(tool._invoke(params))[-1].message.json_object['diagnostics'][0]['code'] == 'INVALID_REQUEST'


def test_required_query_intent_cannot_be_synthesized_from_request_hashes():
    parts = fixture()
    graph = parts[0]['workflows'][0]['phases'][0]['steps'][0]['graph']
    query = next(n for n in graph['nodes'] if n['node_id'] == 'query')
    query['requires_intent'] = True
    for edge in graph['edges']:
        if edge['source'] == 'begin':
            edge['target'] = 'decide'
        elif edge['source'] == 'decide' and edge['source_port'] == 'ok':
            edge['target'] = 'query'
        elif edge['source'] == 'query' and edge['source_port'] == 'ok':
            edge['target'] = 'done'
    for template in parts[0]['models']['eligibility']['result_templates'].values():
        template['actions'] = [{'kind': 'QUERY', 'intent_id': 'read', 'target_node_id': 'query'}]
    parts = repin(parts)
    assert error(invoke(parts)) == 'QUERY_NOT_AUTHORIZED'
    assert parts[-1] == []
    verified = parts[4].verify_node({})
    selected = {'kind': 'QUERY', 'intent_id': 'read', 'target_node_id': 'query', 'parameters': deepcopy(parts[2]['parameters'])}
    deployment = replace(parts[4], verify_node=lambda _: replace(verified, selected_intent=selected))
    assert invoke(parts, deployment)['execution_status'] == 'SUCCEEDED'
    assert len(parts[-1]) == 1


@pytest.mark.parametrize('output', [{}, {'tickets': []}])
def test_query_absence_requires_a_registered_result_contract(output):
    parts = fixture(output=output)
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['outputs']['query']['outcome'] == 'FOUND'
    assert result['outputs']['query']['data'] == output
    declared = fixture(output=output, not_found_when=output)
    absent = invoke(declared)
    assert absent['execution_status'] == 'SUCCEEDED'
    assert absent['outputs']['query']['outcome'] == 'NOT_FOUND'
    assert absent['outputs']['query']['data'] == output
    assert declared[4].registrations[0].compiled.capability.query_plan_sha256 != parts[4].registrations[0].compiled.capability.query_plan_sha256


def test_query_missing_success_port_is_rejected_before_io():
    parts = fixture()
    graph = parts[0]['workflows'][0]['phases'][0]['steps'][0]['graph']
    query = next(node for node in graph['nodes'] if node['node_id'] == 'query')
    query['ports'] = ['error']
    graph['edges'] = [edge for edge in graph['edges'] if edge['source'] != 'query' or edge['source_port'] == 'error']
    next(edge for edge in graph['edges'] if edge['source'] == 'query')['target'] = 'decide'
    parts = repin(parts)
    result = invoke(parts)
    assert result['execution_status'] == 'FAILED', result
    assert error(result) == 'QUERY_PORT_CONTRACT'
    assert result['outputs'] == {'query': None}
    assert parts[-1] == []


def test_optional_unknown_output_cannot_become_confirmed_not_found():
    parts = fixture(output={}, not_found_when={})
    deployment = parts[4]
    registration = deployment.registrations[0]
    capability = replace(registration.compiled.capability, optional_outputs=('missing_optional',))
    compiled = replace(registration.compiled, capability=capability)
    deployment = replace(deployment,
        query=replace(deployment.query, capabilities={'test.read': capability}),
        registrations=(replace(registration, compiled=compiled),))
    result = invoke(parts, deployment)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['outputs']['query']['data'] == {}
    assert result['outputs']['query']['completeness'] == 'PARTIAL'
    assert result['outputs']['query']['outcome'] != 'NOT_FOUND'
    assert result['trace']['unknown_outputs'] == ['missing_optional']
