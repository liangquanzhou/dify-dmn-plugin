"""Typed, pure DECISION-node boundary for explicit architecture.v2 definitions.

The host owns activation, permissions, IO and workflow progress. No claim made
in JSON (including a source reference or digest) can confer that authority.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable

from json_profiles import (JsonProfileError, MISSING, bounded_json, canonical_digest,
                           compare_condition, decode_object, json_equal, lookup,
                           require, select_rules, validate_condition)

REF_KEYS = ('workflow_id', 'phase_id', 'step_id', 'node_id')
RUN_KEYS = ('workflow_run_id', 'step_run_id', 'attempt_id')
CONTEXT_KEYS = (*RUN_KEYS, 'node_run_id', 'activation_ref', 'subject_scope_ref', 'authorization_context_ref', 'as_of')
QUALITIES = {'KNOWN', 'UNKNOWN', 'NOT_APPLICABLE', 'CONFLICT'}
TYPES = {'string': (str,), 'boolean': (bool,), 'integer': (int,), 'number': (int, float), 'object': (dict,), 'array': (list,)}
PORTS = dict(SUCCEEDED='ok', BLOCKED='blocked', FAILED='error', UNKNOWN='unknown', CANCELLED='cancelled', PENDING='pending')
BLOCKED = {'INPUT_REQUIRED_MISSING', 'INPUT_QUALITY_BLOCKED', 'SNAPSHOT_STALE', 'SNAPSHOT_REUSE_UNVERIFIED',
           'INDETERMINATE_MATCH', 'INPUT_BINDING_UNAVAILABLE', 'SOURCE_AUTHORIZATION_REQUIRED', 'HOST_POLICY_DENIED'}


def fields(value, required, optional=(), code='SCHEMA_INVALID'):
    required, optional = set(required), set(optional)
    require(type(value) is dict and required <= value.keys() <= required | optional,
            code, 'Object fields do not match this contract')


def text(value, code='SCHEMA_INVALID'):
    require(type(value) is str and bool(value), code, 'A nonempty string is required')


def string_list(value, code='SCHEMA_INVALID', unique=False):
    require(type(value) is list, code, 'An array of strings is required')
    for item in value:
        text(item, code)
    if unique:
        require(len(set(value)) == len(value), code, 'Duplicate identifiers are forbidden')


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None, 'SNAPSHOT_STALE', 'Reference times need an explicit timezone')
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise JsonProfileError('SNAPSHOT_STALE', 'Invalid reference time') from None


def binding_shape(binding):
    require(type(binding) is dict and (('literal' in binding) != ('from' in binding)),
            'INVALID_BINDING', 'A binding must select a literal or a source')
    fields(binding, ['literal'] if 'literal' in binding else ['from'], ['source_format'], 'INVALID_BINDING')
    require(binding.get('source_format', 'VALUE') in ('VALUE', 'PARAMETER'), 'INVALID_BINDING', 'Invalid source format')
    if 'from' in binding:
        origin = binding['from']
        fields(origin, ['source', 'path'], ['node_id'], 'INVALID_BINDING')
        require(origin['source'] in ('parameters', 'context', 'node', 'decision', 'inputs', 'api', 'event'),
                'INVALID_BINDING', 'Unsupported binding source')
        string_list(origin['path'], 'INVALID_BINDING')
        require(len(origin['path']) <= 64 and not set(origin['path']) & {'__proto__', 'prototype', 'constructor'},
                'INVALID_BINDING', 'Unsafe binding path')
        if origin['source'] in ('node', 'api'):
            text(origin.get('node_id'), 'INVALID_BINDING')
        else:
            require('node_id' not in origin, 'INVALID_BINDING', 'Only node and API sources name a node')


def bind(binding, roots):
    binding_shape(binding)
    if 'literal' in binding:
        value = binding['literal']
    else:
        origin = binding['from']
        source = roots.get(origin['source'], MISSING)
        if origin['source'] in ('node', 'api'):
            source = source.get(origin['node_id'], MISSING) if type(source) is dict else MISSING
        if origin['source'] == 'parameters' and len(origin['path']) > 1 and origin['path'][1] == 'value':
            record = source.get(origin['path'][0]) if type(source) is dict else None
            require(type(record) is dict and record.get('quality') == 'KNOWN', 'INPUT_QUALITY_BLOCKED', 'Unknown parameter values cannot supply result data')
        value = lookup(source, origin['path'])
    require(value is not MISSING, 'INPUT_BINDING_UNAVAILABLE', 'A declared source is unavailable')
    return deepcopy(value)


def bind_map(bindings, roots):
    return {key: bind(binding, roots) for key, binding in bindings.items()}


def validate_model(model):
    fields(model, ['profile', 'version', 'hit_policy', 'parameters', 'rules', 'result_templates', 'on_no_match'], ['empty_template_ref'], 'INVALID_MODEL')
    require(model['profile'] == 'service-decision-table-v1' and model['hit_policy'] in ('UNIQUE', 'FIRST', 'COLLECT'),
            'UNSUPPORTED_RULE_SEMANTICS', 'Explicit typed decision profile is required')
    text(model['version'], 'INVALID_MODEL')
    require(type(model['parameters']) is dict and type(model['result_templates']) is dict, 'INVALID_MODEL', 'Invalid model dictionaries')
    for name in (*model['parameters'], *model['result_templates']):
        text(name, 'INVALID_MODEL')
    if 'empty_template_ref' in model:
        text(model['empty_template_ref'], 'INVALID_MODEL')
    for contract in model['parameters'].values():
        fields(contract, ['type', 'record_required', 'nullable', 'allowed_quality'], code='INVALID_MODEL')
        require(contract['type'] in TYPES and type(contract['record_required']) is bool and type(contract['nullable']) is bool,
                'INVALID_MODEL', 'Invalid parameter type contract')
        string_list(contract['allowed_quality'], 'INVALID_MODEL')
        require(bool(contract['allowed_quality']) and set(contract['allowed_quality']) <= QUALITIES,
                'INVALID_MODEL', 'Invalid parameter quality contract')
    require(type(model['rules']) is list and 1 <= len(model['rules']) <= 128, 'INVALID_MODEL', 'A typed model needs 1–128 rules')
    ids = []
    for rule in model['rules']:
        fields(rule, ['rule_id', 'when', 'output_template_ref'], code='INVALID_MODEL')
        text(rule['rule_id'], 'INVALID_MODEL')
        require(rule['rule_id'] not in ids, 'DUPLICATE_RULE', 'Duplicate rule identifier')
        ids.append(rule['rule_id'])
        require(type(rule['when']) is list and len(rule['when']) <= 32, 'INVALID_MODEL', 'Too many conditions')
        for condition in rule['when']:
            validate_condition(condition)
            path = condition['path']
            require(len(path) >= 3 and path[0] == 'parameters' and path[1] in model['parameters'] and
                    path[2] in ('value', 'quality') and (path[2] != 'quality' or len(path) == 3),
                    'UNREGISTERED_REFERENCE', 'Typed predicates must select a declared value or quality')
        require(rule['output_template_ref'] in model['result_templates'], 'UNKNOWN_TEMPLATE', 'Rule template is not registered')
    require(model['on_no_match'] in ('ERROR', 'RESULT_TEMPLATE'), 'INVALID_MODEL', 'Explicit no-match policy is required')
    if model['on_no_match'] == 'RESULT_TEMPLATE':
        require(model.get('empty_template_ref') in model['result_templates'], 'UNKNOWN_EMPTY_TEMPLATE', 'No-match template is not registered')
    for template in model['result_templates'].values():
        fields(template, ['state', 'data', 'actions'], code='INVALID_MODEL')
        text(template['state'], 'INVALID_MODEL')
        require(type(template['data']) is dict and type(template['actions']) is list, 'INVALID_MODEL', 'Invalid template')
        for name, binding in template['data'].items():
            text(name, 'INVALID_MODEL')
            binding_shape(binding)
            require(binding.get('from', {}).get('source') in (None, 'parameters', 'node', 'context'),
                    'DATA_BINDING_CYCLE', 'Result data cannot depend on itself or action output')
        action_ids, controls = [], 0
        for action in template['actions']:
            kind = action.get('kind') if type(action) is dict else None
            require(kind in ('CONTROL', 'QUERY', 'INTERACTION', 'BUSINESS'), 'ACTION_INTENT_INVALID', 'Unsupported intent kind')
            fields(action, ['kind', 'intent_id', 'route_ref' if kind == 'CONTROL' else 'target_node_id'], code='ACTION_INTENT_INVALID')
            for value in action.values():
                text(value, 'ACTION_INTENT_INVALID')
            require(action['intent_id'] not in action_ids, 'DUPLICATE_INTENT', 'Duplicate intent in template')
            action_ids.append(action['intent_id'])
            controls += kind == 'CONTROL'
        require(controls <= 1, 'CONTROL_CONFLICT', 'A template can declare at most one route')


def _index(items, key):
    require(type(items) is list and bool(items), 'SCHEMA_INVALID', 'A nonempty declaration array is required')
    result = {}
    for item in items:
        require(type(item) is dict, 'SCHEMA_INVALID', 'Declaration must be an object')
        text(item.get(key))
        require(item[key] not in result, 'DUPLICATE_REFERENCE', 'Duplicate declaration identifier')
        result[item[key]] = item
    return result


def _schema_contract(schema):
    """Offline schema checks; the query boundary owns the shared schema engine."""
    require(type(schema) is dict, 'SCHEMA_INVALID', 'A schema object is required')
    pending = [schema]
    while pending:
        item = pending.pop()
        if type(item) is dict:
            for key in ('$ref', '$dynamicRef', '$recursiveRef'):
                require(key not in item or (type(item[key]) is str and item[key].startswith('#')),
                        'REMOTE_SCHEMA_FORBIDDEN', 'Remote schema retrieval is forbidden')
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    from json_query import QueryError, validate_json_schema
    try:
        validate_json_schema(schema)
    except QueryError as exc:
        raise JsonProfileError('SCHEMA_INVALID', 'Invalid embedded schema: ' + exc.code) from None


def _node_shape(node, bundle):
    common = ['node_id', 'name', 'category', 'kind', 'ports']
    kind = node.get('kind')
    if kind == 'DECISION':
        fields(node, common + ['input_bindings', 'model_ref'])
        text(node['model_ref'])
    elif kind == 'QUERY':
        fields(node, common + ['input_bindings', 'capability_ref', 'requires_intent'])
        text(node['capability_ref'])
        require(type(node['requires_intent']) is bool, 'SCHEMA_INVALID', 'requires_intent must be boolean')
    elif kind == 'ACTION':
        fields(node, common + ['input_bindings', 'action_ref', 'action_kind'])
        text(node['action_ref'])
        require(node['action_kind'] in ('INTERACTION', 'BUSINESS'), 'ACTION_INTENT_INVALID', 'Unknown action kind')
        cap = bundle['capabilities'].get(node['action_ref'])
        require(type(cap) is dict and cap['kind'] == node['action_kind'], 'UNKNOWN_CAPABILITY', 'Action capability must match its kind')
        require(node['action_kind'] != 'BUSINESS' or bundle['deployment']['business_enabled'],
                'PROFILE_NOT_ENABLED', 'Business action declarations require explicit deployment enablement')
    elif kind in ('EXCLUSIVE', 'PARALLEL', 'INCLUSIVE'):
        fields(node, common + ['mode'], ['input_bindings', 'pair_ref', 'selector', 'join_policy', 'failure_policy'])
        require(kind != 'INCLUSIVE', 'GRAPH_PROFILE_UNSUPPORTED', 'Inclusive activation is not supported')
        if 'pair_ref' in node:
            text(node['pair_ref'])
        if kind == 'EXCLUSIVE':
            require(node['mode'] in ('SPLIT', 'MERGE') and not {'join_policy', 'failure_policy'} & node.keys(),
                    'GRAPH_PROFILE_UNSUPPORTED', 'Exclusive gateways split or merge without parallel policies')
            require(('selector' in node) == (node['mode'] == 'SPLIT'), 'GATEWAY_SELECTOR_INVALID', 'Only an exclusive split requires a selector')
        else:
            require(node['mode'] in ('SPLIT', 'JOIN') and 'pair_ref' in node and 'selector' not in node,
                    'PARALLEL_PAIR_INVALID', 'Parallel gateways require a pair and cannot select a route')
            if node['mode'] == 'JOIN':
                require(node.get('join_policy') == 'ALL_SUCCESS' and node.get('failure_policy') == 'CANCEL_REMAINING',
                        'GRAPH_PROFILE_UNSUPPORTED', 'Only ALL_SUCCESS with CANCEL_REMAINING is supported')
                require(set(node['ports']) == {'ok', 'error'}, 'PARALLEL_PORT_CONTRACT', 'Parallel join must map success and failure')
            else:
                require(not {'join_policy', 'failure_policy'} & node.keys(), 'PARALLEL_PAIR_INVALID', 'Join policies belong to the paired JOIN')
        if 'selector' in node:
            fields(node['selector'], ['source', 'node_id'])
            text(node['selector']['node_id'])
            require(node['selector']['source'] in ('DECISION_CONTROL', 'NODE_PORT'), 'GATEWAY_SELECTOR_INVALID', 'Unsupported selector source')
    elif kind == 'START':
        fields(node, common, ['input_bindings'])
        require(node['ports'] == ['ok'], 'START_PORT_CONTRACT', 'START has one ok continuation')
    elif kind == 'END':
        fields(node, common + ['exit_ref'], ['input_bindings'])
        text(node['exit_ref'])
    elif kind == 'WAIT':
        fields(node, common + ['event_type', 'correlation_fields', 'timeout_ms', 'pre_register_before', 'event_bindings', 'event_schema'], ['input_bindings'])
        text(node['event_type']); text(node['pre_register_before'])
        string_list(node['correlation_fields'], unique=True)
        require({'workflow_run_id', 'step_run_id', 'attempt_id', 'intent_id'} <= set(node['correlation_fields']),
                'WAIT_CORRELATION_INVALID', 'WAIT must scope events to the run, step, attempt and intent')
        require(type(node['timeout_ms']) is int and node['timeout_ms'] > 0, 'WAIT_TIMEOUT_INVALID', 'WAIT needs a positive timeout')
        require(set(node['ports']) == {'received', 'timeout', 'cancelled', 'error'}, 'WAIT_PORT_CONTRACT', 'WAIT must map receipt, timeout, cancellation and failure')
        require(type(node['event_bindings']) is dict, 'INVALID_BINDING', 'Invalid event bindings')
        _schema_contract(node['event_schema'])
        for name, binding in node['event_bindings'].items():
            text(name, 'INVALID_BINDING'); binding_shape(binding)
            require(binding.get('from', {}).get('source') in (None, 'event'), 'INVALID_BINDING', 'Event projections read the accepted event only')
    else:
        raise JsonProfileError('PROFILE_NOT_ENABLED', 'Unsupported node kind')
    text(node['name'])
    expected = 'EXECUTION' if kind in ('QUERY', 'DECISION', 'ACTION') else 'GATEWAY' if kind in ('EXCLUSIVE', 'PARALLEL') else 'EVENT'
    require(node['category'] == expected, 'NODE_TYPE_MISMATCH', 'Node category does not match kind')
    require(kind in bundle['deployment']['enabled_node_kinds'], 'PROFILE_NOT_ENABLED', 'Node kind is not enabled')
    string_list(node['ports'], unique=True)
    if expected == 'EXECUTION':
        require(set(node['ports']) <= set(PORTS.values()), 'UNKNOWN_OUTPUT_PORT', 'Execution nodes use registered technical result ports')
    require(kind == 'END' or bool(node['ports']), 'UNMAPPED_OR_AMBIGUOUS_PORT', 'A nonterminal node needs a continuation')
    require(type(node.get('input_bindings', {})) is dict, 'INVALID_BINDING', 'Invalid node bindings')
    for name, binding in node.get('input_bindings', {}).items():
        text(name, 'INVALID_BINDING'); binding_shape(binding)


def _graph_evidence(step, bundle):
    """Prove nested fork obligations and definite execution, without running nodes.

    A stack labels each active branch. Ordinary merges may combine alternative
    paths of one branch, never siblings. A paired join discharges exactly its own
    branch labels. Per-edge evidence prevents a failed join from claiming that
    cancelled sibling sources were completed.
    """
    graph = step['graph']
    fields(graph, ['nodes', 'edges'])
    nodes = _index(graph['nodes'], 'node_id')
    for node in nodes.values():
        _node_shape(node, bundle)
    require(type(graph['edges']) is list, 'SCHEMA_INVALID', 'Edges must be an array')
    outgoing, incoming = {key: [] for key in nodes}, {key: [] for key in nodes}
    edge_ids = set()
    for edge in graph['edges']:
        fields(edge, ['edge_id', 'source', 'source_port', 'target'], ['branch_id'])
        for value in edge.values():
            text(value)
        require(edge['edge_id'] not in edge_ids, 'DUPLICATE_EDGE', 'Duplicate edge ID')
        edge_ids.add(edge['edge_id'])
        require(edge['source'] in nodes and edge['target'] in nodes, 'EDGE_REFERENCE', 'Edge target or source is missing')
        outgoing[edge['source']].append(edge); incoming[edge['target']].append(edge)
    starts = [key for key, node in nodes.items() if node['kind'] == 'START']
    decisions = [key for key, node in nodes.items() if node['kind'] == 'DECISION']
    require(starts == [step['entry_node']] and not incoming[starts[0]], 'SINGLE_START_REQUIRED', 'Step must have one declared START')
    require(decisions == [step['main_decision_node']], 'SINGLE_MAIN_DECISION_REQUIRED', 'Step must have one declared decision')
    order, remaining = [], set(nodes)
    while remaining:
        ready = [key for key in nodes if key in remaining and all(e['source'] not in remaining for e in incoming[key])]
        require(bool(ready), 'GRAPH_CYCLE', 'Node graph must be acyclic')
        order.extend(ready); remaining.difference_update(ready)
    for key, node in nodes.items():
        if node['kind'] == 'END':
            require(not node['ports'] and not outgoing[key] and node['exit_ref'] in step['exits'], 'UNKNOWN_EXIT', 'Invalid END or exit')
        else:
            for port in node['ports']:
                require(sum(e['source_port'] == port for e in outgoing[key]) == 1, 'UNMAPPED_OR_AMBIGUOUS_PORT', 'Each declared port requires one edge')
        require(all(e['source_port'] in node['ports'] for e in outgoing[key]), 'UNKNOWN_OUTPUT_PORT', 'Edge uses undeclared port')
        if node['kind'] == 'EXCLUSIVE' and node['mode'] == 'MERGE':
            require(node['ports'] == ['ok'], 'GATEWAY_PORT_CONTRACT', 'Exclusive merge has one ok continuation')
        if node['kind'] == 'EXCLUSIVE' and 'pair_ref' in node:
            pair = nodes.get(node['pair_ref'])
            require(pair is not None and pair['kind'] == 'EXCLUSIVE' and pair['mode'] != node['mode'] and
                    pair.get('pair_ref', key) == key, 'GATEWAY_PAIR_INVALID', 'Exclusive pair must reference its matching split or merge')
        if node['kind'] == 'PARALLEL':
            pair = nodes.get(node['pair_ref'])
            require(pair is not None and pair['kind'] == 'PARALLEL' and pair.get('pair_ref') == key and
                    pair['mode'] == ('JOIN' if node['mode'] == 'SPLIT' else 'SPLIT'),
                    'PARALLEL_PAIR_INVALID', 'Parallel pairs must be reciprocal SPLIT/JOIN nodes')
            if node['mode'] == 'SPLIT':
                branches = [e.get('branch_id') for e in outgoing[key]]
                require(len(branches) >= 2 and all(type(b) is str and b for b in branches) and len(set(branches)) == len(branches),
                        'FORK_BRANCH_MISMATCH', 'Every fork needs at least two distinct explicit branch identities')
    stacks, edge_stacks, facts, edge_facts, ancestors, evidence = {}, {}, {}, {}, {}, {}
    for key in order:
        node, entering = nodes[key], incoming[key]
        require(key == starts[0] or bool(entering), 'UNREACHABLE_NODE', 'Node is unreachable from START')
        ancestors[key] = set().union(*(ancestors[e['source']] | {e['source']} for e in entering)) if entering else set()
        require(key == starts[0] or starts[0] in ancestors[key], 'UNREACHABLE_NODE', 'Node is unreachable from START')
        contexts = {edge_stacks[e['edge_id']] for e in entering}
        join = node['kind'] == 'PARALLEL' and node['mode'] == 'JOIN'
        if join:
            split = node['pair_ref']
            expected = {e['branch_id'] for e in outgoing[split]}
            require(all(stack and stack[-1][0] == split for stack in contexts) and
                    {stack[-1][1] for stack in contexts} == expected and len({stack[:-1] for stack in contexts}) == 1,
                    'FORK_BRANCH_MISMATCH', 'JOIN must converge every branch of its own active fork')
            stack = next(iter(contexts))[:-1]
            branch_facts = []
            for branch in expected:
                arrivals = [evidence[e['edge_id']]['resolved'] for e in entering
                            if edge_stacks[e['edge_id']][-1][1] == branch and 'resolved' in evidence[e['edge_id']]]
                require(bool(arrivals), 'PARALLEL_SUCCESS_UNREACHABLE', 'Every branch needs a resolved completion path')
                branch_facts.append(set.intersection(*arrivals))
            facts[key] = set.union(*branch_facts) | {key}
        else:
            require(node['kind'] != 'END' or not any(contexts), 'PARALLEL_ESCAPE', 'An active branch cannot leave before its JOIN')
            require(len(contexts) <= 1, 'PARALLEL_CROSS_BRANCH', 'Parallel branches can converge only at their paired JOIN')
            stack = next(iter(contexts), ())
            facts[key] = (set.intersection(*(edge_facts[e['edge_id']] for e in entering)) if entering else set()) | {key}
        stacks[key] = stack
        require(node['kind'] != 'END' or not stack, 'PARALLEL_ESCAPE', 'An active parallel branch cannot leave the Step before JOIN')
        incoming_states = {}
        if not entering:
            incoming_states['resolved'] = {key}
        for state in ('resolved', 'unresolved', 'failed'):
            arrivals = [evidence[e['edge_id']][state] for e in entering if state in evidence[e['edge_id']]]
            if arrivals:
                incoming_states[state] = set.intersection(*arrivals) | {key}
        for edge in outgoing[key]:
            next_stack = stack + ((key, edge['branch_id']),) if node['kind'] == 'PARALLEL' and node['mode'] == 'SPLIT' else stack
            if 'branch_id' in edge:
                require(bool(next_stack) and edge['branch_id'] == next_stack[-1][1], 'FORK_BRANCH_MISMATCH', 'Edge branch identity differs from its active fork')
            edge_stacks[edge['edge_id']] = next_stack
            edge_facts[edge['edge_id']] = (facts[node['pair_ref']] | {key}) if join and edge['source_port'] == 'error' else facts[key]
            port = edge['source_port']
            if join:
                states = {'resolved' if port == 'ok' else 'failed': edge_facts[edge['edge_id']]}
            else:
                states = {}
                for state, known in incoming_states.items():
                    result_state = state
                    technical_output = node['category'] == 'EXECUTION' or node.get('selector', {}).get('source') == 'NODE_PORT'
                    if technical_output and port in ('error', 'blocked', 'cancelled', 'timeout'):
                        result_state = 'failed'
                    elif technical_output and port in ('pending', 'unknown') and state != 'failed':
                        result_state = 'unresolved'
                    elif node['kind'] == 'WAIT':
                        result_state = 'resolved' if port == 'received' and state != 'failed' else 'failed'
                    states[result_state] = states[result_state] & known if result_state in states else known
            evidence[edge['edge_id']] = states
    exclusive_regions = {}
    for key, node in nodes.items():
        if node['kind'] != 'EXCLUSIVE' or 'pair_ref' not in node:
            continue
        split, merge = (key, node['pair_ref']) if node['mode'] == 'SPLIT' else (node['pair_ref'], key)
        if split in exclusive_regions:
            continue
        require(split in ancestors[merge] and split in facts[merge], 'GATEWAY_PAIR_INVALID', 'Exclusive pair must converge downstream of its split')
        region, pending = {split}, [e['target'] for e in outgoing[split]]
        while pending:
            current = pending.pop()
            if current == merge or current in region:
                continue
            require(nodes[current]['kind'] != 'END', 'GATEWAY_PAIR_INVALID', 'Declared exclusive pair must close before leaving the Step')
            region.add(current)
            pending.extend(e['target'] for e in outgoing[current])
        require(all(e['source'] in region for member in region - {split} for e in incoming[member]),
                'GATEWAY_PAIR_INVALID', 'Exclusive region cannot be entered from outside its split')
        exclusive_regions[split] = (merge, region)
    for split, (merge, region) in exclusive_regions.items():
        for other, (other_merge, _) in exclusive_regions.items():
            if other != split and other in region:
                require(other_merge in region, 'GATEWAY_PAIR_INVALID', 'Declared exclusive pairs cannot cross or share their closure')
    # Once a nested join fails, the parent may only receive that failure through
    # technical exclusive plumbing. Do not start new work or abandon the fork.
    def technical_path(target, boundary=None, seen=None, result_source=None, result_port=None):
        seen = set() if seen is None else seen
        if target == boundary or target in seen:
            return
        seen.add(target)
        other = nodes[target]
        if other['kind'] == 'END':
            require(boundary is None and step['exits'][other['exit_ref']]['class'] == 'TECHNICAL',
                    'PARALLEL_FAILURE_PATH', 'Failed JOIN must converge or leave through a technical exit')
            return
        require(other['kind'] == 'EXCLUSIVE', 'PARALLEL_FAILURE_PATH', 'Failed JOIN cannot start execution, another fork or WAIT')
        candidates = outgoing[target]
        if other.get('selector') == {'source': 'NODE_PORT', 'node_id': result_source}:
            candidates = [e for e in candidates if e['source_port'] == result_port]
            require(bool(candidates), 'GATEWAY_ROUTE_UNMAPPED', 'Failure selector must map the originating failure port')
        for edge in candidates:
            technical_path(edge['target'], boundary, seen, result_source, result_port)
    for key, node in nodes.items():
        if node['kind'] == 'PARALLEL' and node['mode'] == 'JOIN':
            boundary = nodes[stacks[key][-1][0]]['pair_ref'] if stacks[key] else None
            technical_path(next(e['target'] for e in outgoing[key] if e['source_port'] == 'error'), boundary, result_source=key, result_port='error')
        elif stacks[key] and (node['category'] == 'EXECUTION' or node['kind'] == 'WAIT'):
            boundary = nodes[stacks[key][-1][0]]['pair_ref']
            for edge in outgoing[key]:
                if edge['source_port'] in ('error', 'blocked', 'cancelled', 'timeout'):
                    technical_path(edge['target'], boundary, result_source=key, result_port=edge['source_port'])
    return nodes, outgoing, incoming, order, ancestors, facts, stacks


def _static_binding(binding, consumer, facts, model, *, template=False, intent=False):
    origin = binding.get('from', {})
    source = origin.get('source')
    if source is None:
        return
    require(source in ('context', 'node', 'inputs', 'event', 'parameters', 'decision'), 'INVALID_BINDING', 'This source is unavailable in a Step node binding')
    if source == 'node':
        require(origin['node_id'] in facts[consumer] - {consumer}, 'DATA_SOURCE_NOT_DEFINITE', 'Source must be completed on every activating path')
    if source == 'parameters':
        require(template or intent, 'INVALID_BINDING', 'Parameters belong to the current decision result scope')
        require(not origin['path'] or origin['path'][0] in model['parameters'], 'UNREGISTERED_REFERENCE', 'Parameter source is not declared')
    if source == 'decision':
        require(intent, 'DATA_BINDING_CYCLE', 'Decision result is available only to downstream intent bindings')


def _validate_step(step, bundle):
    nodes, outgoing, incoming, order, ancestors, facts, stacks = _graph_evidence(step, bundle)
    decision = step['main_decision_node']
    decision_node = nodes[decision]
    require({'ok', 'blocked', 'error'} <= set(decision_node['ports']), 'DECISION_PORT_CONTRACT', 'Decision must map all success, blocked and failure output ports')
    require(decision_node['model_ref'] in bundle['models'], 'UNKNOWN_MODEL', 'Decision model missing')
    model = bundle['models'][decision_node['model_ref']]
    require(set(decision_node['input_bindings']) == set(model['parameters']), 'PARAMETER_BINDING_MISMATCH', 'Bindings must cover declared parameters')
    require(all('source_format' in b for b in decision_node['input_bindings'].values()), 'SOURCE_FORMAT_REQUIRED', 'Typed bindings need explicit source formats')
    for key, node in nodes.items():
        is_intent = node['kind'] == 'ACTION' or (node['kind'] == 'QUERY' and node['requires_intent'])
        if is_intent:
            require(decision in facts[key] - {key}, 'ACTION_BYPASSES_DECISION', 'An intent target must follow the main decision on every activating path')
        for binding in node.get('input_bindings', {}).values():
            _static_binding(binding, decision if is_intent else key, facts, model, intent=is_intent)
        if node['kind'] == 'END' and step['exits'][node['exit_ref']]['class'] != 'TECHNICAL':
            require(decision in facts[key], 'BUSINESS_EXIT_BYPASSES_DECISION', 'Business exit must follow decision')
        if node['kind'] == 'QUERY':
            cap = bundle['capabilities'].get(node['capability_ref'])
            require(type(cap) is dict and cap['kind'] == 'QUERY' and cap['read_only'] is True, 'QUERY_CAPABILITY_NOT_READ_ONLY', 'Query must reference a read-only capability')
        if node.get('selector'):
            selector = node['selector']; source = selector['node_id']
            require(source in facts[key] - {key}, 'UNREGISTERED_REFERENCE', 'Selector requires a definite predecessor')
            require(selector['source'] != 'DECISION_CONTROL' or source == decision, 'GATEWAY_SELECTOR_INVALID', 'Business routes come from the main decision only')
            if selector['source'] == 'NODE_PORT':
                require(nodes[source]['category'] == 'EXECUTION' or nodes[source]['kind'] == 'WAIT' or
                        (nodes[source]['kind'] == 'PARALLEL' and nodes[source]['mode'] == 'JOIN'),
                        'GATEWAY_SELECTOR_INVALID', 'Technical selectors require a result-producing predecessor')
                require(set(node['ports']) <= set(nodes[source]['ports']), 'GATEWAY_ROUTE_UNMAPPED', 'Technical route is not a source result port')
        if node['kind'] == 'WAIT':
            action = nodes.get(node['pre_register_before'])
            require(action is not None and action['kind'] == 'ACTION' and action['action_kind'] == 'INTERACTION' and
                    action['node_id'] in facts[key] - {key} and stacks[action['node_id']] == stacks[key],
                    'WAIT_REGISTRATION_INVALID', 'WAIT must preregister for a definite interaction in the same branch')
    for template in model['result_templates'].values():
        for binding in template['data'].values():
            _static_binding(binding, decision, facts, model, template=True)
        for action in template['actions']:
            if action['kind'] == 'CONTROL':
                require(any(n.get('selector') == {'source': 'DECISION_CONTROL', 'node_id': decision} and action['route_ref'] in n['ports'] for n in nodes.values()),
                        'GATEWAY_ROUTE_UNMAPPED', 'Template route has no matching gateway')
            else:
                target = nodes.get(action['target_node_id'])
                require(target is not None and ((action['kind'] == 'QUERY' and target['kind'] == 'QUERY' and target['requires_intent']) or
                        (action['kind'] != 'QUERY' and target['kind'] == 'ACTION' and target['action_kind'] == action['kind'])),
                        'ACTION_INTENT_INVALID', 'Template intent does not match its target')
    failed_pending = [(e['target'], decision, e['source_port']) for e in outgoing[decision] if e['source_port'] != 'ok']
    failed_seen = set()
    while failed_pending:
        key, result_source, result_port = failed_pending.pop()
        state = (key, result_source, result_port)
        if state in failed_seen:
            continue
        failed_seen.add(state)
        node = nodes[key]
        if node['kind'] == 'END':
            require(step['exits'][node['exit_ref']]['class'] == 'TECHNICAL', 'FAILED_DECISION_BUSINESS_EXIT', 'Technical failures cannot enter business exits')
        edges = outgoing[key]
        if node['kind'] == 'PARALLEL' and node['mode'] == 'JOIN':
            edges = [e for e in edges if e['source_port'] == 'error']
            result_source, result_port = key, 'error'
        elif node.get('selector') == {'source': 'NODE_PORT', 'node_id': result_source}:
            edges = [e for e in edges if e['source_port'] == result_port]
            require(bool(edges), 'GATEWAY_ROUTE_UNMAPPED', 'Technical selector must map the originating failure port')
        failed_pending.extend((e['target'], result_source, result_port) for e in edges)


def validate_definition(bundle):
    fields(bundle, ['schema_version', 'example_only', 'deployment', 'workflows', 'models', 'capabilities', 'asset_locks'])
    require(bundle['schema_version'] == 'service-decision-dsl.node-architecture.v2' and type(bundle['example_only']) is bool, 'SCHEMA_INVALID', 'Expected architecture.v2 definition')
    deployment = bundle['deployment']
    fields(deployment, ['runtime_owner', 'action_backend', 'business_enabled', 'enabled_node_kinds'])
    require(deployment['runtime_owner'] == deployment['action_backend'] == 'HOST' and type(deployment['business_enabled']) is bool, 'MULTIPLE_RUNTIME_OWNERS', 'The host must own runtime and effects')
    string_list(deployment['enabled_node_kinds'], unique=True)
    require(bool(deployment['enabled_node_kinds']) and set(deployment['enabled_node_kinds']) <= {'START', 'END', 'WAIT', 'QUERY', 'DECISION', 'ACTION', 'EXCLUSIVE', 'PARALLEL', 'INCLUSIVE'}, 'PROFILE_NOT_ENABLED', 'Invalid node-kind registry')
    for key in ('models', 'capabilities', 'asset_locks'):
        require(type(bundle[key]) is dict, 'SCHEMA_INVALID', 'Expected definition registry')
        for name in bundle[key]:
            text(name)
    for model in bundle['models'].values():
        validate_model(model)
    for lock in bundle['asset_locks'].values():
        fields(lock, ['kind', 'path', 'digest_kind', 'sha256'])
        require(lock['kind'] in ('QUERY_PLAN', 'OPERATION_REGISTRY', 'HOST_MAPPING') and lock['digest_kind'] == 'SHA256_BYTES', 'ASSET_LOCK_INVALID', 'Invalid asset lock kind')
        text(lock['path'], 'ASSET_LOCK_INVALID')
        require(type(lock['sha256']) is str and re.fullmatch('[a-f0-9]{64}', lock['sha256']) is not None, 'ASSET_LOCK_INVALID', 'Invalid asset digest')
    for capability in bundle['capabilities'].values():
        fields(capability, ['kind', 'read_only', 'implementation', 'input_schema', 'output_schema'], ['query_plan_ref'])
        require(capability['kind'] in ('QUERY', 'INTERACTION', 'BUSINESS') and type(capability['read_only']) is bool and capability['implementation'] in ('QUERY_PLAN', 'HOST', 'MOCK'), 'SCHEMA_INVALID', 'Invalid capability contract')
        if 'query_plan_ref' in capability:
            text(capability['query_plan_ref'])
        if capability['implementation'] == 'QUERY_PLAN':
            lock = bundle['asset_locks'].get(capability.get('query_plan_ref'))
            require(capability['kind'] == 'QUERY' and capability['read_only'] is True and type(lock) is dict and lock['kind'] == 'QUERY_PLAN', 'QUERY_PLAN_ASSET_MISSING', 'Query-plan capability requires a declared query-plan asset lock')
        for field in ('input_schema', 'output_schema'):
            _schema_contract(capability[field])
    workflows = _index(bundle['workflows'], 'workflow_id')
    total_nodes = total_edges = 0
    for workflow in workflows.values():
        fields(workflow, ['workflow_id', 'version', 'flow_type', 'scope', 'entry_phase', 'phases', 'domain_id', 'scene_ref'])
        for key in ('version', 'entry_phase', 'domain_id'):
            text(workflow[key])
        require(workflow['flow_type'] in ('LOCATE', 'SOLVE') and workflow['scope'] in ('EXAMPLE_FRAGMENT', 'DEPLOYABLE') and (workflow['scene_ref'] is None or type(workflow['scene_ref']) is str), 'SCHEMA_INVALID', 'Invalid workflow profile')
        phases = _index(workflow['phases'], 'phase_id')
        require(workflow['entry_phase'] in phases, 'UNKNOWN_ENTRY_PHASE', 'Entry phase is missing')
        all_steps, phase_steps = {}, {}
        for phase in phases.values():
            fields(phase, ['phase_id', 'entry_step', 'steps']); text(phase['entry_step'])
            steps = phase_steps[phase['phase_id']] = _index(phase['steps'], 'step_id')
            require(phase['entry_step'] in steps, 'UNKNOWN_ENTRY_STEP', 'Entry step is missing')
            for step in steps.values():
                fields(step, ['step_id', 'name', 'purpose', 'profile', 'entry_node', 'main_decision_node', 'max_attempts', 'graph', 'exits', 'version', 'reentry_exhausted_exit'])
                for key in ('name', 'purpose', 'version', 'entry_node', 'main_decision_node', 'reentry_exhausted_exit'):
                    text(step[key])
                require(step['profile'] == 'decision-step-v2' and type(step['max_attempts']) is int and step['max_attempts'] >= 1, 'SCHEMA_INVALID', 'Invalid step profile or attempt budget')
                require(type(step['exits']) is dict and bool(step['exits']), 'SCHEMA_INVALID', 'Step needs registered exits')
                fields(step['graph'], ['nodes', 'edges'])
                require(type(step['graph']['nodes']) is list and type(step['graph']['edges']) is list, 'SCHEMA_INVALID', 'Invalid graph arrays')
                total_nodes += len(step['graph']['nodes']); total_edges += len(step['graph']['edges'])
                require(total_nodes <= 256 and total_edges <= 1024, 'DEFINITION_LIMIT_EXCEEDED', 'Definition exceeds node or edge budget')
                all_steps[(phase['phase_id'], step['step_id'])] = step
        transitions = {key: set() for key in all_steps}
        for identity, step in all_steps.items():
            for name, exit_def in step['exits'].items():
                text(name); fields(exit_def, ['class', 'destination'])
                require(exit_def['class'] in ('BUSINESS', 'TECHNICAL', 'REENTRY', 'RETURN'), 'SCHEMA_INVALID', 'Invalid exit class')
                destination = exit_def['destination']
                fields(destination, ['kind'], ['phase_id', 'step_id', 'outcome'])
                kind = destination['kind']
                require(kind in ('STEP', 'PHASE', 'RETURN', 'END_WORKFLOW', 'REENTER_STEP'), 'SCHEMA_INVALID', 'Invalid exit destination')
                for value in destination.values():
                    text(value)
                require((exit_def['class'] == 'REENTRY') == (kind == 'REENTER_STEP'), 'INVALID_REENTRY_EXIT', 'Only a REENTRY exit may reenter its Step')
                if kind in ('STEP', 'PHASE'):
                    fields(destination, ['kind', 'phase_id'] + (['step_id'] if kind == 'STEP' else []))
                    target_phase = phases.get(destination['phase_id'])
                    require(target_phase is not None, 'UNKNOWN_EXIT_TARGET', 'Exit phase is missing')
                    target_step = destination['step_id'] if kind == 'STEP' else target_phase['entry_step']
                    target = (destination['phase_id'], target_step)
                    require(target in all_steps, 'UNKNOWN_EXIT_TARGET', 'Exit step is missing')
                    transitions[identity].add(target)
                elif kind == 'REENTER_STEP':
                    fields(destination, ['kind'])
                else:
                    fields(destination, ['kind'], ['outcome'])
            exhausted = step['exits'].get(step['reentry_exhausted_exit'])
            require(type(exhausted) is dict and exhausted['class'] == 'TECHNICAL' and exhausted['destination']['kind'] != 'REENTER_STEP', 'INVALID_REENTRY_EXIT', 'Attempt exhaustion requires a non-reentry technical exit')
            _validate_step(step, bundle)
        # Cycles between Steps would evade max_attempts; bounded repetition uses
        # the explicit REENTER_STEP destination instead of an implicit back edge.
        remaining = set(all_steps)
        while remaining:
            leaves = {key for key in remaining if not transitions[key] & remaining}
            require(bool(leaves), 'CROSS_STEP_CYCLE', 'Cross-Step cycles must use bounded explicit reentry')
            remaining -= leaves
    return bundle

@dataclass(frozen=True)
class VerifiedDecisionSources:
    """Created only by trusted host code after checking activation/permissions.

    sources contain the fixed NodeIO roots; parameter_records are an independent
    host projection. The evaluator rechecks both and enforces observation age.
    This Python type cannot be selected through tool JSON.
    """
    context: dict
    sources: dict
    parameter_records: dict
    max_age_seconds: float


def prepare_node(bundle_raw, ref_raw, expected_digest, inputs_raw, context_raw, *, kind):
    bundle = decode_object(bundle_raw, 'definition_bundle_json', 1048576)
    ref = decode_object(ref_raw, 'node_ref', 4096)
    inputs = decode_object(inputs_raw, 'inputs_json')
    context = decode_object(context_raw, 'execution_context_json', 32768)
    fields(ref, REF_KEYS)
    for value in ref.values():
        text(value)
    fields(context, CONTEXT_KEYS, ['evaluation_ref', 'business_effect_key'])
    for value in context.values():
        text(value)
    timestamp(context['as_of'])
    digest = canonical_digest(bundle)
    require(type(expected_digest) is str and expected_digest == digest, 'DEFINITION_DIGEST_MISMATCH', 'Definition differs from the configured content pin')
    validate_definition(bundle)
    for workflow in bundle['workflows']:
        for phase in workflow['phases']:
            for step in phase['steps']:
                for node in step['graph']['nodes']:
                    candidate = dict(zip(REF_KEYS, [workflow['workflow_id'], phase['phase_id'], step['step_id'], node['node_id']]))
                    if candidate == ref:
                        require(node['kind'] == kind and node.get('category') == 'EXECUTION', 'NODE_TYPE_MISMATCH', 'Selected node has another execution kind')
                        if kind == 'QUERY':
                            require({'ok', 'blocked', 'error', 'unknown', 'cancelled'} <= set(node['ports']),
                                    'QUERY_PORT_CONTRACT', 'Invoked query must map every result port this executor can return')
                        return dict(bundle=bundle, node_ref=ref, node=node, step=step, inputs=inputs, context=context, digest=digest)
    raise JsonProfileError('UNREGISTERED_REFERENCE', 'Fixed node is absent from this definition')


def prepare_decision(bundle_raw, ref_raw, expected_digest, inputs_raw, context_raw):
    return prepare_node(bundle_raw, ref_raw, expected_digest, inputs_raw, context_raw, kind='DECISION')


def validate_snapshot(prepared):
    inputs, context, bundle = prepared['inputs'], prepared['context'], prepared['bundle']
    fields(inputs, ['parameter_snapshot', 'runtime_snapshot'])
    require(type(inputs['runtime_snapshot']) is dict, 'SCHEMA_INVALID', 'Runtime snapshot must be an object')
    snapshot = inputs['parameter_snapshot']
    fields(snapshot, ['schema_version', 'prepared_for', 'definition_digest', 'subject_scope_ref', 'as_of', 'parameters', 'provenance'], ['example_only', 'reused_from'])
    require(snapshot['schema_version'] == 'service-decision-dsl.parameter-snapshot.v2' and type(snapshot['provenance']) is dict,
            'SCHEMA_INVALID', 'Expected parameter-snapshot.v2')
    require(snapshot['prepared_for'] == prepared['node_ref'] and snapshot['subject_scope_ref'] == context['subject_scope_ref'],
            'SNAPSHOT_SCOPE_MISMATCH', 'Snapshot is for another node or subject')
    require(snapshot['definition_digest'] == prepared['digest'], 'DEFINITION_DIGEST_MISMATCH', 'Snapshot uses another definition')
    as_of = timestamp(context['as_of'])
    require(timestamp(snapshot['as_of']) == as_of, 'SNAPSHOT_STALE', 'Snapshot must use the invocation reference time')
    model = bundle['models'][prepared['node']['model_ref']]
    records = snapshot['parameters']
    require(type(records) is dict and not records.keys() - model['parameters'].keys(), 'INPUT_TYPE_MISMATCH', 'Undeclared parameter record')
    for name, contract in model['parameters'].items():
        if name not in records:
            require(not contract['record_required'], 'INPUT_REQUIRED_MISSING', 'Required parameter record missing', name)
            continue
        record = records[name]
        fields(record, ['quality', 'value', 'source_refs'], ['diagnostic_codes', 'observed_at', 'version'])
        require(record['quality'] in QUALITIES, 'INPUT_QUALITY_BLOCKED', 'Unknown quality marker', name)
        value, quality = record['value'], record['quality']
        require(value is None or type(value) in TYPES[contract['type']], 'INPUT_TYPE_MISMATCH', 'Wrong parameter type', name)
        require((quality == 'KNOWN' and (value is not None or contract['nullable'])) or (quality != 'KNOWN' and value is None),
                'INPUT_TYPE_MISMATCH', 'Invalid known-null or unknown-value carrier', name)
        require(quality in contract['allowed_quality'], 'INPUT_QUALITY_BLOCKED', 'Quality is not allowed by this parameter', name)
        string_list(record['source_refs'], 'INPUT_SOURCE_INVALID')
        require(bool(record['source_refs']), 'INPUT_SOURCE_INVALID', 'Explicit source references are required', name)
        string_list(record.get('diagnostic_codes', []))
        require('TYPE_MISMATCH' not in record.get('diagnostic_codes', []), 'INPUT_TYPE_MISMATCH', 'Type diagnostic cannot be hidden', name)
        require('STALE' not in record.get('diagnostic_codes', []), 'SNAPSHOT_STALE', 'Stale record cannot be used', name)
        if 'observed_at' in record:
            require(timestamp(record['observed_at']) <= as_of, 'SNAPSHOT_STALE', 'Observation is after reference time', name)
    return model, records


def _select_templates(model, records, trace):
    states = []
    for rule in model['rules']:
        conditions = []
        for condition in rule['when']:
            report = compare_condition(condition, {'parameters': records})
            parameter = records.get(condition['path'][1])
            if condition['path'][2] == 'value' and (parameter is None or parameter['quality'] != 'KNOWN'):
                report.update(state='UNKNOWN', reason='QUALITY_NOT_KNOWN')
            conditions.append(report)
        state = 'FALSE' if any(c['state'] == 'FALSE' for c in conditions) else 'UNKNOWN' if any(c['state'] == 'UNKNOWN' for c in conditions) else 'TRUE'
        states.append(state)
        trace['rules'].append({'rule_id': rule['rule_id'], 'match': state, 'conditions': conditions})
    trace['matched_rule_ids'] = [r['rule_id'] for r, state in zip(model['rules'], states) if state == 'TRUE']
    trace['unknown_rule_ids'] = [r['rule_id'] for r, state in zip(model['rules'], states) if state == 'UNKNOWN']
    selected, blockers = select_rules(states, model['hit_policy'])
    require(not blockers, 'INDETERMINATE_MATCH', 'Unknown conditions may alter the decision')
    trace['selected_rule_ids'] = [model['rules'][i]['rule_id'] for i in selected]
    if not selected:
        require(model['on_no_match'] == 'RESULT_TEMPLATE', 'NO_MATCH_UNHANDLED', 'No-match requires an explicit result template')
        return [model['result_templates'][model['empty_template_ref']]]
    return [model['result_templates'][model['rules'][i]['output_template_ref']] for i in selected]


def _selected_intent_path(step, decision_id, route, bundle):
    """Project potential successful intent paths, never activate or run a node.

    A technical failure cannot authorize a new action. Pending/unknown actions
    may lead to a declared WAIT; receipt and ALL_SUCCESS continuation are the
    paths on which subsequent selected work may legitimately become active.
    """
    nodes, full, incoming, order, _, _, stacks = _graph_evidence(step, bundle)
    edges = step['graph']['edges']
    selected = {}
    for key, node in nodes.items():
        candidates = [edge for edge in edges if edge['source'] == key]
        if key == decision_id or (node['kind'] == 'PARALLEL' and node['mode'] == 'JOIN'):
            candidates = [e for e in candidates if e['source_port'] == 'ok']
        elif node['category'] == 'EXECUTION':
            candidates = [e for e in candidates if e['source_port'] not in ('error', 'blocked', 'cancelled')]
        elif node['kind'] == 'WAIT':
            candidates = [e for e in candidates if e['source_port'] == 'received']
        elif node.get('selector', {}).get('source') == 'DECISION_CONTROL':
            candidates = [e for e in candidates if e['source_port'] == route]
        selected[key] = candidates

    def reaches(source, target, graph):
        pending, seen = [source], set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(e['target'] for e in graph[current])
        return False

    # Technical split routes must be consistent with the predecessor port that
    # can actually arrive here. This also handles a selector on the main result.
    changed = True
    while changed:
        changed = False
        for key, node in nodes.items():
            selector = node.get('selector', {})
            if selector.get('source') != 'NODE_PORT':
                continue
            source = selector['node_id']
            before = source != decision_id and reaches(source, decision_id, full)
            candidates = full[source] if before else selected[source]
            ports = {e['source_port'] for e in candidates if
                     (reaches(e['target'], decision_id, full) if before else reaches(e['target'], key, selected))}
            updated = [e for e in selected[key] if e['source_port'] in ports]
            changed |= len(updated) != len(selected[key])
            selected[key] = updated
    # Prove the branch obligations again after route selection. Plain graph
    # reachability is insufficient: one live branch cannot authorize JOIN.ok.
    # These are hypothetical static outcomes, not runtime tokens or receipts.
    edge_states, possible = {}, set()
    for key in order:
        node = nodes[key]
        arrivals = [e for e in incoming[key] if edge_states.get(e['edge_id'])]
        if key == decision_id or node['kind'] == 'START':
            states = {'resolved'}
        elif node['kind'] == 'PARALLEL' and node['mode'] == 'JOIN':
            split = node['pair_ref']
            obligations = {e['branch_id']: set() for e in full[split]}
            for edge in arrivals:
                source = edge['source']
                stack = stacks[source]
                if nodes[source]['kind'] == 'PARALLEL' and nodes[source]['mode'] == 'SPLIT':
                    stack = stack + ((source, edge['branch_id']),)
                # Full structural validation has already proved this pairing.
                obligations[stack[-1][1]].update(edge_states[edge['edge_id']])
            states = {'resolved'} if all('resolved' in values for values in obligations.values()) else set()
        else:
            states = set().union(*(edge_states[e['edge_id']] for e in arrivals)) if arrivals else set()
        if not states:
            continue
        possible.add(key)
        for edge in selected[key]:
            port = edge['source_port']
            technical = node['category'] == 'EXECUTION' or node.get('selector', {}).get('source') == 'NODE_PORT'
            if technical and port in ('error', 'blocked', 'cancelled', 'timeout'):
                continue
            if node['kind'] == 'WAIT' and port == 'received':
                outcomes = {'resolved'}
            elif technical and port in ('pending', 'unknown'):
                outcomes = {'unresolved'}
            else:
                outcomes = states
            edge_states[edge['edge_id']] = outcomes
    reached, pending, consumed = set(), [decision_id], False
    while pending:
        source = pending.pop()
        node = nodes[source]
        if node.get('selector', {}).get('source') == 'DECISION_CONTROL':
            require(route is not None, 'CONTROL_ROUTE_REQUIRED', 'An activated business split needs a selected route')
            require(len(selected[source]) == 1, 'GATEWAY_ROUTE_UNMAPPED', 'Selected route does not map exactly once')
            consumed = True
        for edge in selected[source]:
            if edge_states.get(edge['edge_id']) and edge['target'] in possible and edge['target'] not in reached:
                reached.add(edge['target']); pending.append(edge['target'])
    require(route is None or consumed, 'INTENT_PATH_MISMATCH', 'Selected control route is outside the decision continuation')
    return reached


def _reduce(prepared, templates, records, sources):
    nodes = {node['node_id']: node for node in prepared['step']['graph']['nodes']}
    roots = {**sources, 'parameters': records}
    decision = {'state': templates[0]['state'], 'data': {}, 'actions': []}
    for template in templates:
        require(template['state'] == decision['state'], 'RESULT_CONFLICT', 'Selected states disagree')
        facts = bind_map(template['data'], roots)
        for name, value in facts.items():
            require(name not in decision['data'] or json_equal(decision['data'][name], value), 'RESULT_CONFLICT', 'Selected data facts disagree', name)
            decision['data'][name] = value
    roots['decision'] = decision
    by_target, by_id, routes = {}, {}, set()
    for template in templates:
        for declaration in template['actions']:
            intent = deepcopy(declaration)
            kind = intent['kind']
            if kind == 'CONTROL':
                routes.add(intent['route_ref'])
                identity = ('CONTROL', intent['route_ref'])
            else:
                target = nodes.get(intent['target_node_id'])
                require(target is not None and target.get('category') == 'EXECUTION', 'ACTION_INTENT_INVALID', 'Intent target missing or non-execution')
                require((kind == 'QUERY' and target['kind'] == 'QUERY' and target.get('requires_intent') is True) or
                        (kind != 'QUERY' and target['kind'] == 'ACTION' and target.get('action_kind') == kind),
                        'ACTION_INTENT_INVALID', 'Intent and target kinds differ')
                intent['parameters'] = bind_map(target.get('input_bindings', {}), roots)
                identity = (kind, intent['target_node_id'])
            require(intent['intent_id'] not in by_id or by_id[intent['intent_id']] == identity,
                    'ACTION_INTENT_INVALID', 'An intent identifier names different targets')
            by_id[intent['intent_id']] = identity
            payload = {k: v for k, v in intent.items() if k != 'intent_id'}
            if identity in by_target:
                old = {k: v for k, v in by_target[identity].items() if k != 'intent_id'}
                require(json_equal(payload, old), 'RESULT_CONFLICT', 'Selected intent parameters disagree')
            else:
                by_target[identity] = intent
    require(len(routes) <= 1, 'CONTROL_CONFLICT', 'Selected routes disagree')
    route = next(iter(routes), None)
    reached = _selected_intent_path(prepared['step'], prepared['node']['node_id'], route, prepared['bundle'])
    targets = {key[1] for key in by_target if key[0] != 'CONTROL'}
    require(targets <= reached, 'INTENT_PATH_MISMATCH', 'Selected intent is outside selected route')
    required = {key for key in reached if nodes[key]['kind'] == 'ACTION' or (nodes[key]['kind'] == 'QUERY' and nodes[key].get('requires_intent'))}
    require(required <= targets, 'PATH_ACTION_NOT_SELECTED', 'Selected path lacks a required action intent')
    decision['actions'] = list(by_target.values())
    return decision


def _result(ref, context, status, trace, decision=None, error=None):
    safe_ref = {key: ref.get(key) if type(ref.get(key)) is str and ref[key] else 'unresolved' for key in REF_KEYS}
    safe_run = {key: context.get(key) if type(context.get(key)) is str and context[key] else 'unresolved' for key in RUN_KEYS}
    return {'schema_version': 'service-decision-dsl.node-result.v2', 'node_ref': safe_ref,
            'node_run_id': context.get('node_run_id') if type(context.get('node_run_id')) is str else 'unresolved',
            'run_ref': safe_run, 'execution_status': status, 'output_port': PORTS[status],
            'outputs': {'decision': decision if status == 'SUCCEEDED' else None},
            'diagnostics': [], 'trace': trace, 'error': error}


def evaluate_decision(definition_bundle_json, node_ref, expected_definition_sha256, inputs_json, execution_context_json, *, trusted_policy: Callable | None = None):
    ref, context = {}, {}
    trace = {'engine_called': False, 'selected_rule_ids': [], 'matched_rule_ids': [], 'unknown_rule_ids': [], 'rules': [], 'trust': 'CONTENT_ONLY_NOT_AUTHORIZATION'}
    try:
        prepared = prepare_decision(definition_bundle_json, node_ref, expected_definition_sha256, inputs_json, execution_context_json)
        ref, context = prepared['node_ref'], prepared['context']
        model, records = validate_snapshot(prepared)
        sources = {}
        if trusted_policy is not None:
            require(callable(trusted_policy), 'HOST_POLICY_DENIED', 'Policy must be trusted host code')
            try:
                evidence = trusted_policy(deepcopy(prepared))
            except JsonProfileError:
                raise
            except Exception:
                raise JsonProfileError('HOST_POLICY_DENIED', 'Trusted policy did not authorize this snapshot') from None
            require(type(evidence) is VerifiedDecisionSources, 'HOST_POLICY_DENIED', 'Policy must return verified source evidence')
            require(json_equal(evidence.context, context) and json_equal(evidence.parameter_records, records),
                    'INPUT_BINDING_MISMATCH', 'Host evidence differs from this invocation')
            require(type(evidence.max_age_seconds) in (int, float) and 0 <= evidence.max_age_seconds <= 31536000,
                    'HOST_POLICY_DENIED', 'Host must configure a bounded maximum age')
            sources = decode_object(evidence.sources, 'trusted_sources', 1048576)
            # PARAMETER forwards a typed record; VALUE binds only a known fact.
            # Provenance for VALUE records comes from the verified host evidence,
            # never from a synthetic path name or a caller's claimed digest.
            for name, binding in prepared['node']['input_bindings'].items():
                if name not in records:
                    continue
                value = bind(binding, sources)
                record = records[name]
                expected = record if binding['source_format'] == 'PARAMETER' else record['value']
                require(binding['source_format'] == 'PARAMETER' or record['quality'] == 'KNOWN',
                        'INPUT_BINDING_MISMATCH', 'A raw VALUE source must provide a known fact')
                require(json_equal(value, expected), 'INPUT_BINDING_MISMATCH', 'Fixed sources do not reproduce snapshot records')
            for name, record in records.items():
                require('observed_at' in record and 0 <= (timestamp(context['as_of']) - timestamp(record['observed_at'])).total_seconds() <= evidence.max_age_seconds,
                        'SNAPSHOT_STALE', 'Source observation exceeds trusted maximum age', name)
            trace['trust'] = 'DEPLOYMENT_POLICY_CHECKED'
        else:
            require('reused_from' not in prepared['inputs']['parameter_snapshot'], 'SNAPSHOT_REUSE_UNVERIFIED', 'Reused snapshots need trusted source and permission verification')
        trace.update(engine_called=True, model_ref=prepared['node']['model_ref'], model_version=model['version'], model_sha256=canonical_digest(model),
                     profile=model['profile'], hit_policy=model['hit_policy'], definition_digest=prepared['digest'])
        templates = _select_templates(model, records, trace)
        decision = _reduce(prepared, templates, records, sources)
        result = _result(ref, context, 'SUCCEEDED', trace, decision)
        bounded_json(result)
        return result
    except JsonProfileError as exc:
        trace['selected_rule_ids'] = []
        if exc.code == 'RESULT_TOO_LARGE':
            trace['rules'] = []
            trace['matched_rule_ids'] = []
        error = {'code': exc.code, 'stage': 'decision', 'node_id': ref.get('node_id', 'unresolved'), 'path': exc.path, 'retryable': False, 'message': exc.message}
        return _result(ref, context, 'BLOCKED' if exc.code in BLOCKED else 'FAILED', trace, error=error)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        # Malformed static content is a technical failure, never no-match.
        trace['selected_rule_ids'] = []
        return _result(ref, context, 'FAILED', trace, error={'code': 'SCHEMA_INVALID', 'stage': 'validation', 'path': '', 'retryable': False, 'message': 'Malformed node contract'})


def decision_tool_outputs(result):
    decision = result['outputs']['decision'] if result['execution_status'] == 'SUCCEEDED' else None
    return {'results': result, **{key: result[key] for key in ('execution_status', 'output_port', 'outputs', 'diagnostics', 'trace')},
            'state': decision['state'] if decision else '', 'data': decision['data'] if decision else {}, 'actions': decision['actions'] if decision else []}
