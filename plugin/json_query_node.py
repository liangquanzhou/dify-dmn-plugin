"""Fixed architecture-v2 QUERY boundary; registration and authority stay in Python.

This module validates one node and projects its result. It never follows graph
edges, activates another node, loads a registry path, or selects a transport from
caller configuration. Public interface shapes informed this independent adapter.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Callable

from json_decision import (REF_KEYS, RUN_KEYS, bind_map, fields, prepare_node,
                           string_list, text)
from json_profiles import JsonProfileError, canonical_digest
from json_query import (CompiledQueryPlan, QueryDeployment, QueryError, _result,
                        digest, execute_query, json_object)


@dataclass(frozen=True)
class QueryNodeRegistration:
    node_ref: dict
    compiled: CompiledQueryPlan
    query_plan_ref: str
    operation_registry_ref: str


@dataclass(frozen=True)
class VerifiedQueryNode:
    """Independent host evidence after online identity/activation/source checks.

    sources are current, host-authenticated NodeIO roots. selected_intent is the
    actual current QUERY selection, not a copy authenticated by its own hash.
    """
    context: dict
    sources: dict
    source_refs: tuple[str, ...]
    selected_intent: dict | None = None


@dataclass(frozen=True)
class QueryNodeDeployment:
    query: QueryDeployment
    registrations: tuple[QueryNodeRegistration, ...]
    verify_node: Callable[[dict], VerifiedQueryNode | None]


SDK_NODE_DEPLOYMENT: QueryNodeDeployment | None = None


def _wire_result(core, prepared=None, *, plan_ref=None, query_outcome='FOUND'):
    prepared = prepared or {}
    context = prepared.get('context', {})
    query = None
    if core['execution_status'] == 'SUCCEEDED':
        data = core['outputs']
        query = {'outcome': query_outcome, 'data': data,
                 'completeness': 'PARTIAL' if core['trace'].get('partial') or core['trace'].get('unknown_outputs') else 'COMPLETE',
                 'provenance': {**core['provenance'], 'plan_ref': plan_ref,
                                'source_refs': core['trace'].get('source_refs', []),
                                'observed_at': core['trace'].get('observed_at', []),
                                'atomic_snapshot': False}}
    error = None
    if core['diagnostics']:
        error = {'code': core['diagnostics'][0]['code'], 'stage': 'QUERY',
                 'node_id': prepared.get('node_ref', {}).get('node_id', ''),
                 'path': '', 'retryable': False, 'message': 'Query did not produce a complete usable result'}
    return {'schema_version': 'service-decision-dsl.node-result.v2',
            'node_ref': prepared.get('node_ref', {}),
            'node_run_id': context.get('node_run_id', ''),
            'run_ref': {key: context.get(key, '') for key in RUN_KEYS},
            'execution_status': core['execution_status'], 'output_port': core['output_port'],
            'outputs': {'query': query}, 'diagnostics': core['diagnostics'],
            'trace': {**core['trace'], 'definition_digest': prepared.get('digest'),
                      'authorization': core['provenance'].get('authorization', 'NONE')},
            'error': error}


def execute_query_node(definition_bundle_json, node_ref, expected_definition_sha256,
                       inputs_json, execution_context_json, *, deployment=None):
    prepared = None
    provenance = {'environment': 'UNCONFIGURED', 'mock': False, 'authorization': 'NONE'}
    try:
        prepared = prepare_node(definition_bundle_json, node_ref, expected_definition_sha256,
                                inputs_json, execution_context_json, kind='QUERY')
        fields(prepared['inputs'], ['parameters', 'source_refs'], code='INVALID_QUERY_INPUT')
        parameters = prepared['inputs']['parameters']
        if type(parameters) is not dict:
            raise QueryError('SCHEMA_MISMATCH', 'Query parameters must be an object')
        string_list(prepared['inputs']['source_refs'], 'QUERY_SOURCE_MISMATCH', unique=True)
        if deployment is None:
            return _wire_result(_result('BLOCKED', 'QUERY_CONNECTION_NOT_CONFIGURED'), prepared)
        if not isinstance(deployment, QueryNodeDeployment) or not callable(deployment.verify_node):
            raise QueryError('QUERY_TRUSTED_HOST_REQUIRED', 'Node verification requires a trusted host')
        query = deployment.query
        provenance = {'environment': query.environment, 'mock': query.environment == 'SYNTHETIC', 'authorization': 'NONE'}
        registrations = [r for r in deployment.registrations if r.node_ref == prepared['node_ref']]
        if len(registrations) != 1:
            raise QueryError('QUERY_NODE_NOT_REGISTERED', 'Exactly one fixed-node registration is required')
        registration = deepcopy(registrations[0])
        compiled = registration.compiled
        capability = query.capabilities.get(prepared['node']['capability_ref'])
        if capability is None or capability.id != compiled.capability.id or capability.definition_sha256 != prepared['digest'] or capability.query_plan_sha256 != compiled.capability.query_plan_sha256:
            raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Node capability differs from the reviewed registration')
        bundle = prepared['bundle']
        declared = bundle['capabilities'][capability.id]
        if declared.get('implementation') != 'QUERY_PLAN' or declared.get('query_plan_ref') != registration.query_plan_ref:
            raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Node must use its registered query plan')
        if compiled.operation_registry_ref != registration.operation_registry_ref:
            raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Query plan names a different registry')
        for ref, kind, expected in (
                (registration.query_plan_ref, 'QUERY_PLAN', compiled.query_plan_bytes_sha256),
                (registration.operation_registry_ref, 'OPERATION_REGISTRY', compiled.operation_registry_bytes_sha256)):
            lock = bundle['asset_locks'].get(ref)
            if type(lock) is not dict or lock.get('kind') != kind or lock.get('digest_kind') != 'SHA256_BYTES' or lock.get('sha256') != expected:
                raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'A required asset-byte lock differs')
        if digest(declared['input_schema']) != digest(capability.input_schema) or digest(declared['output_schema']) != digest(capability.output_schema):
            raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Capability schema differs from the definition')
        for name, descriptor in compiled.operation_registry.items():
            actual = query.operation_registry.get(name)
            # A pinned fixed transport may add its transport_sha256. Compiled
            # registry semantics and source identities must still match exactly.
            if type(actual) is not dict or digest({key: value for key, value in actual.items() if key != 'transport_sha256'}) != digest(descriptor):
                raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Operation registry differs from the reviewed asset')
        native_context = {'subject_id': prepared['context']['subject_scope_ref'],
                          'run_id': prepared['context']['workflow_run_id'],
                          'activation_id': prepared['context']['activation_ref'],
                          'node_ref': digest(prepared['node_ref']),
                          'selected_intent': {'kind': 'QUERY', 'capability_id': capability.id,
                                              'inputs_sha256': digest(parameters)}}
        native_request = {'capability_id': capability.id, 'definition_sha256': prepared['digest'],
                          'query_plan_sha256': capability.query_plan_sha256,
                          'operation_registry_sha256': query.operation_registry_sha256,
                          'inputs': parameters, 'context': native_context}

        def authorize(request):
            verified = deployment.verify_node(deepcopy(prepared))
            if not isinstance(verified, VerifiedQueryNode) or verified.context != prepared['context']:
                return False
            if type(verified.sources) is not dict or type(verified.source_refs) is not tuple or list(verified.source_refs) != prepared['inputs']['source_refs']:
                return False
            # Inputs are rebound from independently authenticated roots. There
            # is no implicit current-input root that could authenticate itself.
            try:
                rebound = bind_map(prepared['node'].get('input_bindings', {}), verified.sources)
            except JsonProfileError:
                return False
            if digest(rebound) != digest(parameters):
                return False
            selected = verified.selected_intent
            if prepared['node'].get('requires_intent') or selected is not None:
                if type(selected) is not dict or set(selected) != {'kind', 'intent_id', 'target_node_id', 'parameters'} or selected['kind'] != 'QUERY' or selected['target_node_id'] != prepared['node_ref']['node_id'] or type(selected['intent_id']) is not str or not selected['intent_id'] or digest(selected['parameters']) != digest(parameters):
                    return False
            return query.authorize(deepcopy(request)) is True

        core = execute_query(native_request, deployment=replace(query, authorize=authorize), binding_context=prepared['context'])
        outcome = 'FOUND'
        if core['execution_status'] == 'SUCCEEDED' and not core['trace'].get('partial') and not core['trace'].get('unknown_outputs') and capability.not_found_when is not None and digest(core['outputs']) == digest(capability.not_found_when):
            outcome = 'NOT_FOUND'
        return _wire_result(core, prepared, plan_ref=compiled.plan_id, query_outcome=outcome)
    except (QueryError, JsonProfileError) as exc:
        status = 'BLOCKED' if exc.code in {'QUERY_TRUSTED_HOST_REQUIRED', 'QUERY_NODE_NOT_REGISTERED',
                                         'QUERY_ASSET_LOCK_MISMATCH', 'QUERY_NOT_AUTHORIZED',
                                         'INPUT_BINDING_UNAVAILABLE', 'INPUT_QUALITY_BLOCKED'} else 'FAILED'
        return _wire_result(_result(status, exc.code, provenance=provenance), prepared)
    except Exception:
        return _wire_result(_result('FAILED', 'QUERY_ADAPTER_ERROR', provenance=provenance), prepared)
