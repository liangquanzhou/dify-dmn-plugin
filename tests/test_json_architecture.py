"""Original static-conformance vectors, independent of the reference repository.

These build synthetic definitions; they never run a workflow or external IO.
"""
from copy import deepcopy

import pytest

from json_decision import validate_definition
from json_profiles import JsonProfileError
from test_json_decision import fixture, routed_fixture, invoke, code


def step(parts):
    return parts[0]['workflows'][0]['phases'][0]['steps'][0]


def node(parts, name):
    return next(n for n in step(parts)['graph']['nodes'] if n['node_id'] == name)


def edge(parts, source, port):
    return next(e for e in step(parts)['graph']['edges'] if e['source'] == source and e['source_port'] == port)


def add_edge(graph, source, port, target, branch=None):
    value = dict(edge_id=f'{source}:{port}', source=source, source_port=port, target=target)
    if branch is not None:
        value['branch_id'] = branch
    graph['edges'].append(value)


def gateway(name, mode, ports, pair=None, selector=None):
    value = dict(node_id=name, name=name, category='GATEWAY', kind='PARALLEL' if pair else 'EXCLUSIVE', mode=mode, ports=ports)
    if pair:
        value['pair_ref'] = pair
    if pair and mode == 'JOIN':
        value.update(join_policy='ALL_SUCCESS', failure_policy='CANCEL_REMAINING')
    if selector:
        value['selector'] = selector
    return value


def query(name, requires_intent=False):
    return dict(node_id=name, name=name, category='EXECUTION', kind='QUERY', ports=['ok', 'error'],
                capability_ref='read', requires_intent=requires_intent, input_bindings={})


def parallel_fixture(nested=False):
    parts = fixture()
    bundle, graph = parts[0], step(parts)['graph']
    bundle['deployment']['enabled_node_kinds'].append('PARALLEL')
    bundle['capabilities']['read'] = dict(kind='QUERY', read_only=True, implementation='HOST', input_schema={}, output_schema={})
    graph['nodes'] += [gateway('fork', 'SPLIT', ['left', 'right'], 'join'), gateway('join', 'JOIN', ['ok', 'error'], 'fork'), query('left'), query('right')]
    edge(parts, 'begin', 'ok')['target'] = 'fork'
    for name in ('left', 'right'):
        add_edge(graph, 'fork', name, name, 'branch-' + name)
        add_edge(graph, name, 'ok', 'join')
        add_edge(graph, name, 'error', 'join')
    add_edge(graph, 'join', 'ok', 'decide'); add_edge(graph, 'join', 'error', 'stop')
    if nested:
        graph['nodes'] += [gateway('inner', 'SPLIT', ['a', 'b'], 'inner-join'), gateway('inner-join', 'JOIN', ['ok', 'error'], 'inner'), query('other')]
        edge(parts, 'fork', 'left')['target'] = 'inner'
        edge(parts, 'left', 'ok')['target'] = 'inner-join'; edge(parts, 'left', 'error')['target'] = 'inner-join'
        add_edge(graph, 'inner', 'a', 'left', 'inside-a'); add_edge(graph, 'inner', 'b', 'other', 'inside-b')
        add_edge(graph, 'other', 'ok', 'inner-join'); add_edge(graph, 'other', 'error', 'inner-join')
        add_edge(graph, 'inner-join', 'ok', 'join'); add_edge(graph, 'inner-join', 'error', 'join')
    return parts


def wait_fixture():
    parts = routed_fixture(); graph = step(parts)['graph']
    parts[0]['deployment']['enabled_node_kinds'].append('WAIT')
    graph['nodes'].append(dict(node_id='answer', name='Answer', category='EVENT', kind='WAIT', ports=['received', 'timeout', 'cancelled', 'error'],
                              event_type='test.answer.v1', correlation_fields=['workflow_run_id', 'step_run_id', 'attempt_id', 'intent_id'],
                              timeout_ms=10000, pre_register_before='ask', event_bindings={'eligible': {'from': {'source': 'event', 'path': ['eligible']}, 'source_format': 'VALUE'}},
                              event_schema={'type': 'object', 'properties': {'eligible': {'type': 'boolean'}}, 'required': ['eligible'], 'additionalProperties': False}))
    edge(parts, 'ask', 'ok')['target'] = 'answer'
    add_edge(graph, 'answer', 'received', 'done')
    for port in ('timeout', 'cancelled', 'error'):
        add_edge(graph, 'answer', port, 'stop')
    return parts


def assert_rejected(parts, expected):
    with pytest.raises(JsonProfileError) as exc:
        validate_definition(parts[0])
    assert exc.value.code == expected
    result = invoke(parts)
    assert code(result) == expected
    assert result['outputs']['decision'] is None


@pytest.mark.parametrize('nested', [False, True])
def test_paired_parallel_accepts_without_running_other_nodes(nested):
    parts = parallel_fixture(nested)
    assert validate_definition(parts[0]) is parts[0]
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED', result
    assert result['trace']['trust'] == 'CONTENT_ONLY_NOT_AUTHORIZATION'


@pytest.mark.parametrize('nested', [False, True])
def test_join_success_establishes_definite_sources_from_every_branch(nested):
    parts = parallel_fixture(nested)
    source = 'other' if nested else 'left'
    node(parts, 'decide')['input_bindings']['eligible']['from'] = {'source': 'node', 'node_id': source, 'path': ['query', 'eligible']}
    parts[0]['models']['eligibility']['result_templates']['accepted']['data'] = {'proof': {'from': {'source': 'node', 'node_id': source, 'path': ['query', 'proof']}}}
    validate_definition(parts[0])
    # Content-only evaluation cannot conjure the declared trusted source.
    assert code(invoke(parts)) == 'INPUT_BINDING_UNAVAILABLE'


@pytest.mark.parametrize('mutation, expected', [
    (lambda p: node(p, 'fork').update(pair_ref='missing'), 'PARALLEL_PAIR_INVALID'),
    (lambda p: node(p, 'join').update(pair_ref='left'), 'PARALLEL_PAIR_INVALID'),
    (lambda p: node(p, 'join').update(join_policy='ALL_SETTLED'), 'GRAPH_PROFILE_UNSUPPORTED'),
    (lambda p: node(p, 'join').update(failure_policy='IGNORE'), 'GRAPH_PROFILE_UNSUPPORTED'),
    (lambda p: edge(p, 'fork', 'left').pop('branch_id'), 'FORK_BRANCH_MISMATCH'),
    (lambda p: edge(p, 'fork', 'right').update(branch_id='branch-left'), 'FORK_BRANCH_MISMATCH'),
    (lambda p: edge(p, 'left', 'ok').update(branch_id='branch-right'), 'FORK_BRANCH_MISMATCH'),
    (lambda p: edge(p, 'left', 'error').update(target='stop'), 'PARALLEL_ESCAPE'),
    (lambda p: edge(p, 'left', 'ok').update(target='right'), 'PARALLEL_CROSS_BRANCH'),
    (lambda p: edge(p, 'join', 'error').update(target='decide'), 'PARALLEL_FAILURE_PATH'),
    (lambda p: node(p, 'fork').update(kind='INCLUSIVE'), 'GRAPH_PROFILE_UNSUPPORTED'),
])
def test_parallel_pair_branch_convergence_and_failure_rejections(mutation, expected):
    parts = parallel_fixture(); mutation(parts); assert_rejected(parts, expected)


def test_parallel_does_not_establish_sources_on_its_failure_continuation():
    parts = parallel_fixture()
    node(parts, 'stop')['input_bindings'] = {'unsafe': {'from': {'source': 'node', 'node_id': 'left', 'path': []}}}
    assert_rejected(parts, 'DATA_SOURCE_NOT_DEFINITE')


def test_nested_failure_accepts_exclusive_plumbing_but_not_new_work():
    parts = parallel_fixture(True); graph = step(parts)['graph']
    graph['nodes'].append(gateway('error-merge', 'MERGE', ['ok']))
    edge(parts, 'inner-join', 'error')['target'] = 'error-merge'
    add_edge(graph, 'error-merge', 'ok', 'join')
    validate_definition(parts[0])
    graph['nodes'].append(query('fallback'))
    edge(parts, 'error-merge', 'ok')['target'] = 'fallback'
    add_edge(graph, 'fallback', 'ok', 'join'); add_edge(graph, 'fallback', 'error', 'join')
    assert_rejected(parts, 'PARALLEL_FAILURE_PATH')


def test_crossed_pairs_are_not_nested_regions():
    parts = parallel_fixture(True)
    node(parts, 'fork')['pair_ref'] = 'inner-join'; node(parts, 'inner-join')['pair_ref'] = 'fork'
    node(parts, 'inner')['pair_ref'] = 'join'; node(parts, 'join')['pair_ref'] = 'inner'
    assert_rejected(parts, 'FORK_BRANCH_MISMATCH')


def test_exclusive_predecessor_is_not_a_definite_data_source():
    parts = fixture(); graph = step(parts)['graph']
    parts[0]['capabilities']['read'] = dict(kind='QUERY', read_only=True, implementation='HOST', input_schema={}, output_schema={})
    graph['nodes'] += [query('probe'), gateway('choose', 'SPLIT', ['ok', 'error'], selector={'source': 'NODE_PORT', 'node_id': 'probe'}), query('optional'), gateway('merge', 'MERGE', ['ok'])]
    edge(parts, 'begin', 'ok')['target'] = 'probe'
    add_edge(graph, 'probe', 'ok', 'choose'); add_edge(graph, 'probe', 'error', 'choose')
    add_edge(graph, 'choose', 'ok', 'optional'); add_edge(graph, 'choose', 'error', 'merge')
    add_edge(graph, 'optional', 'ok', 'merge'); add_edge(graph, 'optional', 'error', 'merge')
    add_edge(graph, 'merge', 'ok', 'decide')
    node(parts, 'decide')['input_bindings']['eligible']['from'] = {'source': 'node', 'node_id': 'optional', 'path': []}
    assert_rejected(parts, 'DATA_SOURCE_NOT_DEFINITE')


def test_action_cannot_depend_on_a_future_action_output_at_selection_time():
    parts = routed_fixture()
    node(parts, 'ask')['input_bindings']['future'] = {'from': {'source': 'node', 'node_id': 'ask', 'path': []}}
    assert_rejected(parts, 'DATA_SOURCE_NOT_DEFINITE')


def test_wait_declaration_acceptance_does_not_save_or_consume_runtime_state():
    parts = wait_fixture()
    parts[2]['runtime_snapshot'] = {'claimed_event': {'received': True}, 'claimed_authorized': True}
    before = deepcopy(parts)
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED', result
    assert result['trace']['trust'] == 'CONTENT_ONLY_NOT_AUTHORIZATION'
    assert parts[2]['runtime_snapshot'] == before[2]['runtime_snapshot']


@pytest.mark.parametrize('mutation,expected', [
    (lambda p: node(p, 'answer').pop('event_schema'), 'SCHEMA_INVALID'),
    (lambda p: node(p, 'answer').update(timeout_ms=True), 'WAIT_TIMEOUT_INVALID'),
    (lambda p: node(p, 'answer').update(timeout_ms=0), 'WAIT_TIMEOUT_INVALID'),
    (lambda p: node(p, 'answer')['correlation_fields'].remove('attempt_id'), 'WAIT_CORRELATION_INVALID'),
    (lambda p: node(p, 'answer').update(pre_register_before='decide'), 'WAIT_REGISTRATION_INVALID'),
    (lambda p: node(p, 'answer').update(event_schema={'type': 'bogus'}), 'SCHEMA_INVALID'),
    (lambda p: node(p, 'answer').update(event_schema={'$ref': 'https://example.invalid/schema'}), 'REMOTE_SCHEMA_FORBIDDEN'),
    (lambda p: node(p, 'answer')['event_bindings']['eligible']['from'].update(source='api', node_id='secret'), 'INVALID_BINDING'),
    (lambda p: node(p, 'answer')['ports'].remove('cancelled'), 'WAIT_PORT_CONTRACT'),
])
def test_wait_schema_and_registration_fail_closed(mutation,expected):
    parts = wait_fixture(); mutation(parts); assert_rejected(parts, expected)


def test_wait_supports_explicit_bounded_reentry_and_exhaustion():
    parts = wait_fixture()
    step(parts)['max_attempts'] = 3
    step(parts)['exits']['business'] = {'class': 'REENTRY', 'destination': {'kind': 'REENTER_STEP'}}
    validate_definition(parts[0])
    step(parts)['exits']['technical']['destination'] = {'kind': 'REENTER_STEP'}
    assert_rejected(parts, 'INVALID_REENTRY_EXIT')


def test_cross_step_and_phase_exits_are_resolved_after_indexing():
    parts = fixture(); workflow = parts[0]['workflows'][0]
    following = deepcopy(step(parts)); following['step_id'] = 'followup'
    workflow['phases'].append({'phase_id': 'P2', 'entry_step': 'followup', 'steps': [following]})
    step(parts)['exits']['business']['destination'] = {'kind': 'PHASE', 'phase_id': 'P2'}
    validate_definition(parts[0])
    step(parts)['exits']['business']['destination'] = {'kind': 'STEP', 'phase_id': 'P2', 'step_id': 'followup'}
    validate_definition(parts[0])
    following['exits']['business']['destination'] = {'kind': 'STEP', 'phase_id': 'P1', 'step_id': 'eligibility'}
    assert_rejected(parts, 'CROSS_STEP_CYCLE')


@pytest.mark.parametrize('destination', [
    {'kind': 'STEP', 'phase_id': 'P1', 'step_id': 'absent'},
    {'kind': 'PHASE', 'phase_id': 'absent'},
])
def test_dangling_cross_step_destinations_fail(destination):
    parts = fixture(); step(parts)['exits']['business']['destination'] = destination
    assert_rejected(parts, 'UNKNOWN_EXIT_TARGET')


def test_technical_node_selector_follows_actual_decision_success():
    parts = fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('technical-route', 'SPLIT', ['ok', 'error'], selector={'source': 'NODE_PORT', 'node_id': 'decide'}))
    edge(parts, 'decide', 'ok')['target'] = 'technical-route'
    add_edge(graph, 'technical-route', 'ok', 'done'); add_edge(graph, 'technical-route', 'error', 'stop')
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'


def test_parallel_selected_intents_require_each_branch_without_dispatch():
    parts = routed_fixture(); graph = step(parts)['graph']; bundle = parts[0]
    bundle['deployment']['enabled_node_kinds'].append('PARALLEL')
    second = deepcopy(node(parts, 'ask')); second.update(node_id='notify', name='Notify')
    graph['nodes'] += [second, gateway('fork', 'SPLIT', ['a', 'b'], 'join'), gateway('join', 'JOIN', ['ok', 'error'], 'fork')]
    edge(parts, 'route', 'ask')['target'] = 'fork'; edge(parts, 'ask', 'ok')['target'] = 'join'
    add_edge(graph, 'fork', 'a', 'ask', 'ask-branch'); add_edge(graph, 'fork', 'b', 'notify', 'notify-branch')
    add_edge(graph, 'notify', 'ok', 'join'); add_edge(graph, 'join', 'ok', 'done'); add_edge(graph, 'join', 'error', 'stop')
    assert code(invoke(parts)) == 'PATH_ACTION_NOT_SELECTED'
    bundle['models']['eligibility']['result_templates']['accepted']['actions'].append(dict(kind='INTERACTION', intent_id='notify', target_node_id='notify'))
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED', result
    assert {a.get('target_node_id') for a in result['outputs']['decision']['actions']} == {None, 'ask', 'notify'}


def test_no_unregistered_parameter_reference_hidden_in_template():
    parts = fixture()
    parts[0]['models']['eligibility']['result_templates']['empty']['data'] = {'bad': {'from': {'source': 'parameters', 'path': ['undeclared', 'value']}}}
    assert_rejected(parts, 'UNREGISTERED_REFERENCE')


@pytest.mark.parametrize('mutation', [
    lambda p: node(p, 'begin').update(event_type='silently-ignored'),
    lambda p: edge(p, 'begin', 'ok').update(branch_id='not-in-a-fork'),
    lambda p: node(p, 'decide')['input_bindings']['eligible']['from'].update(node_id='ignored'),
    lambda p: step(p)['exits']['business']['destination'].update(step_id='unused'),
    lambda p: p[0]['models']['eligibility'].update(empty_template_ref=[]),
])
def test_irrelevant_or_malformed_declarations_do_not_succeed(mutation):
    parts = fixture(); mutation(parts)
    result = invoke(parts)
    assert result['execution_status'] == 'FAILED' and result['outputs']['decision'] is None


def test_wait_inside_a_parallel_branch_converges_every_outcome():
    parts = wait_fixture(); graph = step(parts)['graph']; bundle = parts[0]
    bundle['deployment']['enabled_node_kinds'].append('PARALLEL')
    second = deepcopy(node(parts, 'ask')); second.update(node_id='notify', name='Notify')
    graph['nodes'] += [second, gateway('fork', 'SPLIT', ['a', 'b'], 'join'), gateway('join', 'JOIN', ['ok', 'error'], 'fork')]
    edge(parts, 'route', 'ask')['target'] = 'fork'
    for port in ('received', 'timeout', 'cancelled', 'error'):
        edge(parts, 'answer', port)['target'] = 'join'
    add_edge(graph, 'fork', 'a', 'ask', 'asked'); add_edge(graph, 'fork', 'b', 'notify', 'notified')
    add_edge(graph, 'notify', 'ok', 'join'); add_edge(graph, 'join', 'ok', 'done'); add_edge(graph, 'join', 'error', 'stop')
    bundle['models']['eligibility']['result_templates']['accepted']['actions'].append(dict(kind='INTERACTION', intent_id='notify', target_node_id='notify'))
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    node(parts, 'answer')['pre_register_before'] = 'notify'
    assert_rejected(parts, 'WAIT_REGISTRATION_INVALID')


def test_a_branch_failure_cannot_start_fallback_execution():
    parts = parallel_fixture(); graph = step(parts)['graph']
    graph['nodes'].append(query('fallback'))
    edge(parts, 'left', 'error')['target'] = 'fallback'
    add_edge(graph, 'fallback', 'ok', 'join'); add_edge(graph, 'fallback', 'error', 'join')
    assert_rejected(parts, 'PARALLEL_FAILURE_PATH')


def test_unresolved_branch_does_not_satisfy_all_success():
    parts = parallel_fixture()
    node(parts, 'left')['ports'] = ['unknown', 'error']
    edge(parts, 'left', 'ok')['source_port'] = 'unknown'
    assert_rejected(parts, 'PARALLEL_SUCCESS_UNREACHABLE')


def test_an_intent_on_only_a_failed_action_path_is_not_selected_work():
    parts = routed_fixture(); graph = step(parts)['graph']
    other = deepcopy(node(parts, 'ask')); other.update(node_id='repair', name='Repair')
    graph['nodes'].append(other)
    node(parts, 'ask')['ports'].append('error')
    add_edge(graph, 'ask', 'error', 'repair'); add_edge(graph, 'repair', 'ok', 'stop')
    # A possible failure path cannot demand new work in the success decision.
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    parts[0]['models']['eligibility']['result_templates']['accepted']['actions'].append(dict(kind='INTERACTION', intent_id='repair', target_node_id='repair'))
    assert code(invoke(parts)) == 'INTENT_PATH_MISMATCH'


def test_valid_offline_event_schema_local_reference():
    parts = wait_fixture()
    node(parts, 'answer')['event_schema'] = {'$defs': {'answer': {'type': 'boolean'}}, 'type': 'object', 'properties': {'eligible': {'$ref': '#/$defs/answer'}}}
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'


def test_business_actions_still_emit_only_intents_with_explicit_enablement():
    parts = routed_fixture()
    parts[0]['deployment']['business_enabled'] = True
    node(parts, 'ask')['action_kind'] = 'BUSINESS'
    parts[0]['capabilities']['human']['kind'] = 'BUSINESS'
    parts[0]['models']['eligibility']['result_templates']['accepted']['actions'][1]['kind'] = 'BUSINESS'
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['outputs']['decision']['actions'][1]['kind'] == 'BUSINESS'
    parts[0]['deployment']['business_enabled'] = False
    assert_rejected(parts, 'PROFILE_NOT_ENABLED')


def test_a_shared_technical_selector_routes_success_and_failures_separately():
    parts = fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('technical-route', 'SPLIT', ['ok', 'error', 'blocked'], selector={'source': 'NODE_PORT', 'node_id': 'decide'}))
    for port in ('ok', 'error', 'blocked'):
        edge(parts, 'decide', port)['target'] = 'technical-route'
        add_edge(graph, 'technical-route', port, 'done' if port == 'ok' else 'stop')
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    edge(parts, 'technical-route', 'error')['target'] = 'done'
    assert_rejected(parts, 'FAILED_DECISION_BUSINESS_EXIT')


def test_a_sibling_branch_is_not_an_intent_parameter_source():
    parts = parallel_fixture(); graph = step(parts)['graph']
    # The right query runs concurrently with left, never after it.
    node(parts, 'right')['input_bindings']['borrow'] = {'from': {'source': 'node', 'node_id': 'left', 'path': []}}
    assert_rejected(parts, 'DATA_SOURCE_NOT_DEFINITE')


def test_nonreciprocal_empty_or_dead_parallel_branches_fail():
    parts = parallel_fixture(); graph = step(parts)['graph']
    # One branch reaches JOIN twice through two ports: those are alternatives,
    # not two independently identified obligations.
    edge(parts, 'fork', 'right')['target'] = 'left'
    graph['nodes'] = [n for n in graph['nodes'] if n['node_id'] != 'right']
    graph['edges'] = [e for e in graph['edges'] if e['source'] != 'right']
    assert_rejected(parts, 'PARALLEL_CROSS_BRANCH')


def test_end_only_branch_can_finish_at_the_paired_join_without_fake_work():
    parts = parallel_fixture(); graph = step(parts)['graph']
    graph['nodes'] = [n for n in graph['nodes'] if n['node_id'] != 'left']
    graph['edges'] = [e for e in graph['edges'] if e['source'] != 'left']
    edge(parts, 'fork', 'left')['target'] = 'join'
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'


def test_technical_selector_failure_does_not_erase_join_success_source_proof():
    parts = parallel_fixture(); graph = step(parts)['graph']
    graph['nodes'] += [gateway('status', 'SPLIT', ['ok', 'error'], selector={'source': 'NODE_PORT', 'node_id': 'left'}), query('detail')]
    for port in ('ok', 'error'):
        edge(parts, 'left', port)['target'] = 'status'
    add_edge(graph, 'status', 'ok', 'detail'); add_edge(graph, 'status', 'error', 'join')
    add_edge(graph, 'detail', 'ok', 'join'); add_edge(graph, 'detail', 'error', 'join')
    node(parts, 'decide')['input_bindings']['eligible']['from'] = {'source': 'node', 'node_id': 'detail', 'path': []}
    validate_definition(parts[0])


def test_technical_selector_cannot_turn_a_failure_only_branch_into_success():
    parts = parallel_fixture(); graph = step(parts)['graph']
    graph['nodes'] += [gateway('status', 'SPLIT', ['ok', 'error'], selector={'source': 'NODE_PORT', 'node_id': 'left'}), query('detail')]
    for port in ('ok', 'error'):
        edge(parts, 'left', port)['target'] = 'status'
    add_edge(graph, 'status', 'ok', 'detail'); add_edge(graph, 'status', 'error', 'join')
    node(parts, 'detail')['ports'] = ['error']
    add_edge(graph, 'detail', 'error', 'join')
    assert_rejected(parts, 'PARALLEL_SUCCESS_UNREACHABLE')


def test_explicit_event_root_is_host_evidence_not_an_implicit_wait_receipt():
    parts = fixture()
    node(parts, 'decide')['input_bindings']['eligible']['from'] = {'source': 'event', 'path': ['eligible']}
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['trace']['trust'] == 'CONTENT_ONLY_NOT_AUTHORIZATION'
    # Trusted mode must independently reproduce the declared event record.
    from json_decision import VerifiedDecisionSources
    def wrong_source(prepared):
        records = deepcopy(parts[2]['parameter_snapshot']['parameters'])
        return VerifiedDecisionSources(parts[3], {'event': {}}, records, 30)
    assert code(invoke(parts, wrong_source)) == 'INPUT_BINDING_UNAVAILABLE'


def test_exclusive_pair_metadata_resolves_without_parallel_synchronization():
    parts = routed_fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('merge', 'MERGE', ['ok']))
    node(parts, 'route')['pair_ref'] = 'merge'; node(parts, 'merge')['pair_ref'] = 'route'
    edge(parts, 'route', 'done')['target'] = 'merge'; edge(parts, 'ask', 'ok')['target'] = 'merge'
    add_edge(graph, 'merge', 'ok', 'done')
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    node(parts, 'route')['pair_ref'] = 'absent'
    assert_rejected(parts, 'GATEWAY_PAIR_INVALID')


def selected_parallel_fixture(nested=False):
    """A global success path exists, but CONTROL ask selects a failed branch."""
    parts = routed_fixture(); graph = step(parts)['graph']; bundle = parts[0]
    bundle['deployment']['enabled_node_kinds'].append('PARALLEL')
    graph['nodes'] += [gateway('fork', 'SPLIT', ['left', 'right'], 'join'),
                       gateway('join', 'JOIN', ['ok', 'error'], 'fork'),
                       gateway('right-route', 'SPLIT', ['ask', 'done'], selector={'source': 'DECISION_CONTROL', 'node_id': 'decide'})]
    for name, ports in [('fail', ['error']), ('right-ok', ['ok']), ('after', ['ok'])]:
        target = deepcopy(node(parts, 'ask'))
        target.update(node_id=name, name=name, ports=ports, input_bindings={})
        graph['nodes'].append(target)
    edge(parts, 'route', 'ask')['target'] = 'fork'; edge(parts, 'ask', 'ok')['target'] = 'join'
    add_edge(graph, 'fork', 'left', 'ask', 'left'); add_edge(graph, 'fork', 'right', 'right-route', 'right')
    add_edge(graph, 'right-route', 'ask', 'fail'); add_edge(graph, 'right-route', 'done', 'right-ok')
    add_edge(graph, 'fail', 'error', 'join'); add_edge(graph, 'right-ok', 'ok', 'join')
    add_edge(graph, 'join', 'ok', 'after'); add_edge(graph, 'join', 'error', 'stop'); add_edge(graph, 'after', 'ok', 'done')
    actions = bundle['models']['eligibility']['result_templates']['accepted']['actions']
    for name in ('fail', 'after'):
        actions.append(dict(kind='INTERACTION', intent_id=name, target_node_id=name))
    if nested:
        graph['nodes'] += [gateway('inner', 'SPLIT', ['choice', 'steady'], 'inner-join'),
                           gateway('inner-join', 'JOIN', ['ok', 'error'], 'inner')]
        other = deepcopy(node(parts, 'right-ok')); other.update(node_id='inner-work', name='Inner work')
        graph['nodes'].append(other)
        edge(parts, 'fork', 'right')['target'] = 'inner'
        edge(parts, 'fail', 'error')['target'] = 'inner-join'; edge(parts, 'right-ok', 'ok')['target'] = 'inner-join'
        add_edge(graph, 'inner', 'choice', 'right-route', 'choice'); add_edge(graph, 'inner', 'steady', 'inner-work', 'steady')
        add_edge(graph, 'inner-work', 'ok', 'inner-join')
        add_edge(graph, 'inner-join', 'ok', 'join'); add_edge(graph, 'inner-join', 'error', 'join')
        actions.append(dict(kind='INTERACTION', intent_id='inner-work', target_node_id='inner-work'))
    return parts


@pytest.mark.parametrize('nested', [False, True])
def test_selected_join_cannot_borrow_success_from_an_unselected_route(nested):
    parts = selected_parallel_fixture(nested)
    # Structural success through right-route.done does not prove success for
    # this result's selected ask route. No actual action is executed here.
    validate_definition(parts[0])
    result = invoke(parts)
    assert code(result) == 'INTENT_PATH_MISMATCH'
    assert result['outputs']['decision'] is None


@pytest.mark.parametrize('nested', [False, True])
def test_selected_join_allows_every_branch_with_a_selected_success_alternative(nested):
    parts = selected_parallel_fixture(nested)
    edge(parts, 'right-route', 'ask')['target'] = 'right-ok'
    edge(parts, 'right-route', 'done')['target'] = 'fail'
    actions = parts[0]['models']['eligibility']['result_templates']['accepted']['actions']
    next(a for a in actions if a['intent_id'] == 'fail').update(intent_id='right-ok', target_node_id='right-ok')
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    # A possible error alternative does not remove the selected successful one.
    node(parts, 'right-ok')['ports'].append('error')
    add_edge(step(parts)['graph'], 'right-ok', 'error', 'inner-join' if nested else 'join')
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'


def test_selected_unresolved_branch_cannot_satisfy_join():
    parts = selected_parallel_fixture()
    node(parts, 'fail')['ports'] = ['pending']
    edge(parts, 'fail', 'error')['source_port'] = 'pending'
    validate_definition(parts[0])
    assert code(invoke(parts)) == 'INTENT_PATH_MISMATCH'


def test_declared_exclusive_pair_cannot_point_backwards():
    parts = routed_fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('upstream-merge', 'MERGE', ['ok']))
    node(parts, 'route')['pair_ref'] = 'upstream-merge'; node(parts, 'upstream-merge')['pair_ref'] = 'route'
    edge(parts, 'begin', 'ok')['target'] = 'upstream-merge'
    add_edge(graph, 'upstream-merge', 'ok', 'decide')
    assert_rejected(parts, 'GATEWAY_PAIR_INVALID')


def test_declared_exclusive_pair_cannot_leave_before_its_merge():
    parts = routed_fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('merge', 'MERGE', ['ok']))
    node(parts, 'route')['pair_ref'] = 'merge'; node(parts, 'merge')['pair_ref'] = 'route'
    edge(parts, 'ask', 'ok')['target'] = 'merge'; add_edge(graph, 'merge', 'ok', 'done')
    # The route.done arm still leaves directly, bypassing the declared closure.
    assert_rejected(parts, 'GATEWAY_PAIR_INVALID')


def test_parallel_split_is_not_a_single_node_port_result():
    parts = parallel_fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('bad-selector', 'SPLIT', ['left', 'right'], selector={'source': 'NODE_PORT', 'node_id': 'fork'}))
    edge(parts, 'decide', 'ok')['target'] = 'bad-selector'
    add_edge(graph, 'bad-selector', 'left', 'done'); add_edge(graph, 'bad-selector', 'right', 'done')
    assert_rejected(parts, 'GATEWAY_SELECTOR_INVALID')


def test_parallel_join_is_a_valid_technical_result_source():
    parts = parallel_fixture(); graph = step(parts)['graph']
    graph['nodes'].append(gateway('join-status', 'SPLIT', ['ok', 'error'], selector={'source': 'NODE_PORT', 'node_id': 'join'}))
    edge(parts, 'decide', 'ok')['target'] = 'join-status'
    add_edge(graph, 'join-status', 'ok', 'done'); add_edge(graph, 'join-status', 'error', 'stop')
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'


def test_query_invocation_requires_executor_result_ports_before_io():
    from json_decision import prepare_node
    from json_profiles import canonical_digest
    parts = parallel_fixture(); bundle, ref, inputs, context = parts
    ref = {**ref, 'node_id': 'left'}
    validate_definition(bundle)  # Generic host-adapter structure is inspectable.
    with pytest.raises(JsonProfileError) as exc:
        prepare_node(bundle, ref, canonical_digest(bundle), inputs, context, kind='QUERY')
    assert exc.value.code == 'QUERY_PORT_CONTRACT'


def test_selected_pending_branch_can_resolve_through_declared_wait_receipt():
    parts = wait_fixture(); graph = step(parts)['graph']; bundle = parts[0]
    bundle['deployment']['enabled_node_kinds'].append('PARALLEL')
    other = deepcopy(node(parts, 'ask')); other.update(node_id='other', name='Other')
    after = deepcopy(other); after.update(node_id='after', name='After')
    graph['nodes'] += [other, after, gateway('fork', 'SPLIT', ['waiting', 'other'], 'join'), gateway('join', 'JOIN', ['ok', 'error'], 'fork')]
    node(parts, 'ask')['ports'] = ['pending']; edge(parts, 'ask', 'ok')['source_port'] = 'pending'
    edge(parts, 'route', 'ask')['target'] = 'fork'
    for port in ('received', 'timeout', 'cancelled', 'error'):
        edge(parts, 'answer', port)['target'] = 'join'
    add_edge(graph, 'fork', 'waiting', 'ask', 'waiting'); add_edge(graph, 'fork', 'other', 'other', 'other')
    add_edge(graph, 'other', 'ok', 'join'); add_edge(graph, 'join', 'ok', 'after')
    add_edge(graph, 'join', 'error', 'stop'); add_edge(graph, 'after', 'ok', 'done')
    actions = bundle['models']['eligibility']['result_templates']['accepted']['actions']
    for name in ('other', 'after'):
        actions.append(dict(kind='INTERACTION', intent_id=name, target_node_id=name))
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'


def test_selected_join_obligation_can_include_predecision_sibling_query():
    parts = parallel_fixture(); graph = step(parts)['graph']; bundle = parts[0]
    # Put the main decision inside one fork branch; the other branch remains a
    # predecision query. The join, rather than an ordinary merge, proves both.
    edge(parts, 'fork', 'left')['target'] = 'decide'
    graph['nodes'] = [n for n in graph['nodes'] if n['node_id'] != 'left']
    graph['edges'] = [e for e in graph['edges'] if e['source'] != 'left']
    for port in ('ok', 'error', 'blocked'):
        edge(parts, 'decide', port)['target'] = 'join'
    edge(parts, 'join', 'ok')['target'] = 'done'
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
