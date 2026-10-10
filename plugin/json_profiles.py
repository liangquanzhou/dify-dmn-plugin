"""Explicit JSON-table profile. Never changes the legacy flat-key evaluator.

Written against the public json-table-v1 contract. No network or dynamic code.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import rfc8785

MISSING = object()
MAX_DEPTH = 64
MAX_INPUT = 262144
MAX_RESPONSE = 2 * 1024 * 1024
UNSAFE_KEYS = frozenset({'__proto__', 'prototype', 'constructor', 'services'})
OPERATORS = frozenset({'eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'exists', 'is_null'})


class JsonProfileError(ValueError):
    def __init__(self, code: str, message: str, path: str = ''):
        super().__init__(message)
        self.code, self.message, self.path = code, message, path


def require(valid: bool, code: str, message: str, path: str = '') -> None:
    if not valid:
        raise JsonProfileError(code, message, path)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'INVALID_JSON', 'Duplicate object keys are forbidden')
        result[key] = value
    return result


def _invalid_constant(_):
    raise JsonProfileError('INVALID_JSON', 'Non-finite numbers are forbidden')


def validate_json_tree(root: Any, max_depth: int = MAX_DEPTH) -> None:
    # Track the current ancestry instead of rejecting harmless shared references.
    pending = [(root, 0, frozenset())]
    while pending:
        item, depth, parents = pending.pop()
        require(depth <= max_depth, 'INVALID_JSON', 'JSON depth exceeds the profile limit')
        kind = type(item)
        if kind in (dict, list):
            require(id(item) not in parents, 'INVALID_JSON', 'Cyclic input is not JSON')
            ancestors = parents | {id(item)}
            if kind is dict:
                for key in item:
                    require(type(key) is str and key not in UNSAFE_KEYS,
                            'INVALID_JSON', 'Unsafe or non-string object key')
                    key.encode('utf-8')
                children = item.values()
            else:
                children = item
            pending.extend((v, depth + 1, ancestors) for v in children)
        elif kind is str:
            item.encode('utf-8')
        elif kind in (int, float):
            require(math.isfinite(item) and (not float(item).is_integer() or abs(item) <= 2**53 - 1),
                    'INVALID_JSON', 'Numbers must be finite and integers safely representable')
        else:
            require(item is None or kind is bool, 'INVALID_JSON', 'Only native JSON values are allowed')


def bounded_json(value: Any, limit: int = MAX_RESPONSE) -> str:
    validate_json_tree(value)
    chunks, size = [], 0
    for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':')).iterencode(value):
        size += len(part.encode('utf-8'))
        require(size <= limit, 'RESULT_TOO_LARGE', 'Serialized JSON exceeds the response limit')
        chunks.append(part)
    return ''.join(chunks)


def decode_object(raw: Any, name: str, limit: int = MAX_INPUT) -> dict:
    try:
        require(type(raw) in (dict, str), 'INVALID_INPUT', f'{name} must be an object or one JSON object string')
        if type(raw) is dict:
            validate_json_tree(raw)
            # Round-trip gives the invocation an isolated copy, not caller-owned mutable data.
            source = bounded_json(raw, limit)
        else:
            source = raw
        require(len(source.encode('utf-8')) <= limit, 'INPUT_TOO_LARGE', f'{name} exceeds its byte budget')
        value = json.loads(source, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        require(type(value) is dict, 'INVALID_INPUT', f'{name} must have an object root')
        validate_json_tree(value)
        return value
    except JsonProfileError as exc:
        if exc.code == 'RESULT_TOO_LARGE':
            raise JsonProfileError('INPUT_TOO_LARGE', f'{name} exceeds its byte budget') from None
        raise
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise JsonProfileError('INVALID_JSON', f'{name} is not safe JSON') from None


def canonical_digest(value: Any) -> str:
    try:
        validate_json_tree(value)
        return hashlib.sha256(rfc8785.dumps(value)).hexdigest()
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise JsonProfileError('INVALID_JSON', 'Content cannot be canonicalized') from None


def json_equal(left: Any, right: Any) -> bool:
    # RFC8785 makes JSON number forms equal while preserving bool/number and null.
    return rfc8785.dumps(left) == rfc8785.dumps(right)


def lookup(value: Any, path: list[str]) -> Any:
    for key in path:
        if type(value) is not dict or key not in value:
            return MISSING
        value = value[key]
    return value


def validate_condition(condition: Any) -> None:
    require(type(condition) is dict and set(condition) == {'path', 'op', 'value'},
            'INVALID_TABLE', 'Each condition needs path, op and value')
    path, op, operand = condition['path'], condition['op'], condition['value']
    require(type(path) is list and 1 <= len(path) <= 16 and
            all(type(key) is str and 1 <= len(key) <= 128 and key not in UNSAFE_KEYS for key in path),
            'INVALID_TABLE', 'A condition path needs 1–16 object keys')
    require(type(op) is str and op in OPERATORS, 'INVALID_TABLE', 'Unsupported comparison operator')
    if op in ('exists', 'is_null'):
        require(type(operand) is bool, 'INVALID_TABLE', 'Presence predicates need boolean operands')
    elif op == 'in':
        require(type(operand) is list and len(operand) <= 128, 'INVALID_TABLE', 'Membership needs at most 128 candidates')
    elif op in ('lt', 'lte', 'gt', 'gte'):
        require(type(operand) in (int, float, str), 'INVALID_TABLE', 'Ordering needs a number or string operand')


def validate_json_table(table: dict) -> None:
    require(set(table) == {'format', 'id', 'version', 'hit_policy', 'rules'}, 'INVALID_TABLE', 'Unexpected table fields')
    require(table['format'] == 'json-table-v1', 'INVALID_TABLE', 'Explicit json-table-v1 format is required')
    for field in ('id', 'version'):
        require(type(table[field]) is str and 1 <= len(table[field]) <= 128, 'INVALID_TABLE', 'Invalid table identity')
    require(table['hit_policy'] in ('FIRST', 'COLLECT', 'UNIQUE'), 'INVALID_TABLE', 'Unsupported hit policy')
    require(type(table['rules']) is list and 1 <= len(table['rules']) <= 128, 'INVALID_TABLE', 'A table needs 1–128 rules')
    identifiers = []
    for rule in table['rules']:
        require(type(rule) is dict and set(rule) == {'id', 'when', 'output'}, 'INVALID_TABLE', 'Invalid rule fields')
        require(type(rule['id']) is str and 1 <= len(rule['id']) <= 128 and rule['id'] not in identifiers,
                'INVALID_TABLE', 'Rule identifiers must be nonempty and unique')
        identifiers.append(rule['id'])
        require(type(rule['when']) is list and len(rule['when']) <= 32, 'INVALID_TABLE', 'At most 32 conjunctive conditions are supported')
        for condition in rule['when']:
            validate_condition(condition)


def compare_condition(condition: dict, inputs: dict) -> dict:
    actual = lookup(inputs, condition['path'])
    operand, op = condition['value'], condition['op']
    state, reason = None, None
    if op == 'exists':
        state = (actual is not MISSING) is operand
    elif actual is MISSING:
        reason = 'MISSING'
    elif op == 'is_null':
        state = (actual is None) is operand
    elif op == 'eq':
        state = json_equal(actual, operand)
    elif op == 'ne':
        state = not json_equal(actual, operand)
    elif op == 'in':
        state = any(json_equal(actual, candidate) for candidate in operand)
    elif ((type(actual) in (int, float) and type(operand) in (int, float)) or
          (type(actual) is str and type(operand) is str)):
        if op == 'lt':
            state = actual < operand
        elif op == 'lte':
            state = actual <= operand
        elif op == 'gt':
            state = actual > operand
        elif op == 'gte':
            state = actual >= operand
    else:
        reason = 'TYPE_MISMATCH'
    return {'path': condition['path'], 'op': op,
            'input_state': 'MISSING' if actual is MISSING else 'NULL' if actual is None else 'VALUE',
            'state': 'UNKNOWN' if state is None else 'TRUE' if state else 'FALSE', 'reason': reason}


def select_rules(states: list[str], policy: str) -> tuple[list[int], list[int]]:
    true_indexes = [i for i, state in enumerate(states) if state == 'TRUE']
    unknown_indexes = [i for i, state in enumerate(states) if state == 'UNKNOWN']
    if policy == 'UNIQUE' and len(true_indexes) > 1:
        raise JsonProfileError('UNIQUE_HIT_CONFLICT', 'Multiple rules match a UNIQUE table')
    if policy == 'FIRST':
        selected = true_indexes[:1]
        blockers = [i for i in unknown_indexes if not selected or i < selected[0]]
    else:
        selected, blockers = true_indexes, unknown_indexes
    return ([] if blockers else selected), blockers


def evaluate_json_table(table: Any, inputs: Any, expected_sha256: Any = None) -> dict:
    response = dict(schema_version='1.0', engine='json-table-v1', status='FAILED', outcome=None,
                    table_id=None, table_version=None, table_sha256=None, hit_policy=None,
                    result=None, matched_rule_ids=[], selected_rule_ids=[], trace=[], error=None)
    try:
        model = decode_object(table, 'table_json')
        data = decode_object(inputs, 'inputs_json')
        validate_json_table(model)
        digest = canonical_digest(model)
        response.update(table_id=model['id'], table_version=model['version'], table_sha256=digest, hit_policy=model['hit_policy'])
        require(expected_sha256 in (None, '', digest), 'MODEL_DIGEST_MISMATCH', 'Table digest differs from the configured pin')
        states = []
        for rule in model['rules']:
            checks = [compare_condition(c, data) for c in rule['when']]
            state = 'FALSE' if any(c['state'] == 'FALSE' for c in checks) else 'UNKNOWN' if any(c['state'] == 'UNKNOWN' for c in checks) else 'TRUE'
            states.append(state)
            response['trace'].append(dict(rule_id=rule['id'], state=state, conditions=checks))
        response['matched_rule_ids'] = [r['id'] for r, state in zip(model['rules'], states) if state == 'TRUE']
        selected, blockers = select_rules(states, model['hit_policy'])
        if blockers:
            response.update(status='WAITING_INPUT', outcome='UNKNOWN')
        else:
            outputs = [model['rules'][i]['output'] for i in selected]
            response.update(status='SUCCEEDED', outcome='MATCHED' if selected else 'NO_MATCH',
                            selected_rule_ids=[model['rules'][i]['id'] for i in selected],
                            result=outputs if model['hit_policy'] == 'COLLECT' else outputs[0] if outputs else None)
        bounded_json(response)
    except JsonProfileError as exc:
        response.update(status='FAILED', outcome=None, result=None, selected_rule_ids=[], error={'code': exc.code, 'message': exc.message})
        if exc.code == 'RESULT_TOO_LARGE':
            response['trace'] = []
            response['matched_rule_ids'] = []
    return response
