"""Independent synthetic typed-decision and trust-boundary scenarios."""
from copy import deepcopy
import pytest
from json_profiles import canonical_digest
from json_decision import evaluate_decision, decision_tool_outputs, VerifiedDecisionSources


def fixture(policy='UNIQUE'):
    ref = {'workflow_id': 'support', 'phase_id': 'P1', 'step_id': 'eligibility', 'node_id': 'decide'}
    context = {k: 'synthetic-' + k for k in ('workflow_run_id', 'step_run_id', 'attempt_id', 'node_run_id', 'activation_ref', 'subject_scope_ref', 'authorization_context_ref')}
    context['as_of'] = '2026-10-09T12:00:00Z'
    records = {'eligible': {'quality': 'KNOWN', 'value': True, 'source_refs': ['SYNTHETIC:confirmed'], 'observed_at': '2026-10-09T11:59:55Z'}}
    model = {'profile': 'service-decision-table-v1', 'version': 'fixture-1', 'hit_policy': policy,
             'parameters': {'eligible': {'type': 'boolean', 'record_required': True, 'nullable': False, 'allowed_quality': ['KNOWN', 'UNKNOWN', 'CONFLICT', 'NOT_APPLICABLE']}},
             'rules': [{'rule_id': 'yes', 'when': [{'path': ['parameters', 'eligible', 'value'], 'op': 'eq', 'value': True}], 'output_template_ref': 'accepted'}],
             'result_templates': {'accepted': {'state': 'ELIGIBLE', 'data': {'eligibility': {'from': {'source': 'parameters', 'path': ['eligible', 'value']}}}, 'actions': []},
                                  'empty': {'state': 'INELIGIBLE', 'data': {}, 'actions': []}},
             'on_no_match': 'RESULT_TEMPLATE', 'empty_template_ref': 'empty'}
    nodes = [
        {'node_id': 'begin', 'name': 'Begin', 'category': 'EVENT', 'kind': 'START', 'ports': ['ok']},
        {'node_id': 'decide', 'name': 'Eligibility', 'category': 'EXECUTION', 'kind': 'DECISION', 'ports': ['ok', 'error', 'blocked'], 'model_ref': 'eligibility',
         'input_bindings': {'eligible': {'from': {'source': 'context', 'path': ['eligible']}, 'source_format': 'PARAMETER'}}},
        {'node_id': 'done', 'name': 'Done', 'category': 'EVENT', 'kind': 'END', 'ports': [], 'exit_ref': 'business'},
        {'node_id': 'stop', 'name': 'Stopped', 'category': 'EVENT', 'kind': 'END', 'ports': [], 'exit_ref': 'technical'}]
    edges = [dict(edge_id=f'e{i}', source=s, source_port=p, target=t) for i, (s,p,t) in enumerate([('begin','ok','decide'), ('decide','ok','done'), ('decide','error','stop'), ('decide','blocked','stop')])]
    exits = {k: {'class': c, 'destination': {'kind': 'END_WORKFLOW', 'outcome': k}} for k,c in [('business','BUSINESS'),('technical','TECHNICAL')]}
    step = {'step_id': 'eligibility', 'name': 'Eligibility', 'purpose': 'Synthetic gate', 'profile': 'decision-step-v2', 'version': '1', 'entry_node': 'begin', 'main_decision_node': 'decide', 'max_attempts': 1, 'graph': {'nodes': nodes, 'edges': edges}, 'exits': exits, 'reentry_exhausted_exit': 'technical'}
    bundle = {'schema_version': 'service-decision-dsl.node-architecture.v2', 'example_only': True,
              'deployment': {'runtime_owner': 'HOST', 'action_backend': 'HOST', 'business_enabled': False, 'enabled_node_kinds': ['START','DECISION','END','QUERY','ACTION','EXCLUSIVE']},
              'workflows': [{'workflow_id': 'support', 'version': '1', 'flow_type': 'SOLVE', 'scope': 'EXAMPLE_FRAGMENT', 'entry_phase': 'P1', 'domain_id': 'synthetic', 'scene_ref': None,
                             'phases': [{'phase_id': 'P1', 'entry_step': 'eligibility', 'steps': [step]}]}],
              'models': {'eligibility': model}, 'capabilities': {}, 'asset_locks': {}}
    inputs = {'parameter_snapshot': {'schema_version': 'service-decision-dsl.parameter-snapshot.v2', 'prepared_for': ref, 'definition_digest': canonical_digest(bundle),
                                    'subject_scope_ref': context['subject_scope_ref'], 'as_of': context['as_of'], 'parameters': records, 'provenance': {'environment': 'SYNTHETIC'}}, 'runtime_snapshot': {}}
    return bundle, ref, inputs, context


def invoke(parts, policy=None, repin=True):
    bundle, ref, inputs, context = parts
    if repin:
        inputs['parameter_snapshot']['definition_digest'] = canonical_digest(bundle)
    return evaluate_decision(bundle, ref, canonical_digest(bundle), inputs, context, trusted_policy=policy)


def code(response):
    return response['error']['code']


def test_typed_success_and_known_false_no_match():
    parts = fixture()
    result = invoke(parts)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['outputs']['decision'] == {'state': 'ELIGIBLE', 'data': {'eligibility': True}, 'actions': []}
    assert result['trace']['trust'] == 'CONTENT_ONLY_NOT_AUTHORIZATION'
    parts[2]['parameter_snapshot']['parameters']['eligible']['value'] = False
    assert invoke(parts)['outputs']['decision']['state'] == 'INELIGIBLE'


@pytest.mark.parametrize('quality,value,expected', [('KNOWN','true','INPUT_TYPE_MISMATCH'), ('UNKNOWN',False,'INPUT_TYPE_MISMATCH'), ('UNKNOWN',None,'INDETERMINATE_MATCH'), ('KNOWN',None,'INPUT_TYPE_MISMATCH'), ('CONFLICT',None,'INDETERMINATE_MATCH')])
def test_unknown_is_not_false_and_cannot_hide_type_error(quality,value,expected):
    parts = fixture(); parts[2]['parameter_snapshot']['parameters']['eligible'].update(quality=quality,value=value)
    assert code(invoke(parts)) == expected


def test_known_null_is_different_from_unknown():
    parts = fixture()
    model = parts[0]['models']['eligibility']; model['parameters']['eligible']['nullable'] = True
    model['rules'][0]['when'][0].update(op='is_null', value=True)
    record = parts[2]['parameter_snapshot']['parameters']['eligible']; record['value'] = None
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    record['quality'] = 'UNKNOWN'
    assert code(invoke(parts)) == 'INDETERMINATE_MATCH'


@pytest.mark.parametrize('mutation,expected', [
    (lambda p: p[2]['parameter_snapshot']['parameters'].clear(), 'INPUT_REQUIRED_MISSING'),
    (lambda p: p[2]['parameter_snapshot'].update(subject_scope_ref='another'), 'SNAPSHOT_SCOPE_MISMATCH'),
    (lambda p: p[2]['parameter_snapshot'].update(as_of='2026-10-09T11:00:00Z'), 'SNAPSHOT_STALE'),
    (lambda p: p[2]['parameter_snapshot']['parameters']['eligible'].update(observed_at='2026-10-10T00:00:00Z'), 'SNAPSHOT_STALE'),
    (lambda p: p[2]['parameter_snapshot']['parameters']['eligible'].update(source_refs=[]), 'INPUT_SOURCE_INVALID'),
    (lambda p: p[2]['parameter_snapshot'].update(reused_from='old'), 'SNAPSHOT_REUSE_UNVERIFIED'),
    (lambda p: p[2]['parameter_snapshot']['parameters']['eligible'].update(diagnostic_codes=['TYPE_MISMATCH']), 'INPUT_TYPE_MISMATCH'),
    (lambda p: p[0]['models']['eligibility']['parameters']['eligible'].update(allowed_quality=['UNKNOWN']), 'INPUT_QUALITY_BLOCKED')])
def test_invalid_snapshot_and_quality_boundaries(mutation,expected):
    parts = fixture(); mutation(parts)
    response = invoke(parts)
    assert code(response) == expected
    convenience = decision_tool_outputs(response)
    assert convenience['state'] == '' and convenience['data'] == {} and convenience['actions'] == []


def test_unique_conflict_wins_over_unknown_and_same_outputs():
    parts = fixture()
    model = parts[0]['models']['eligibility']
    model['rules'] += [dict(rule_id='also', when=[], output_template_ref='accepted'), dict(rule_id='unknown', when=[{'path':['parameters','eligible','value','missing'],'op':'eq','value':True}], output_template_ref='accepted')]
    response = invoke(parts)
    assert code(response) == 'UNIQUE_HIT_CONFLICT'
    assert response['trace']['matched_rule_ids'] == ['yes','also']
    assert response['trace']['unknown_rule_ids'] == ['unknown']
    assert response['outputs']['decision'] is None


def test_first_unknown_position_and_collect_conflict():
    parts = fixture('FIRST'); model = parts[0]['models']['eligibility']
    unknown = dict(rule_id='unknown', when=[{'path':['parameters','eligible','value','missing'],'op':'eq','value':True}], output_template_ref='accepted')
    model['rules'].append(unknown)
    assert invoke(parts)['execution_status'] == 'SUCCEEDED'
    model['rules'].reverse()
    assert code(invoke(parts)) == 'INDETERMINATE_MATCH'
    parts = fixture('COLLECT'); model = parts[0]['models']['eligibility']
    model['rules'].append(dict(rule_id='no',when=[],output_template_ref='empty'))
    assert code(invoke(parts)) == 'RESULT_CONFLICT'


def policy_for(parts, max_age=30, change=None):
    def policy(prepared):
        records = deepcopy(parts[2]['parameter_snapshot']['parameters'])
        if change:
            change(records)
        return VerifiedDecisionSources(deepcopy(parts[3]), {'context': records}, records, max_age)
    return policy


def test_trusted_sources_rebind_and_age_reuse():
    parts = fixture(); parts[2]['parameter_snapshot']['reused_from'] = 'earlier'
    response = invoke(parts, policy_for(parts))
    assert response['execution_status'] == 'SUCCEEDED' and response['trace']['trust'] == 'DEPLOYMENT_POLICY_CHECKED'
    assert code(invoke(parts, policy_for(parts, max_age=1))) == 'SNAPSHOT_STALE'
    assert code(invoke(parts, policy_for(parts, change=lambda records: records['eligible'].update(value=False)))) == 'INPUT_BINDING_MISMATCH'
    assert code(invoke(parts, lambda _: {'verified':True})) == 'HOST_POLICY_DENIED'


def test_hash_and_self_reported_provenance_never_authorize():
    parts = fixture()
    parts[2]['parameter_snapshot']['provenance']['verified'] = True
    assert invoke(parts)['trace']['trust'] == 'CONTENT_ONLY_NOT_AUTHORIZATION'
    assert code(evaluate_decision(parts[0],parts[1],'0'*64,parts[2],parts[3])) == 'DEFINITION_DIGEST_MISMATCH'


def test_no_match_without_template_is_technical_failure():
    parts=fixture(); model=parts[0]['models']['eligibility']; model['on_no_match']='ERROR'
    parts[2]['parameter_snapshot']['parameters']['eligible']['value']=False
    assert code(invoke(parts))=='NO_MATCH_UNHANDLED'


def test_invalid_graph_fails_even_when_bad_node_would_not_run():
    parts=fixture(); graph=parts[0]['workflows'][0]['phases'][0]['steps'][0]['graph']
    graph['edges'][2]['target']='done'
    assert code(invoke(parts))=='FAILED_DECISION_BUSINESS_EXIT'


def routed_fixture():
    parts=fixture('COLLECT'); bundle=parts[0]; step=bundle['workflows'][0]['phases'][0]['steps'][0]; graph=step['graph']
    graph['nodes'] += [dict(node_id='route',name='Route',kind='EXCLUSIVE',category='GATEWAY',mode='SPLIT',ports=['ask','done'],selector={'source':'DECISION_CONTROL','node_id':'decide'}),
                       dict(node_id='ask',name='Ask',kind='ACTION',category='EXECUTION',ports=['ok'],action_ref='human',action_kind='INTERACTION',input_bindings={'confirmed':{'from':{'source':'decision','path':['data','eligibility']}}})]
    graph['edges'][1]['target']='route'
    graph['edges'] += [dict(edge_id='route-ask',source='route',source_port='ask',target='ask'),dict(edge_id='route-done',source='route',source_port='done',target='done'),dict(edge_id='ask-done',source='ask',source_port='ok',target='done')]
    bundle['capabilities']['human']={'kind':'INTERACTION','read_only':False,'implementation':'HOST','input_schema':{},'output_schema':{}}
    template=bundle['models']['eligibility']['result_templates']['accepted']
    template['actions']=[dict(intent_id='control',kind='CONTROL',route_ref='ask'),dict(intent_id='request',kind='INTERACTION',target_node_id='ask')]
    return parts


def test_data_reduced_before_intent_binding_and_route_checks():
    parts=routed_fixture()
    result=invoke(parts)
    assert result['execution_status']=='SUCCEEDED',result
    assert result['outputs']['decision']['actions'][1]['parameters']=={'confirmed':True}
    template=parts[0]['models']['eligibility']['result_templates']['accepted']
    template['actions'][0]['route_ref']='done'
    assert code(invoke(parts))=='INTENT_PATH_MISMATCH'
    template['actions'][0]['route_ref']='ask'; template['actions'].pop()
    assert code(invoke(parts))=='PATH_ACTION_NOT_SELECTED'


def test_unselected_template_cannot_supply_path_action():
    parts=routed_fixture(); model=parts[0]['models']['eligibility']
    model['result_templates']['empty']['actions']=[model['result_templates']['accepted']['actions'].pop()]
    assert code(invoke(parts))=='PATH_ACTION_NOT_SELECTED'


def test_value_binding_requires_verified_known_fact():
    parts = fixture()
    node=parts[0]['workflows'][0]['phases'][0]['steps'][0]['graph']['nodes'][1]
    node['input_bindings']['eligible']['source_format']='VALUE'
    def policy(prepared):
        return VerifiedDecisionSources(parts[3], {'context':{'eligible':True}}, deepcopy(parts[2]['parameter_snapshot']['parameters']), 30)
    assert invoke(parts,policy)['execution_status']=='SUCCEEDED'


def test_unknown_parameter_value_cannot_supply_data_even_if_quality_rule_matches():
    parts=fixture(); model=parts[0]['models']['eligibility']
    model['rules'][0]['when'][0]={'path':['parameters','eligible','quality'],'op':'eq','value':'UNKNOWN'}
    parts[2]['parameter_snapshot']['parameters']['eligible'].update(quality='UNKNOWN',value=None)
    assert code(invoke(parts))=='INPUT_QUALITY_BLOCKED'


def test_collect_equal_data_deduplicates_and_different_data_fails():
    parts=fixture('COLLECT'); model=parts[0]['models']['eligibility']
    model['rules'].append(dict(rule_id='second',when=[],output_template_ref='second'))
    model['result_templates']['second']=deepcopy(model['result_templates']['accepted'])
    assert invoke(parts)['outputs']['decision']['data']=={'eligibility':True}
    model['result_templates']['second']['data']['eligibility']={'literal':False}
    assert code(invoke(parts))=='RESULT_CONFLICT'


def test_collect_intents_deduplicate_but_conflicting_routes_fail():
    parts=routed_fixture(); model=parts[0]['models']['eligibility']
    model['rules'].append(dict(rule_id='second',when=[],output_template_ref='second'))
    model['result_templates']['second']=deepcopy(model['result_templates']['accepted'])
    model['result_templates']['second']['actions'][1]['intent_id']='alternate-name'
    assert len(invoke(parts)['outputs']['decision']['actions'])==2
    model['result_templates']['second']['actions'][0]['route_ref']='done'
    model['result_templates']['second']['actions'][0]['intent_id']='alternate-control'
    assert code(invoke(parts))=='CONTROL_CONFLICT'


@pytest.mark.parametrize('mutation',[
    lambda p:p[0].update(unrecognized=True),
    lambda p:p[0]['deployment'].update(runtime_owner='PLUGIN'),
    lambda p:p[0]['workflows'][0]['phases'][0]['steps'][0]['graph']['edges'][0].update(source_port='unknown'),
    lambda p:p[0]['workflows'][0]['phases'][0]['steps'][0]['graph']['nodes'].append(deepcopy(p[0]['workflows'][0]['phases'][0]['steps'][0]['graph']['nodes'][0])),
    lambda p:p[0]['workflows'][0]['phases'][0]['steps'][0]['graph']['edges'][0].update(target='missing'),
    lambda p:p[0]['models']['eligibility']['rules'][0].update(output_template_ref='missing'),
    lambda p:p[0]['models']['eligibility']['rules'][0]['when'][0].update(op='eval'),
    lambda p:p[2]['parameter_snapshot'].update(extra='ignored?'),
    lambda p:p[3].update(as_of='2026-10-09T12:00:00'),
    lambda p:p[0]['asset_locks'].update(query={'kind':'QUERY_PLAN','path':'plan.json','digest_kind':'SHA256_BYTES','sha256':'bad'}),
])
def test_invalid_schema_never_succeeds(mutation):
    parts=fixture();mutation(parts)
    response=invoke(parts)
    assert response['execution_status'] in ('FAILED','BLOCKED') and response['outputs']['decision'] is None


def test_legacy_success_then_failure_outputs_are_fresh():
    from tools.evaluate_decision import EvaluateTypedDecisionTool
    tool=EvaluateTypedDecisionTool.from_credentials({})
    parts=fixture();bundle,ref,inputs,context=parts
    request=dict(definition_bundle_json=bundle,node_ref=ref,expected_definition_sha256=canonical_digest(bundle),inputs_json=inputs,execution_context_json=context)
    first=list(tool._invoke(request));request['inputs_json']='{'
    second=list(tool._invoke(request))
    def variables(messages):
        return {m.message.variable_name:m.message.variable_value for m in messages if m.type.value=='variable'}
    assert variables(first)['state']=='ELIGIBLE'
    assert variables(second)['state']=='' and variables(second)['data']=={} and variables(second)['actions']==[]


def test_decision_requires_every_output_port_it_can_return():
    parts = fixture()
    step = parts[0]['workflows'][0]['phases'][0]['steps'][0]
    node = next(n for n in step['graph']['nodes'] if n['node_id'] == 'decide')
    node['ports'].remove('ok')
    step['graph']['nodes'] = [n for n in step['graph']['nodes'] if n['node_id'] != 'done']
    step['graph']['edges'] = [e for e in step['graph']['edges'] if e['target'] != 'done']
    response = invoke(parts)
    assert code(response) == 'DECISION_PORT_CONTRACT'
    assert response['outputs']['decision'] is None


@pytest.mark.parametrize('port', ['blocked', 'error'])
def test_decision_cannot_omit_technical_ports(port):
    parts = fixture()
    graph = parts[0]['workflows'][0]['phases'][0]['steps'][0]['graph']
    node = next(n for n in graph['nodes'] if n['node_id'] == 'decide')
    node['ports'].remove(port)
    graph['edges'] = [e for e in graph['edges'] if not (e['source'] == 'decide' and e['source_port'] == port)]
    assert code(invoke(parts)) == 'DECISION_PORT_CONTRACT'


@pytest.mark.parametrize('reference,lock', [(None,None),('absent',None),('asset',{'kind':'HOST_MAPPING','path':'host.json','digest_kind':'SHA256_BYTES','sha256':'a'*64})])
def test_query_plan_capabilities_require_correct_asset_lock_even_if_unused(reference,lock):
    parts=fixture()
    capability={'kind':'QUERY','read_only':True,'implementation':'QUERY_PLAN','input_schema':{},'output_schema':{}}
    if reference is not None:capability['query_plan_ref']=reference
    parts[0]['capabilities']['read']=capability
    if lock:parts[0]['asset_locks']['asset']=lock
    assert code(invoke(parts))=='QUERY_PLAN_ASSET_MISSING'
