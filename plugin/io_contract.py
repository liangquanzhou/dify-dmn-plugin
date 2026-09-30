"""Bounded JSON boundary for the single-table Tool; no I/O or business rules."""
import hashlib
import json
import math
from typing import Any

from evaluator import TableError, evaluate_table, validate_table
from decision_policy import unknown_policy, apply_policy
from model_identity import model_identity

MAX_SAFE_INTEGER = 2**53 - 1
MAX_TABLE_BYTES = 512 * 1024
MAX_VALUES_BYTES = 256 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 20000
MAX_RULES = 1000


def _error(code: str, path: str, message: str) -> None:
    raise TableError(code, path, message)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _error('INVALID_JSON', '$', 'Duplicate object keys are not allowed')
        result[key] = value
    return result


def _constant(_: str) -> None:
    _error('INVALID_JSON', '$', 'Non-finite numeric constants are not allowed')


def parse_object(raw: Any, parameter: str, limit: int) -> dict[str, Any]:
    path = '$.' + parameter
    if not isinstance(raw, str) or not raw.strip():
        _error('INVALID_INPUT', path, 'A non-empty JSON object string is required')
    try:
        encoded = raw.encode('utf-8')
    except UnicodeEncodeError:
        _error('INVALID_JSON', path, 'Invalid Unicode in JSON text')
    if len(encoded) > limit:
        _error('LIMIT_EXCEEDED', path, 'JSON input exceeds the byte limit')
    try:
        result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, TableError):
            raise
        _error('INVALID_JSON', path, 'Invalid JSON object text')
    if not isinstance(result, dict):
        _error('INVALID_INPUT', path, 'The JSON root must be an object')
    stack = [(result, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _error('LIMIT_EXCEEDED', path, 'JSON exceeds the structural limit')
        if isinstance(value, dict):
            for key in value:
                try:
                    key.encode('utf-8')
                except UnicodeEncodeError:
                    _error('INVALID_JSON', path, 'Invalid Unicode in a JSON key')
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
                _error('INVALID_JSON', path, 'Invalid Unicode in a JSON string')
        elif type(value) in (int, float):
            if isinstance(value, float) and not math.isfinite(value):
                _error('INVALID_INPUT', path, 'Numeric values must be finite')
            if (isinstance(value, int) or value.is_integer()) and abs(value) > MAX_SAFE_INTEGER:
                _error('INVALID_INPUT', path, 'Integer values must be within the JavaScript safe-integer range; use strings for identifiers')
    return result


def exact_json(value: Any) -> str:
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    chunks = []
    size = 0
    for chunk in encoder.iterencode(value):
        size += len(chunk.encode('utf-8'))
        if size > MAX_RESULT_BYTES:
            _error('LIMIT_EXCEEDED', '$', 'The evaluation result exceeds the output limit')
        chunks.append(chunk)
    return ''.join(chunks)


def prepare_model(raw_table: Any, expected_sha256: Any = None) -> tuple[dict[str, Any], str, str]:
    table = parse_object(raw_table, 'table_json', MAX_TABLE_BYTES)
    if isinstance(table.get('rules'), list) and len(table['rules']) > MAX_RULES:
        _error('LIMIT_EXCEEDED', '$.table_json.rules', 'The table exceeds the rule-count limit')
    validate_table(table)
    policy = unknown_policy(table)
    return table, policy, model_identity(table, expected_sha256)


def compile_table_config(raw_table: Any) -> dict[str, str]:
    """Compile two static Tool fields; preserve source text and keep the lock external."""
    _, _, digest = prepare_model(raw_table)
    return {'table_json': raw_table, 'expected_sha256': digest}


def invoke_table(parameters: dict[str, Any]) -> dict[str, Any]:
    raw_table = parameters.get('table_json')
    table, policy, digest = prepare_model(raw_table, parameters.get('expected_sha256'))
    values = parse_object(parameters.get('values_json'), 'values_json', MAX_VALUES_BYTES)
    decision = apply_policy(table, evaluate_table(table, values), policy, digest)
    result = decision['result']
    matched = result['matched']
    serialized = exact_json(result)
    if len(serialized.encode('utf-8')) > MAX_RESULT_BYTES:
        _error('LIMIT_EXCEEDED', '$', 'The evaluation result exceeds the output limit')
    return {
        'result': result,
        'result_json': serialized,
        'matched': matched,
        'outputs': [rule.get('output') for rule in matched],
        'evaluations': result['evaluations'],
        'matched_rule_ids': [rule['id'] for rule in matched],
        'status': decision['status'],
        'table_id': table['id'],
        'table_version': hashlib.sha256(raw_table.encode('utf-8')).hexdigest(),
        **{key: value for key, value in decision.items() if key not in ('result', 'status')},
    }
