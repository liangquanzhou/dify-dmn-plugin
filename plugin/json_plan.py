"""Bounded advisory compatibility adapter, not a replacement workflow runtime.

Only local synthetic queries and pure JSON-table evaluation are dispatched.
There is no graph activation, persistent state, WAIT/resume or business action.
"""
from __future__ import annotations

from typing import Any

from json_profiles import (JsonProfileError, canonical_digest, evaluate_json_table,
                           json_equal, validate_json_table)
from json_query import QueryError, digest, json_object, query_local

MAX_PLAN_BYTES = 1_600_000
MAX_PLAN_RESPONSE_BYTES = 2 * 1024 * 1024
_MISSING = object()


def _fail(code: str, message: str):
    raise QueryError(code, message)


def _mapping(mapping: Any, *, allowed_steps: set[str] | None = None):
    if type(mapping) is not dict or len(mapping) > 128:
        _fail('INVALID_BINDING', 'A bounded binding object is required')
    for binding in mapping.values():
        _binding(binding, allowed_steps=allowed_steps)


def _binding(binding: Any, *, allowed_steps: set[str] | None = None):
    if type(binding) is not dict:
        _fail('INVALID_BINDING', 'Bindings must be literal or from objects')
    if set(binding) == {'literal'}:
        return
    if set(binding) != {'from'}:
        _fail('INVALID_BINDING', 'Exactly one binding source is required')
    path = binding['from']
    if type(path) is not list or not 1 <= len(path) <= 16 or any(type(p) is not str or not p for p in path):
        _fail('INVALID_BINDING', 'Binding paths require 1–16 nonempty string components')
    if path[0] not in {'inputs', 'steps'}:
        _fail('INVALID_BINDING', 'Only inputs and prior steps can be bound')
    if path[0] == 'steps':
        if len(path) < 3 or (allowed_steps is not None and path[1] not in allowed_steps):
            _fail('UNDECLARED_DEPENDENCY', 'Step bindings must follow explicit transitive dependencies')


def _resolve(binding: dict, root: dict):
    if 'literal' in binding:
        return binding['literal']
    value = root
    for component in binding['from']:
        if type(value) is dict:
            value = value.get(component, _MISSING)
        elif type(value) is list and component == 'length':
            value = len(value)
        elif type(value) is list and component.isascii() and component.isdecimal():
            index = int(component)
            value = value[index] if index < len(value) else _MISSING
        else:
            return _MISSING
        if value is _MISSING:
            break
    return value


def _bind(mapping: dict, root: dict, *, require=False) -> dict:
    out = {}
    for name, binding in mapping.items():
        value = _resolve(binding, root)
        if value is _MISSING:
            if require:
                _fail('MISSING_OUTPUT', 'A projected value is not available')
        else:
            out[name] = value
    return out


def _validate(request: dict):
    if set(request) != {'plan', 'models', 'inputs'}:
        _fail('INVALID_PLAN_REQUEST', 'Plan request requires plan, models and inputs')
    plan, models, inputs = request['plan'], request['models'], request['inputs']
    if type(plan) is not dict or set(plan) - {'format', 'id', 'version', 'flow', 'phases', 'outputs'}:
        _fail('INVALID_PLAN', 'Unrecognized plan structure')
    if not {'format', 'id', 'version', 'flow', 'phases', 'outputs'} <= set(plan):
        _fail('INVALID_PLAN', 'Required plan fields are missing')
    if plan['format'] != 'json-plan-v1' or plan['version'] != '0.3.0' or type(plan['id']) is not str or not plan['id']:
        _fail('INVALID_PLAN', 'Only explicit json-plan-v1 version 0.3.0 is supported')
    phases = plan['phases']
    expected = {'locate_problem': ['LOCATE'], 'solve_problem': ['P1', 'P2', 'P3', 'P4', 'P5']}.get(plan['flow'])
    if expected is None or type(phases) is not list or [p.get('id') if type(p) is dict else None for p in phases] != expected:
        _fail('INVALID_PHASES', 'Flow must declare LOCATE or all P1–P5 phases in order')
    if type(models) is not dict or not 1 <= len(models) <= 64:
        _fail('INVALID_MODELS', 'Between 1 and 64 pinned models are required')
    json_object(inputs)
    for model_id, model in models.items():
        if not model_id or type(model) is not dict or set(model) != {'table', 'sha256'}:
            _fail('INVALID_MODEL', 'Models require table and sha256')
        if type(model['table']) is not dict:
            _fail('INVALID_MODEL', 'A plan model table must be a JSON object, not encoded text')
        table = json_object(model['table'])
        validate_json_table(table)
        if type(model['sha256']) is not str or canonical_digest(table) != model['sha256']:
            _fail('MODEL_HASH_MISMATCH', 'Pinned model digest does not match its content')
    steps, phase_index = {}, {}
    for phase_no, phase in enumerate(phases):
        if set(phase) - {'id', 'steps', 'skip_reason'} or type(phase.get('steps')) is not list or len(phase['steps']) > 64:
            _fail('INVALID_PHASE', 'Phase requires a bounded list of steps')
        if not phase['steps']:
            if type(phase.get('skip_reason')) is not str or not phase['skip_reason'].strip():
                _fail('INVALID_PHASE', 'An empty phase requires an explicit skip_reason')
        elif not any(type(step) is dict and step.get('kind') == 'decision' for step in phase['steps']):
            _fail('INVALID_PHASE', 'A nonempty phase requires at least one decision')
        for step in phase['steps']:
            if type(step) is not dict or type(step.get('id')) is not str or not step['id'] or step['id'] in steps:
                _fail('DUPLICATE_STEP', 'Step identifiers must be nonempty and globally unique')
            if step.get('kind') not in {'query', 'decision'} or type(step.get('depends_on')) is not list:
                _fail('INVALID_STEP', 'Step kind and explicit dependencies are required')
            deps = step['depends_on']
            if any(type(dep) is not str for dep in deps) or len(set(deps)) != len(deps):
                _fail('INVALID_DEPENDENCY', 'Dependencies must be distinct step identifiers')
            steps[step['id']] = step
            phase_index[step['id']] = phase_no
    if len(steps) > 128:
        _fail('LIMIT_EXCEEDED', 'Plan exceeds 128 steps')
    for step_id, step in steps.items():
        for dep in step['depends_on']:
            if dep not in steps or phase_index[dep] > phase_index[step_id]:
                _fail('INVALID_DEPENDENCY', 'Missing or later-phase dependency')
    ordered = []
    complete = set()
    ancestors = {}
    for phase in phases:
        pending = list(phase['steps'])
        while pending:
            # Stable Kahn ordering: choose the earliest declared ready step.
            ready = next((step for step in pending if set(step['depends_on']) <= complete), None)
            if ready is None:
                _fail('DEPENDENCY_CYCLE', 'Step dependencies contain a cycle')
            step_id = ready['id']
            deps = set(ready['depends_on'])
            ancestors[step_id] = deps | set().union(*(ancestors[dep] for dep in deps))
            ordered.append((phase['id'], ready))
            complete.add(step_id)
            pending.remove(ready)
    for step_id, step in steps.items():
        base = {'id', 'kind', 'depends_on'}
        if step['kind'] == 'query':
            fields = {'capability_id', 'input_contract', 'output_contract', 'parameters'}
            if set(step) != base | fields or step['capability_id'] not in {'demo.ticket_lookup', 'demo.order_lookup'}:
                _fail('INVALID_QUERY_STEP', 'Only fixed synthetic query capabilities are supported')
            if step['input_contract'] != step['capability_id'] + '.input.v1' or step['output_contract'] != step['capability_id'] + '.output.v1':
                _fail('CONTRACT_MISMATCH', 'Query contract pins do not match the capability')
            _mapping(step['parameters'], allowed_steps=ancestors[step_id])
        else:
            fields = {'model_id', 'hit_policy', 'inputs'}
            if not base | fields <= set(step) or set(step) - (base | fields | {'terminate_when'}):
                _fail('INVALID_DECISION_STEP', 'Decision fields are invalid')
            if step['model_id'] not in models:
                _fail('MISSING_MODEL', 'Decision model does not exist')
            if step['hit_policy'] != models[step['model_id']]['table'].get('hit_policy'):
                _fail('HIT_POLICY_MISMATCH', 'Decision policy does not match the pinned model')
            _mapping(step['inputs'], allowed_steps=ancestors[step_id])
            if 'terminate_when' in step:
                terminate = step['terminate_when']
                if type(terminate) is not dict or set(terminate) != {'value', 'equals', 'outputs'}:
                    _fail('INVALID_TERMINATION', 'Termination requires value, equals and outputs')
                allowed = ancestors[step_id] | {step_id}
                _binding(terminate['value'], allowed_steps=allowed)
                _mapping(terminate['outputs'], allowed_steps=allowed)
    _mapping(plan['outputs'], allowed_steps=set(steps))
    return plan, models, inputs, ordered


def execute_json_plan(request: Any, expected_sha256: str | None = None) -> dict:
    """Validate all assets before execution, then fail-fast in stable DAG order."""
    result = {'status': 'FAILED', 'outcome': None, 'outputs': None, 'steps': [], 'phases': [],
              'terminated_by': None, 'plan_id': None, 'plan_version': None, 'flow': None,
              'plan_sha256': None, 'request_sha256': None,
              'provenance': {'environment': 'SYNTHETIC', 'advisory_only': True,
                             'execution_authority': 'ADVISORY_ONLY'}, 'error': None}
    try:
        request = json_object(request, limit=MAX_PLAN_BYTES)
        result['request_sha256'] = digest(request)
        if expected_sha256 not in (None, '') and expected_sha256 != result['request_sha256']:
            _fail('REQUEST_HASH_MISMATCH', 'Request digest does not match its expected lock')
        plan, models, inputs, ordered = _validate(request)
        result.update(plan_id=plan['id'], plan_version=plan['version'], flow=plan['flow'], plan_sha256=digest(plan))
        root = {'inputs': inputs, 'steps': {}}
        stop = None
        for phase_id, step in ordered:
            record = {'id': step['id'], 'phase_id': phase_id, 'kind': step['kind'], 'status': None, 'response': None}
            result['steps'].append(record)
            if stop:
                record.update(status='SKIPPED' if stop == 'TERMINATED' else 'BLOCKED', reason=stop)
                continue
            mapping = step['parameters'] if step['kind'] == 'query' else step['inputs']
            values = _bind(mapping, root)
            if step['kind'] == 'query':
                response = query_local({'capability_id': step['capability_id'], 'parameters': values})
                status = response['execution_status']
            else:
                model = models[step['model_id']]
                response = evaluate_json_table(model['table'], values, expected_sha256=model['sha256'])
                status = response['status']
            record.update(status=status, response=response)
            root['steps'][step['id']] = response
            if status != 'SUCCEEDED':
                result['status'] = 'WAITING_INPUT' if status in {'WAITING_INPUT', 'UNKNOWN', 'BLOCKED'} else 'FAILED'
                stop = result['status']
            elif 'terminate_when' in step:
                terminate = step['terminate_when']
                condition = _resolve(terminate['value'], root)
                if condition is _MISSING:
                    result.update(status='WAITING_INPUT', error={'code': 'MISSING_TERMINATION_VALUE'})
                    record.update(status='WAITING_INPUT', reason='MISSING_TERMINATION_VALUE')
                    stop = 'WAITING_INPUT'
                elif json_equal(condition, terminate['equals']):
                    try:
                        outputs = _bind(terminate['outputs'], root, require=True)
                    except QueryError as exc:
                        result.update(status='WAITING_INPUT', error={'code': exc.code})
                        record.update(status='WAITING_INPUT', reason=exc.code)
                        stop = 'WAITING_INPUT'
                    else:
                        result.update(status='SUCCEEDED', outcome='TERMINATED', outputs=outputs, terminated_by=step['id'])
                        stop = 'TERMINATED'
            # A bounded response is checked before any next step, not only at the end.
            json_object(result, limit=MAX_PLAN_RESPONSE_BYTES)
        if stop is None:
            try:
                outputs = _bind(plan['outputs'], root, require=True)
            except QueryError as exc:
                result.update(status='WAITING_INPUT', error={'code': exc.code})
            else:
                result.update(status='SUCCEEDED', outcome='COMPLETED', outputs=outputs)
        for phase in plan['phases']:
            phase_steps = [record for record in result['steps'] if record['phase_id'] == phase['id']]
            statuses = {record['status'] for record in phase_steps}
            status = next((s for s in ['FAILED', 'WAITING_INPUT', 'UNKNOWN', 'BLOCKED', 'SUCCEEDED', 'SKIPPED'] if s in statuses), 'SKIPPED')
            result['phases'].append({'id': phase['id'], 'status': status,
                                     'skip_reason': phase.get('skip_reason') if not phase_steps else None})
        return json_object(result, limit=MAX_PLAN_RESPONSE_BYTES)
    except (QueryError, JsonProfileError) as exc:
        result.update(status='FAILED', outcome=None, outputs=None, terminated_by=None,
                      error={'code': exc.code, 'message': str(exc)})
        if exc.code == 'LIMIT_EXCEEDED':
            result['steps'] = []
            result['phases'] = []
            result['trace_truncated'] = True
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        result.update(status='FAILED', outcome=None, outputs=None, terminated_by=None,
                      error={'code': 'INVALID_PLAN', 'message': 'Plan structure or content is invalid'})
        return result
