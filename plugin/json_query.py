"""Read-only, bounded query adapters. JSON cannot install a deployment or transport.

The default SDK route has no deployment. A trusted embedding host must register
reviewed capabilities, transports and an online authorization callback in Python.
Only the optional host-configured fixed-IP GET/read-only POST transport performs network I/O.
There is no ambient credential lookup, dynamic endpoint resolution, retry or dynamic import.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
import re
import socket
import ssl
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlsplit

import rfc8785
import regex
from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from referencing.exceptions import NoSuchResource

MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DANGEROUS = {'__proto__', 'constructor', 'prototype'}
_MISSING = object()


class QueryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def json_object(raw: Any, *, limit: int = MAX_REQUEST_BYTES) -> dict:
    """Decode once and clone JSON; reject ambiguous and hostile representations."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise QueryError('INVALID_JSON', 'Duplicate keys are not allowed')
            out[key] = value
        return out

    if isinstance(raw, str):
        try:
            if len(raw.encode('utf-8')) > limit:
                raise QueryError('LIMIT_EXCEEDED', 'JSON exceeds the byte limit')
            raw = json.loads(raw, object_pairs_hook=pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 QueryError('INVALID_JSON', 'Non-finite number')))
        except (ValueError, UnicodeError, RecursionError) as exc:
            if isinstance(exc, QueryError):
                raise
            raise QueryError('INVALID_JSON', 'Invalid JSON object') from None
    if type(raw) is not dict:
        raise QueryError('INVALID_INPUT', 'One JSON object is required')
    active = set()
    count = 0

    def inspect(value, depth):
        nonlocal count
        count += 1
        if depth > 64 or count > 100000:
            raise QueryError('LIMIT_EXCEEDED', 'JSON structure exceeds the limit')
        if type(value) in (dict, list):
            if id(value) in active:
                raise QueryError('INVALID_JSON', 'Circular JSON is not allowed')
            active.add(id(value))
            if type(value) is dict:
                for key, child in value.items():
                    if type(key) is not str or key in _DANGEROUS:
                        raise QueryError('INVALID_JSON', 'Invalid or unsafe object key')
                    key.encode('utf-8')
                    inspect(child, depth + 1)
            else:
                for child in value:
                    inspect(child, depth + 1)
            active.remove(id(value))
        elif type(value) is str:
            value.encode('utf-8')
        elif type(value) in (int, float):
            if not math.isfinite(value) or (float(value).is_integer() and abs(value) > 2**53 - 1):
                raise QueryError('INVALID_JSON', 'Numeric value is not JSON-safe')
        elif value is not None and type(value) is not bool:
            raise QueryError('INVALID_JSON', 'Only JSON values are allowed')
    try:
        inspect(raw, 0)
        encoded = json.dumps(raw, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (UnicodeError, OverflowError, RecursionError):
        raise QueryError('INVALID_JSON', 'Invalid JSON value') from None
    if len(encoded) > limit:
        raise QueryError('LIMIT_EXCEEDED', 'JSON exceeds the byte limit')
    return json.loads(encoded)


def digest(value: Any) -> str:
    try:
        return hashlib.sha256(rfc8785.dumps(value)).hexdigest()
    except (ValueError, OverflowError):
        raise QueryError('INVALID_JSON', 'Content cannot be canonicalized') from None


def _lock(value: Any) -> str:
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise QueryError('INVALID_ASSET_LOCK', 'A lowercase SHA-256 asset lock is required')
    return value


def _result(status: str, code: str, *, outputs=None, trace=None, provenance=None) -> dict:
    ports = {'SUCCEEDED': 'ok', 'BLOCKED': 'blocked', 'FAILED': 'error',
             'UNKNOWN': 'unknown', 'CANCELLED': 'cancelled', 'WAITING_INPUT': 'blocked'}
    return {'execution_status': status, 'output_port': ports[status],
            'outputs': outputs, 'diagnostics': [] if code == 'OK' else [{'code': code}],
            'trace': trace or {}, 'provenance': provenance or {'environment': 'UNCONFIGURED', 'mock': False}}


def query_local(request: Any) -> dict:
    """Fixed, offline SYNTHETIC fixtures; never a fallback for execute_query."""
    provenance = {'environment': 'SYNTHETIC', 'mock': True, 'source': 'bundled-fixture',
                  'advisory_only': True}
    try:
        request = json_object(request)
        if set(request) != {'capability_id', 'parameters'}:
            raise QueryError('INVALID_REQUEST', 'Only capability_id and parameters are accepted')
        capability = request['capability_id']
        fields = {'demo.ticket_lookup': 'ticket_id', 'demo.order_lookup': 'order_id'}
        if type(capability) is not str or capability not in fields:
            raise QueryError('UNKNOWN_CAPABILITY', 'Capability is not registered')
        parameters = request['parameters']
        key = fields[capability]
        if type(parameters) is not dict or set(parameters) - {key}:
            raise QueryError('INVALID_PARAMETERS', 'Unexpected query parameter')
        identifier = parameters.get(key)
        if identifier is None or identifier == '':
            out = _result('WAITING_INPUT', 'MISSING_INPUT', provenance=provenance)
            out['query_status'] = 'UNKNOWN'
        elif type(identifier) is not str:
            raise QueryError('INVALID_PARAMETERS', 'Lookup identifier must be a string')
        elif identifier in {'T-UNKNOWN', 'O-UNKNOWN', 'T-TIMEOUT', 'O-TIMEOUT', 'T-ERROR', 'O-ERROR'}:
            suffix = identifier.rsplit('-', 1)[1]
            out = _result('WAITING_INPUT' if suffix == 'UNKNOWN' else 'FAILED',
                          'SYNTHETIC_' + suffix, provenance=provenance)
            out['query_status'] = suffix
        else:
            outputs = None
            prefix = 'T' if key == 'ticket_id' else 'O'
            if identifier in {prefix + '-100', prefix + '-200', prefix + '-300'}:
                number = identifier.split('-')[1]
                outputs = {key: identifier}
                if prefix == 'T':
                    outputs['order_id'] = 'O-' + number
                else:
                    outputs.update(availability_state={'100': 'CONFIRMED_ABSENT', '200': 'CONFIRMED_PRESENT', '300': 'UNKNOWN'}[number],
                                   evidence_state='UNKNOWN' if number == '300' else 'KNOWN')
            out = _result('SUCCEEDED', 'OK', outputs=outputs, provenance=provenance)
            out['query_status'] = 'FOUND' if outputs is not None else 'NOT_FOUND'
        out.update(status=out['execution_status'], outcome=out['query_status'],
                   error=None if not out['diagnostics'] else out['diagnostics'][0],
                   capability_id=capability, input_contract=capability + '.input.v1',
                   output_contract=capability + '.output.v1')
        return out
    except QueryError as exc:
        out = _result('FAILED', exc.code, provenance=provenance)
        out.update(status='FAILED', outcome=None, error={'code': exc.code})
        return out


@dataclass(frozen=True)
class QueryBudget:
    max_calls: int = 16
    max_pages: int = 16
    max_response_bytes: int = MAX_RESPONSE_BYTES
    timeout_seconds: float = 10.0
    max_batch_items: int = 100

    def validate(self):
        for name, ceiling in [('max_calls', 1000), ('max_pages', 1000),
                              ('max_response_bytes', MAX_RESPONSE_BYTES), ('max_batch_items', 1000)]:
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise QueryError('INVALID_DEPLOYMENT', 'Invalid query budget')
        if type(self.timeout_seconds) not in (int, float) or not 0 < self.timeout_seconds <= 300:
            raise QueryError('INVALID_DEPLOYMENT', 'Invalid timeout budget')


@dataclass(frozen=True)
class QueryCollection:
    """Explicit ordered-set collection, optionally keyed by record identities.

    Equal records deduplicate; different records with the same identity fail.
    Empty identity_paths means the complete JSON value is the identity.
    """
    path: tuple[str, ...]
    identity_paths: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class QueryOperation:
    """A reviewed transport name plus technical dependencies; never a URL."""
    id: str
    transport: str
    depends_on: tuple[str, ...] = ()
    batch_input: str | None = None
    batch_size: int = 100
    paginate: bool = False
    input_bindings: dict | None = None
    collections: tuple[QueryCollection, ...] = ()
    max_pages_per_batch: int | None = None
    max_batches: int | None = None


@dataclass(frozen=True)
class QueryCapability:
    id: str
    definition_sha256: str
    input_schema: dict
    output_schema: dict
    operations: tuple[QueryOperation, ...]
    subject_input: str | None
    optional_outputs: tuple[str, ...] = ()
    max_age_seconds: float = 300
    budget: QueryBudget = field(default_factory=QueryBudget)
    output_bindings: dict | None = None
    not_found_when: dict | None = None
    collections: tuple[QueryCollection, ...] = ()

    def plan_asset(self) -> dict:
        asset = {'capability_id': self.id, 'input_schema': self.input_schema,
                'output_schema': self.output_schema, 'subject_input': self.subject_input,
                'optional_outputs': list(self.optional_outputs), 'max_age_seconds': self.max_age_seconds,
                'operations': [{'id': op.id, 'transport': op.transport,
                                'depends_on': list(op.depends_on), 'batch_input': op.batch_input,
                                'batch_size': op.batch_size, 'paginate': op.paginate} for op in self.operations],
                'budget': vars(self.budget)}
        # Preserve the legacy digest when the registered extensions are unused.
        for op, item in zip(self.operations, asset['operations']):
            if op.input_bindings is not None:
                item['input_bindings'] = op.input_bindings
            if op.collections:
                item['collections'] = [_collection_asset(c) for c in op.collections]
            if op.max_pages_per_batch is not None:
                item['max_pages_per_batch'] = op.max_pages_per_batch
            if op.max_batches is not None:
                item['max_batches'] = op.max_batches
        if self.output_bindings is not None:
            asset['output_bindings'] = self.output_bindings
        if self.not_found_when is not None:
            asset['not_found_when'] = self.not_found_when
        if self.collections:
            asset['collections'] = [_collection_asset(c) for c in self.collections]
        return asset

    @property
    def query_plan_sha256(self) -> str:
        return digest(self.plan_asset())


@dataclass(frozen=True)
class QueryDeployment:
    """Trusted code only. authorize must recheck online activation and permission.

    transport(payload, timeout_seconds=remaining) returns a bounded page:
    {facts: {...}, subject_id, source_ref, observed_at, next_cursor?: str|null,
     partial?: bool}, as an object or one JSON object string. Raw strings retain
    exact byte accounting; object responses count their serialized JSON. Transports enforce their own I/O deadline, response byte
    limit, cancellation, safe endpoint policy, no redirects/proxies and no retry.
    """
    capabilities: Mapping[str, QueryCapability]
    transports: Mapping[str, Callable]
    operation_registry: dict
    authorize: Callable[[dict], bool]
    environment: str = 'TRUSTED_HOST'
    cancelled: Callable[[], bool] = lambda: False
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    monotonic: Callable[[], float] = time.monotonic

    @property
    def operation_registry_sha256(self) -> str:
        return digest(self.operation_registry)


# The SDK is intentionally unconnected. A host integration may inject a trusted
# deployment by calling execute_query directly; tool parameters cannot change it.
SDK_DEPLOYMENT: QueryDeployment | None = None


def _deny_schema_retrieval(uri):
    raise NoSuchResource(ref=uri)


_SCHEMA_REGISTRY = Registry(retrieve=_deny_schema_retrieval)
_SCHEMA_SINGLE = {'additionalProperties', 'unevaluatedProperties', 'propertyNames',
                  'items', 'contains', 'unevaluatedItems', 'not', 'if', 'then', 'else',
                  'contentSchema'}
_SCHEMA_ARRAY = {'allOf', 'anyOf', 'oneOf', 'prefixItems'}
_SCHEMA_MAP = {'properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'}


def validate_json_schema(schema: Any) -> None:
    """Validate Draft 2020-12 with no remote resource loading, even indirectly.

    Format is an annotation as in the default 2020-12 vocabulary. Schema refs
    may use only local fragments. Unknown keywords remain annotations under the
    standard; they are never executable configuration.
    """
    try:
        json_object({'schema': schema})
        Draft202012Validator.check_schema(schema)
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        root_resolver = _SCHEMA_REGISTRY.resolver_with_root(resource)
        pending = [(schema, 0, root_resolver)]
        visited = set()
        while pending:
            item, depth, resolver = pending.pop()
            marker = (id(item), resolver._base_uri)
            if marker in visited:
                continue
            visited.add(marker)
            if depth > 32:
                raise QueryError('INVALID_SCHEMA', 'Schema nesting exceeds the limit')
            if type(item) is bool:
                continue
            if type(item) is not dict:
                raise QueryError('INVALID_SCHEMA', 'Schema must be an object or boolean')
            if '$schema' in item and item['$schema'] not in (
                    'https://json-schema.org/draft/2020-12/schema',
                    'https://json-schema.org/draft/2020-12/schema#'):
                raise QueryError('INVALID_SCHEMA', 'Only Draft 2020-12 is supported')
            if 'nullable' in item and type(item['nullable']) is not bool:
                raise QueryError('INVALID_SCHEMA', 'Legacy nullable extension must be boolean')
            for keyword in ('$ref', '$dynamicRef', '$recursiveRef'):
                if keyword in item and (type(item[keyword]) is not str or not item[keyword].startswith('#')):
                    raise QueryError('INVALID_SCHEMA', 'Only local schema references are supported')
                if keyword in item:
                    try:
                        resolved = resolver.lookup(item[keyword])
                    except Exception:
                        raise QueryError('INVALID_SCHEMA', 'Local schema reference does not resolve') from None
                    if type(resolved.contents) not in (dict, bool):
                        raise QueryError('INVALID_SCHEMA', 'Reference target must be a schema')
                    pending.append((resolved.contents, depth + 1, resolved.resolver))
            def enqueue(child):
                subresource = Resource.from_contents(child, default_specification=DRAFT202012)
                pending.append((child, depth + 1, resolver.in_subresource(subresource)))
            for key in _SCHEMA_SINGLE & item.keys():
                enqueue(item[key])
            for key in _SCHEMA_ARRAY & item.keys():
                for child in item[key]:
                    enqueue(child)
            for key in _SCHEMA_MAP & item.keys():
                for child in item[key].values():
                    enqueue(child)
    except QueryError:
        raise
    except (SchemaError, ValueError, TypeError, RecursionError):
        raise QueryError('INVALID_SCHEMA', 'Invalid Draft 2020-12 schema') from None


def _validator(schema):
    # Bound recursive refs/combinators even when a schema never descends into
    # instance data. Shared closures carry the budget through validator.evolve.
    state = {'steps': 0, 'depth': 0}
    deadline = time.monotonic() + 1.0

    def tick():
        state['steps'] += 1
        if state['steps'] > 100000 or state['depth'] > 128 or time.monotonic() >= deadline:
            raise QueryError('QUERY_SCHEMA_BUDGET_EXCEEDED', 'Schema evaluation exceeds its budget')

    def matches(pattern, value):
        tick()
        try:
            return regex.search(pattern, value, timeout=min(0.05, max(0.001, deadline - time.monotonic()))) is not None
        except TimeoutError:
            raise QueryError('QUERY_SCHEMA_BUDGET_EXCEEDED', 'Schema pattern exceeds its budget') from None

    def bounded(original):
        def check(validator, constraint, instance, subschema):
            state['depth'] += 1
            try:
                tick()
                if instance is None and subschema.get('nullable') is True:
                    return
                yield from original(validator, constraint, instance, subschema)
            finally:
                state['depth'] -= 1
        return check

    def pattern(validator, constraint, instance, subschema):
        if type(instance) is str and not matches(constraint, instance):
            yield ValidationError('String does not satisfy pattern')

    def pattern_properties(validator, patterns, instance, subschema):
        if type(instance) is dict:
            for name, value in instance.items():
                for pattern, child in patterns.items():
                    if matches(pattern, name):
                        yield from validator.descend(value, child, path=name, schema_path=pattern)

    def additional_properties(validator, constraint, instance, subschema):
        if type(instance) is dict:
            for name, value in instance.items():
                tick()
                if name not in subschema.get('properties', {}) and not any(matches(p, name) for p in subschema.get('patternProperties', {})):
                    yield from validator.descend(value, constraint, path=name)

    def evaluated_keys(validator, instance, subschema, depth=0):
        tick()
        if depth > 128:
            raise QueryError('QUERY_SCHEMA_BUDGET_EXCEEDED', 'Schema annotation traversal exceeds its budget')
        if type(subschema) is bool:
            return set()
        keys = set(instance) & set(subschema.get('properties', {}))
        for keyword in ('$ref', '$dynamicRef'):
            if keyword in subschema:
                found = validator._resolver.lookup(subschema[keyword])
                keys |= evaluated_keys(validator.evolve(schema=found.contents, _resolver=found.resolver), instance, found.contents, depth + 1)
        for name, value in instance.items():
            for pattern in subschema.get('patternProperties', {}):
                if matches(pattern, name):
                    keys.add(name)
            for keyword in ('additionalProperties', 'unevaluatedProperties'):
                if keyword in subschema and validator.evolve(schema=subschema[keyword]).is_valid(value):
                    keys.add(name)
        for name, child in subschema.get('dependentSchemas', {}).items():
            if name in instance:
                keys |= evaluated_keys(validator, instance, child, depth + 1)
        for keyword in ('allOf', 'anyOf', 'oneOf'):
            for child in subschema.get(keyword, []):
                if validator.evolve(schema=child).is_valid(instance):
                    keys |= evaluated_keys(validator, instance, child, depth + 1)
        if 'if' in subschema:
            accepted = validator.evolve(schema=subschema['if']).is_valid(instance)
            if accepted:
                keys |= evaluated_keys(validator, instance, subschema['if'], depth + 1)
            branch = 'then' if accepted else 'else'
            if branch in subschema:
                keys |= evaluated_keys(validator, instance, subschema[branch], depth + 1)
        return keys

    def unevaluated_properties(validator, constraint, instance, subschema):
        if type(instance) is dict:
            for name in instance.keys() - evaluated_keys(validator, instance, subschema):
                yield from validator.descend(instance[name], constraint, path=name)

    def unique_items(validator, constraint, instance, subschema):
        if constraint and type(instance) is list:
            seen = set()
            for value in instance:
                tick()
                key = digest(value)
                if key in seen:
                    yield ValidationError('Array items are not unique')
                    return
                seen.add(key)

    entries = dict(Draft202012Validator.VALIDATORS)
    entries.update(pattern=pattern, patternProperties=pattern_properties,
                   additionalProperties=additional_properties, uniqueItems=unique_items,
                   unevaluatedProperties=unevaluated_properties)
    cls = validators.extend(Draft202012Validator, {key: bounded(value) for key, value in entries.items()})

    def check_dialect(value):
        if type(value) is dict and '$schema' in value and value['$schema'] not in (
                'https://json-schema.org/draft/2020-12/schema',
                'https://json-schema.org/draft/2020-12/schema#'):
            raise QueryError('INVALID_SCHEMA', 'Only Draft 2020-12 is supported')

    def evolve(self, **changes):
        # jsonschema's generated evolve() calls validator_for($schema), which
        # selects the stock class even for a nested declaration of this same
        # draft. Always retain this invocation's class AND budget closures.
        child = changes.pop('schema', self.schema)
        check_dialect(child)
        options = {'resolver': self._ref_resolver, 'format_checker': self.format_checker,
                   'registry': self._registry, '_resolver': self._resolver}
        options.update(changes)
        return cls(child, **options)

    cls.evolve = evolve
    check_dialect(schema)
    return cls(schema, registry=_SCHEMA_REGISTRY)


def validate_schema_value(value: Any, schema: Any) -> None:
    try:
        error = next(_validator(schema).iter_errors(value), None)
        if error is not None:
            raise QueryError('SCHEMA_MISMATCH', 'Query value does not satisfy its schema')
    except QueryError:
        raise
    except RecursionError:
        # Some Draft annotation helpers recurse outside keyword wrappers. The
        # interpreter's finite recursion guard is also a resource rejection,
        # never evidence that query data satisfied the registered schema.
        raise QueryError('QUERY_SCHEMA_BUDGET_EXCEEDED', 'Schema recursion exceeds its budget') from None
    except Exception:
        raise QueryError('INVALID_SCHEMA', 'Schema reference or validation failed') from None


def _validate_schema(schema, **_):
    validate_json_schema(schema)


def _schema(value, schema, *, partial=False):
    if partial and type(schema) is dict:
        schema = dict(schema)
        schema.pop('required', None)
    validate_schema_value(value, schema)


def _collection_asset(collection):
    return {'path': list(collection.path), 'identity_paths': [list(p) for p in collection.identity_paths]}


def _path_shape(path, *, empty=False):
    if type(path) not in (list, tuple) or not (0 if empty else 1) <= len(path) <= 16 or any(
            type(key) is not str or not key or key in _DANGEROUS for key in path):
        raise QueryError('INVALID_QUERY_PLAN', 'Invalid declared binding or collection path')


def _lookup(value, path):
    for key in path:
        if type(value) is dict:
            value = value.get(key, _MISSING)
        elif type(value) is list and key.isdecimal() and str(int(key)) == key and int(key) < len(value):
            value = value[int(key)]
        else:
            return _MISSING
    return value


def _validate_bindings(bindings, sources, *, operation_ids=()):
    if type(bindings) is not dict or len(bindings) > 128:
        raise QueryError('INVALID_QUERY_PLAN', 'Bindings must be a bounded mapping')
    for name, binding in bindings.items():
        if type(name) is not str or not name or name in _DANGEROUS or type(binding) is not dict:
            raise QueryError('INVALID_QUERY_PLAN', 'Invalid binding declaration')
        if binding.get('source_format', 'VALUE') not in ('VALUE', 'PARAMETER'):
            raise QueryError('INVALID_QUERY_PLAN', 'Invalid source format')
        selected = set(binding) - {'source_format'}
        if selected == {'literal'}:
            json_object({'value': binding['literal']})
            continue
        if selected != {'from'} or type(binding['from']) is not dict:
            raise QueryError('INVALID_QUERY_PLAN', 'Binding needs one literal or source')
        origin = binding['from']
        source = origin.get('source')
        if type(source) is not str or source not in sources or set(origin) != ({'source', 'path', 'node_id'} if source == 'api' else {'source', 'path'}):
            raise QueryError('INVALID_QUERY_PLAN', 'Invalid binding source')
        _path_shape(origin['path'], empty=True)
        if source == 'api' and (type(origin['node_id']) is not str or origin['node_id'] not in operation_ids):
            raise QueryError('INVALID_QUERY_PLAN', 'API binding must refer to a declared dependency')


def _bind(binding, inputs, prior, bind_context):
    if 'literal' in binding:
        return deepcopy(binding['literal'])
    origin = binding['from']
    if origin['source'] == 'api':
        data = prior.get(origin['node_id'], _MISSING)
        root = {'data': data} if data is not _MISSING else _MISSING
    else:
        root = inputs if origin['source'] == 'inputs' else bind_context
    value = _lookup(root, origin['path'])
    return _MISSING if value is _MISSING else deepcopy(value)


def _validate_collections(collections):
    if type(collections) is not tuple or len(collections) > 64:
        raise QueryError('INVALID_QUERY_PLAN', 'Collection policies must be a bounded tuple')
    paths = []
    for policy in collections:
        if not isinstance(policy, QueryCollection):
            raise QueryError('INVALID_QUERY_PLAN', 'Collection policy must be registered by trusted code')
        _path_shape(policy.path)
        if any(tuple(policy.path[:len(path)]) == path or tuple(path[:len(policy.path)]) == tuple(policy.path) for path in paths):
            raise QueryError('INVALID_QUERY_PLAN', 'Collection paths must be unique and nonoverlapping')
        paths.append(tuple(policy.path))
        if type(policy.identity_paths) is not tuple or len(policy.identity_paths) > 16:
            raise QueryError('INVALID_QUERY_PLAN', 'Invalid collection identity declaration')
        for path in policy.identity_paths:
            _path_shape(path)
        if len(set(tuple(p) for p in policy.identity_paths)) != len(policy.identity_paths):
            raise QueryError('INVALID_QUERY_PLAN', 'Duplicate collection identity path')


def _merge_facts(target, incoming, collections):
    policies = {tuple(p.path): p for p in collections}

    def merge(old, new, path):
        if path in policies:
            if type(new) is not list or (old is not _MISSING and type(old) is not list):
                raise QueryError('SCHEMA_MISMATCH', 'Declared collection must be an array')
            values, identities = [], {}
            for record in ([] if old is _MISSING else old) + new:
                keys = [_lookup(record, p) for p in policies[path].identity_paths]
                if any(key is _MISSING or key is None or type(key) in (dict, list) for key in keys):
                    raise QueryError('QUERY_COLLECTION_IDENTITY', 'Collection record has no valid scalar identity')
                identity = digest(keys if keys else record)
                record_digest = digest(record)
                if identity in identities:
                    if identities[identity] != record_digest:
                        raise QueryError('QUERY_FACT_CONFLICT', 'Collection identity has conflicting records')
                else:
                    identities[identity] = record_digest
                    values.append(deepcopy(record))
            return values
        nested = any(p[:len(path)] == path for p in policies)
        if type(new) is dict and nested and (old is _MISSING or type(old) is dict):
            result = {} if old is _MISSING else deepcopy(old)
            for key, value in new.items():
                result[key] = merge(result.get(key, _MISSING), value, path + (key,))
            return result
        if old is not _MISSING and digest(old) != digest(new):
            raise QueryError('QUERY_FACT_CONFLICT', 'Sources returned conflicting facts')
        return deepcopy(new)

    for key, value in incoming.items():
        target[key] = merge(target.get(key, _MISSING), value, (key,))


def _operation_order(operations: tuple[QueryOperation, ...]) -> list[QueryOperation]:
    if type(operations) is not tuple or any(not isinstance(op, QueryOperation) or type(op.id) is not str or not op.id or op.id in _DANGEROUS or
            type(op.transport) is not str or not op.transport or type(op.depends_on) is not tuple or
            any(type(dep) is not str or not dep for dep in op.depends_on) for op in operations):
        raise QueryError('INVALID_QUERY_PLAN', 'Operations must be fixed declarations')
    by_id = {op.id: op for op in operations}
    if not operations or len(operations) > 64 or len(by_id) != len(operations):
        raise QueryError('INVALID_QUERY_PLAN', 'Invalid operation identifiers or count')
    ordered = []
    complete = set()
    while len(ordered) < len(operations):
        ready = [op for op in operations if op.id not in complete and set(op.depends_on) <= complete]
        if not ready:
            raise QueryError('INVALID_QUERY_PLAN', 'Missing or cyclic operation dependency')
        for op in ready:
            if len(set(op.depends_on)) != len(op.depends_on):
                raise QueryError('INVALID_QUERY_PLAN', 'Duplicate dependency')
            ordered.append(op)
            complete.add(op.id)
    return ordered


@dataclass(frozen=True)
class CompiledQueryPlan:
    """Pure, trusted-registration result; never accepted as a tool parameter."""
    capability: QueryCapability
    operation_registry: dict
    plan_bytes: bytes
    registry_bytes: bytes
    plan_id: str
    operation_registry_ref: str

    @property
    def query_plan_bytes_sha256(self):
        return hashlib.sha256(self.plan_bytes).hexdigest()

    @property
    def operation_registry_bytes_sha256(self):
        return hashlib.sha256(self.registry_bytes).hexdigest()


def _asset_bytes(raw):
    if type(raw) is bytes:
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            raise QueryError('INVALID_JSON', 'Asset bytes must be UTF-8 JSON') from None
        return json_object(text), raw
    value = json_object(raw)
    # Native objects have no original byte representation. Use RFC8785 bytes
    # explicitly; callers with file locks must supply the original file bytes.
    return value, raw.encode('utf-8') if type(raw) is str else rfc8785.dumps(value)


def compile_query_plan(plan_raw, registry_raw, *, capability_id, definition_sha256,
                       input_schema, output_schema, subject_input, source_refs,
                       optional_outputs=(), operation_options=None, not_found_when=None,
                       max_response_bytes=MAX_RESPONSE_BYTES, max_age_seconds=300):
    """Compile public query-plan.v2 declarations during trusted host setup only.

    Transports, source identities and optional batch/collection settings are
    supplied separately by reviewed Python code. No endpoint, credential,
    module, registry path or operation implementation is loaded here.
    """
    plan, plan_bytes = _asset_bytes(plan_raw)
    registry, registry_bytes = _asset_bytes(registry_raw)
    required = {'schema_version', 'plan_id', 'example_only', 'read_only', 'budget',
                'nodes', 'outputs', 'operation_registry_ref'}
    if set(plan) != required or plan['schema_version'] != 'service-decision-dsl.query-plan.v2' or plan['read_only'] is not True or type(plan['example_only']) is not bool:
        raise QueryError('INVALID_QUERY_PLAN', 'Expected a fixed read-only query-plan.v2')
    for key in ('plan_id', 'operation_registry_ref'):
        if type(plan[key]) is not str or not plan[key]:
            raise QueryError('INVALID_QUERY_PLAN', 'Plan and registry identifiers must be nonempty')
    if set(registry) != {'schema_version', 'example_only', 'operations'} or registry['schema_version'] != 'service-decision-dsl.operation-registry.v2' or type(registry['example_only']) is not bool or type(registry['operations']) is not dict:
        raise QueryError('INVALID_DEPLOYMENT', 'Expected a static operation-registry.v2')
    budget = plan['budget']
    if type(budget) is not dict or set(budget) != {'max_calls', 'max_pages', 'max_concurrency', 'total_timeout_ms'} or any(type(v) is not int or v < 1 for v in budget.values()):
        raise QueryError('INVALID_QUERY_PLAN', 'Invalid declared technical budget')
    if budget['max_concurrency'] > 1000:
        raise QueryError('INVALID_QUERY_PLAN', 'Concurrency ceiling exceeds the supported limit')
    limits = QueryBudget(max_calls=budget['max_calls'], max_pages=budget['max_pages'],
                         timeout_seconds=budget['total_timeout_ms'] / 1000,
                         max_response_bytes=max_response_bytes)
    limits.validate()
    if type(plan['nodes']) is not list or not 1 <= len(plan['nodes']) <= 64:
        raise QueryError('INVALID_QUERY_PLAN', 'Plan needs a bounded declaration array')
    options = {} if operation_options is None else dict(operation_options)
    operations, descriptors = [], {}
    for node in plan['nodes']:
        if type(node) is not dict or set(node) != {'node_id', 'operation_ref', 'depends_on', 'input_bindings'} or type(node['depends_on']) is not list:
            raise QueryError('INVALID_QUERY_PLAN', 'Invalid technical operation declaration')
        opid, transport = node['node_id'], node['operation_ref']
        if type(opid) is not str or not opid or type(transport) is not str or not transport:
            raise QueryError('INVALID_QUERY_PLAN', 'Technical operation identifiers must be strings')
        descriptor = registry['operations'].get(transport)
        if type(descriptor) is not dict or not {'read_only', 'backend', 'input_schema', 'output_schema'} <= set(descriptor) <= {'read_only', 'backend', 'input_schema', 'output_schema', 'pagination', 'batch'} or descriptor['read_only'] is not True or type(descriptor['backend']) is not str or not descriptor['backend']:
            raise QueryError('INVALID_DEPLOYMENT', 'Operation needs reviewed read-only metadata and schemas')
        _validate_schema(descriptor['input_schema'])
        _validate_schema(descriptor['output_schema'])
        refs = source_refs.get(transport) if type(source_refs) is dict else None
        if type(refs) not in (list, tuple) or not refs or any(type(ref) is not str or not ref for ref in refs):
            raise QueryError('INVALID_DEPLOYMENT', 'Every operation needs trusted source registration')
        descriptors[transport] = {**deepcopy(descriptor), 'source_refs': list(refs)}
        settings = options.pop(opid, {})
        if type(settings) is not dict or set(settings) - {'batch_input', 'batch_size', 'paginate', 'collections', 'max_pages_per_batch', 'max_batches'}:
            raise QueryError('INVALID_QUERY_PLAN', 'Unknown trusted operation option')
        settings = dict(settings)
        defaults = {}
        if 'pagination' in descriptor:
            paging = descriptor['pagination']
            if type(paging) is not dict or set(paging) != {'parameter', 'items_key', 'max_pages'} or any(type(paging[k]) is not str or not paging[k] or paging[k] in _DANGEROUS for k in ('parameter', 'items_key')) or type(paging['max_pages']) is not int or not 1 <= paging['max_pages'] <= 1000:
                raise QueryError('INVALID_QUERY_PLAN', 'Invalid registered pagination policy')
            defaults.update(paginate=True, max_pages_per_batch=paging['max_pages'])
            if 'collections' not in settings:
                settings['collections'] = (QueryCollection((paging['items_key'],)),)
            elif (paging['items_key'],) not in [c.path for c in settings['collections']]:
                raise QueryError('INVALID_QUERY_PLAN', 'Collection policy must include the registered paged items')
        if 'batch' in descriptor:
            batch = descriptor['batch']
            if type(batch) is not dict or set(batch) != {'parameter', 'max_items', 'max_batches'} or type(batch['parameter']) is not str or not batch['parameter'] or batch['parameter'] in _DANGEROUS or any(type(batch[k]) is not int or not 1 <= batch[k] <= 1000 for k in ('max_items', 'max_batches')):
                raise QueryError('INVALID_QUERY_PLAN', 'Invalid registered batch policy')
            defaults.update(batch_input=batch['parameter'], batch_size=batch['max_items'], max_batches=batch['max_batches'])
        for key, value in defaults.items():
            if key in settings and settings[key] != value:
                raise QueryError('INVALID_QUERY_PLAN', 'Trusted options conflict with the locked operation policy')
            settings[key] = value
        operations.append(QueryOperation(opid, transport, tuple(node['depends_on']),
                          input_bindings=deepcopy(node['input_bindings']), **settings))
    if options:
        raise QueryError('INVALID_QUERY_PLAN', 'Options refer to an absent technical operation')
    ordered = _operation_order(tuple(operations))
    ancestors = {}
    for op in ordered:
        ancestors[op.id] = set(op.depends_on)
        for dep in op.depends_on:
            ancestors[op.id].update(ancestors[dep])
        _validate_bindings(op.input_bindings, {'inputs', 'api', 'context'}, operation_ids=ancestors[op.id])
        _validate_collections(op.collections)
    _validate_bindings(plan['outputs'], {'inputs', 'api', 'context'}, operation_ids=ancestors)
    _validate_schema(input_schema)
    _validate_schema(output_schema)
    _lock(definition_sha256)
    if type(capability_id) is not str or not capability_id or (subject_input is not None and (type(subject_input) is not str or not subject_input)):
        raise QueryError('INVALID_DEPLOYMENT', 'Capability and subject input must be registered')
    limits = replace(limits, max_batch_items=max([limits.max_batch_items] + [op.batch_size for op in operations]))
    limits.validate()
    capability = QueryCapability(capability_id, definition_sha256, deepcopy(input_schema),
                    deepcopy(output_schema), tuple(operations), subject_input,
                    optional_outputs=optional_outputs, max_age_seconds=max_age_seconds,
                    budget=limits, output_bindings=deepcopy(plan['outputs']), not_found_when=deepcopy(not_found_when))
    return CompiledQueryPlan(capability, descriptors, plan_bytes, registry_bytes,
                             plan['plan_id'], plan['operation_registry_ref'])


def execute_query(request: Any, *, deployment: QueryDeployment | None = None, binding_context: dict | None = None) -> dict:
    """Execute one pinned capability with trusted policy before *every* I/O call.

    Partial/ambiguous/expired results never become usable success outputs. No
    signature or caller-supplied digest can replace the authorization callback.
    """
    trace = {'calls': 0, 'pages': 0, 'response_bytes': 0, 'operations': [], 'source_refs': []}
    provenance = {'environment': 'UNCONFIGURED' if deployment is None else deployment.environment,
                  'mock': deployment is not None and deployment.environment == 'SYNTHETIC',
                  'authorization': 'NONE'}
    try:
        req = json_object(request)
        allowed = {'capability_id', 'definition_sha256', 'query_plan_sha256',
                   'operation_registry_sha256', 'inputs', 'context'}
        if set(req) != allowed:
            raise QueryError('INVALID_REQUEST', 'Request fields do not match the fixed query contract')
        if deployment is None:
            return _result('BLOCKED', 'QUERY_CONNECTION_NOT_CONFIGURED', trace=trace, provenance=provenance)
        if not callable(deployment.authorize) or not callable(deployment.cancelled):
            return _result('BLOCKED', 'QUERY_TRUSTED_HOST_REQUIRED', trace=trace, provenance=provenance)
        start = deployment.monotonic()
        if type(req['capability_id']) is not str or not req['capability_id']:
            raise QueryError('INVALID_REQUEST', 'Capability identifier must be a nonempty string')
        capability = deployment.capabilities.get(req['capability_id'])
        if capability is None:
            return _result('BLOCKED', 'QUERY_CAPABILITY_NOT_REGISTERED', trace=trace, provenance=provenance)
        # Snapshot registered assets so mutable caller inputs cannot alter execution.
        capability = deepcopy(capability)
        if capability.id != req['capability_id']:
            raise QueryError('INVALID_DEPLOYMENT', 'Registered capability identity differs from its registry key')
        registry = json_object(deployment.operation_registry)
        for name, actual in [('definition_sha256', capability.definition_sha256),
                             ('query_plan_sha256', capability.query_plan_sha256),
                             ('operation_registry_sha256', digest(registry))]:
            if _lock(req[name]) != _lock(actual):
                return _result('BLOCKED', 'QUERY_ASSET_LOCK_MISMATCH', trace=trace, provenance=provenance)
        capability.budget.validate()
        if type(capability.max_age_seconds) not in (int, float) or not 0 < capability.max_age_seconds <= 86400:
            raise QueryError('INVALID_DEPLOYMENT', 'Invalid observation age policy')
        inputs, context = req['inputs'], req['context']
        _validate_schema(capability.input_schema)
        _validate_schema(capability.output_schema)
        if type(capability.input_schema) is not dict or type(capability.output_schema) is not dict:
            raise QueryError('INVALID_SCHEMA', 'Capability root schemas must be objects')
        if type(inputs) is not dict:
            raise QueryError('SCHEMA_MISMATCH', 'Capability inputs must be an object')
        if type(capability.optional_outputs) is not tuple or any(type(k) is not str or not k for k in capability.optional_outputs) or len(set(capability.optional_outputs)) != len(capability.optional_outputs) or set(capability.optional_outputs) & set(capability.output_schema.get('required', [])):
            raise QueryError('INVALID_SCHEMA', 'Optional output registration is inconsistent')
        if capability.not_found_when is not None:
            json_object(capability.not_found_when)
            _schema(capability.not_found_when, capability.output_schema)
        _schema(inputs, capability.input_schema)
        if set(inputs) & {'url', 'endpoint', 'headers', 'credentials', 'module', 'code', 'proxy'}:
            raise QueryError('INVALID_PARAMETERS', 'Network configuration cannot be supplied as query input')
        if type(context) is not dict or set(context) != {'subject_id', 'run_id', 'activation_id', 'node_ref', 'selected_intent'}:
            raise QueryError('INVALID_CONTEXT', 'Host-bound identity context is required')
        if any(type(context[k]) is not str or not context[k] for k in ('subject_id', 'run_id', 'activation_id', 'node_ref')):
            raise QueryError('INVALID_CONTEXT', 'Identity fields must be non-empty strings')
        if capability.subject_input is not None and inputs.get(capability.subject_input, _MISSING) != context['subject_id']:
            return _result('BLOCKED', 'QUERY_SUBJECT_MISMATCH', trace=trace, provenance=provenance)
        bind_context = context if binding_context is None else json_object(binding_context)
        expected_intent = {'kind': 'QUERY', 'capability_id': capability.id, 'inputs_sha256': digest(inputs)}
        if context['selected_intent'] != expected_intent:
            return _result('BLOCKED', 'QUERY_INTENT_MISMATCH', trace=trace, provenance=provenance)
        operations = _operation_order(capability.operations)
        _validate_collections(capability.collections)
        if capability.output_bindings is not None:
            _validate_bindings(capability.output_bindings, {'inputs', 'api', 'context'}, operation_ids={op.id for op in operations})
            for name, binding in capability.output_bindings.items():
                if name not in capability.optional_outputs and binding.get('from', {}).get('source') != 'api' and _bind(binding, inputs, {}, bind_context) is _MISSING:
                    raise QueryError('QUERY_INPUT_UNAVAILABLE', 'A declared required output source is missing')
        ancestors = {}
        for op in operations:
            ancestors[op.id] = set(op.depends_on)
            for dep in op.depends_on:
                ancestors[op.id].update(ancestors[dep])
        transports = dict(deployment.transports)
        for op in operations:
            descriptor = registry.get(op.transport)
            if type(descriptor) is not dict or descriptor.get('read_only') is not True or not callable(transports.get(op.transport)):
                return _result('BLOCKED', 'QUERY_OPERATION_NOT_REGISTERED', trace=trace, provenance=provenance)
            sources = descriptor.get('source_refs')
            if type(sources) is not list or not sources or any(type(ref) is not str or not ref for ref in sources):
                raise QueryError('INVALID_DEPLOYMENT', 'Operations require registered source identities')
            transport = transports[op.transport]
            if isinstance(transport, FixedHttpReadTransport):
                if descriptor.get('transport_sha256') != digest(transport.asset):
                    raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Fixed transport asset is not pinned by the registry')
                if ('pagination' in descriptor and descriptor['pagination']['parameter'] != transport.cursor_parameter) or ('batch' in descriptor and descriptor['batch']['parameter'] != transport.batch_parameter):
                    raise QueryError('QUERY_ASSET_LOCK_MISMATCH', 'Transport parameters differ from the registered operation policy')
                if transport.environment == 'SYNTHETIC' and deployment.environment != 'SYNTHETIC':
                    raise QueryError('QUERY_ENVIRONMENT_MISMATCH', 'Synthetic transport requires synthetic deployment provenance')
            for name in ('input_schema', 'output_schema'):
                if name in descriptor:
                    _validate_schema(descriptor[name])
            _validate_collections(op.collections)
            if op.input_bindings is not None:
                _validate_bindings(op.input_bindings, {'inputs', 'api', 'context'}, operation_ids=ancestors[op.id])
                if set(op.input_bindings) & {'url', 'endpoint', 'headers', 'credentials', 'module', 'code', 'proxy'}:
                    raise QueryError('INVALID_QUERY_PLAN', 'Network configuration is not an operation input')
                if 'input_schema' not in descriptor or 'output_schema' not in descriptor:
                    raise QueryError('INVALID_DEPLOYMENT', 'Declared API bindings require registered input and output schemas')
                early = {key: _bind(binding, inputs, {}, bind_context) for key, binding in op.input_bindings.items()
                         if binding.get('from', {}).get('source') != 'api'}
                if any(value is _MISSING for value in early.values()):
                    raise QueryError('QUERY_INPUT_UNAVAILABLE', 'A declared query input is missing')
                json_object(early, limit=capability.budget.max_response_bytes)
                if len(early) == len(op.input_bindings) and op.batch_input is None:
                    _schema(early, descriptor['input_schema'])
            if op.max_pages_per_batch is not None and (not op.paginate or type(op.max_pages_per_batch) is not int or not 1 <= op.max_pages_per_batch <= 1000):
                raise QueryError('INVALID_QUERY_PLAN', 'Local page limit requires pagination and a positive bound')
            if op.max_batches is not None and (op.batch_input is None or type(op.max_batches) is not int or not 1 <= op.max_batches <= 1000):
                raise QueryError('INVALID_QUERY_PLAN', 'Local batch limit requires batching and a positive bound')
            if type(op.batch_size) is not int or not 1 <= op.batch_size <= capability.budget.max_batch_items:
                raise QueryError('INVALID_QUERY_PLAN', 'Invalid batch size')
            if type(op.paginate) is not bool:
                raise QueryError('INVALID_QUERY_PLAN', 'Invalid pagination flag')
            if op.batch_input is not None:
                if type(op.batch_input) is not str or not op.batch_input:
                    raise QueryError('INVALID_QUERY_PLAN', 'Batch input must name a registered operation input')
                if op.input_bindings is None and type(inputs.get(op.batch_input)) is not list:
                    raise QueryError('SCHEMA_MISMATCH', 'Batch input must be an array')
                if op.input_bindings is not None and op.batch_input not in op.input_bindings:
                    raise QueryError('INVALID_QUERY_PLAN', 'Batch field has no declared binding')
        merged, prior = {}, {}
        unavailable = set()
        trace['operation_statuses'] = {}
        partial = False
        observed = []
        observation_stamps = []

        def check_freshness(stamps):
            if not stamps:
                return
            try:
                now = deployment.now()
                if now.tzinfo is None or any(stamp.tzinfo is None or
                        not 0 <= (now - stamp).total_seconds() <= capability.max_age_seconds
                        for stamp in stamps):
                    raise ValueError
            except (TypeError, ValueError, AttributeError):
                raise QueryError('QUERY_STALE_RESPONSE', 'Response observation time is invalid, future or expired') from None

        def guard():
            if deployment.cancelled():
                raise QueryError('QUERY_CANCELLED', 'Query was cancelled')
            remaining = capability.budget.timeout_seconds - (deployment.monotonic() - start)
            if remaining <= 0:
                raise QueryError('QUERY_TIMEOUT', 'Query deadline exceeded')
            if deployment.authorize(deepcopy(req)) is not True:
                raise QueryError('QUERY_NOT_AUTHORIZED', 'Online host authorization rejected the query')
            provenance['authorization'] = 'TRUSTED_HOST_POLICY'
            # An online policy lookup can itself consume the deadline.
            remaining = capability.budget.timeout_seconds - (deployment.monotonic() - start)
            if remaining <= 0:
                raise QueryError('QUERY_TIMEOUT', 'Authorization consumed the query deadline')
            if deployment.cancelled():
                raise QueryError('QUERY_CANCELLED', 'Query was cancelled')
            # Earlier pages can expire while later I/O or online authorization
            # runs. Recheck every retained observation before another call and
            # again immediately before publishing the fully validated result.
            check_freshness(observation_stamps)
            return remaining

        guard()
        for op in operations:
            if set(op.depends_on) & unavailable:
                unavailable.add(op.id)
                trace['operation_statuses'][op.id] = 'BLOCKED_DEPENDENCY'
                trace['operations'].append(op.id)
                continue
            op_inputs = deepcopy(inputs) if op.input_bindings is None else {
                key: _bind(binding, inputs, prior, bind_context) for key, binding in op.input_bindings.items()}
            if any(value is _MISSING for value in op_inputs.values()):
                unavailable.add(op.id)
                trace['operation_statuses'][op.id] = 'BLOCKED_INPUT'
                trace['operations'].append(op.id)
                continue
            op_inputs = json_object(op_inputs, limit=capability.budget.max_response_bytes)
            descriptor = registry[op.transport]
            if 'input_schema' in descriptor and op.batch_input is None:
                _schema(op_inputs, descriptor['input_schema'])
            if op.batch_input is not None and type(op_inputs.get(op.batch_input)) is not list:
                raise QueryError('SCHEMA_MISMATCH', 'Bound batch input must be an array')
            op_facts, op_partial = {}, False
            batches = [None] if op.batch_input is None else [op_inputs[op.batch_input][i:i + op.batch_size] for i in range(0, len(op_inputs[op.batch_input]), op.batch_size)]
            # Empty batches perform no I/O; declared collections are known empty.
            if not batches:
                for policy in op.collections:
                    root = op_facts
                    for key in policy.path[:-1]:
                        root = root.setdefault(key, {})
                    root[policy.path[-1]] = []
            for batch_index, batch in enumerate(batches):
                if op.max_batches is not None and batch_index >= op.max_batches:
                    op_partial = True
                    break
                cursor, batch_pages = None, 0
                seen = set()
                while True:
                    if trace['calls'] >= capability.budget.max_calls or trace['pages'] >= capability.budget.max_pages:
                        raise QueryError('QUERY_BUDGET_EXCEEDED', 'Query call/page budget exhausted')
                    payload = {'inputs': deepcopy(op_inputs), 'dependencies': {key: deepcopy(prior[key]) for key in op.depends_on},
                               'cursor': cursor, 'batch': deepcopy(batch), 'subject_id': context['subject_id'],
                               'max_response_bytes': capability.budget.max_response_bytes - trace['response_bytes']}
                    if op.batch_input is not None:
                        payload['inputs'][op.batch_input] = deepcopy(batch)
                    if 'input_schema' in descriptor:
                        _schema(payload['inputs'], descriptor['input_schema'])
                    remaining = guard()
                    trace['calls'] += 1
                    page = transports[op.transport](payload, timeout_seconds=remaining)
                    guard()  # Reject late results, cancellation and revoked authority.
                    raw_page_bytes = len(page.encode('utf-8')) if type(page) is str else None
                    page = json_object(page, limit=capability.budget.max_response_bytes)
                    trace['pages'] += 1
                    batch_pages += 1
                    trace['response_bytes'] += raw_page_bytes if raw_page_bytes is not None else len(json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode())
                    if trace['response_bytes'] > capability.budget.max_response_bytes:
                        raise QueryError('QUERY_BUDGET_EXCEEDED', 'Response byte budget exhausted')
                    required = {'facts', 'subject_id', 'source_ref', 'observed_at'}
                    if not required <= set(page) or set(page) - (required | {'partial', 'next_cursor'}) or type(page['facts']) is not dict:
                        raise QueryError('INVALID_QUERY_RESPONSE', 'Invalid response envelope')
                    if page['subject_id'] != context['subject_id'] or type(page['source_ref']) is not str or page['source_ref'] not in descriptor['source_refs']:
                        raise QueryError('QUERY_SOURCE_MISMATCH', 'Response identity/source is missing or mismatched')
                    try:
                        stamp = datetime.fromisoformat(page['observed_at'].replace('Z', '+00:00'))
                    except (TypeError, ValueError, AttributeError):
                        raise QueryError('QUERY_STALE_RESPONSE', 'Response observation time is invalid, future or expired') from None
                    check_freshness([stamp])
                    observation_stamps.append(stamp)
                    if type(page.get('partial', False)) is not bool:
                        raise QueryError('INVALID_QUERY_RESPONSE', 'Partial marker must be a boolean')
                    op_partial |= page.get('partial', False)
                    # The schema describes the complete operation aggregate, not
                    # an individual page slice (e.g. minItems across all pages).
                    _merge_facts(op_facts, page['facts'], op.collections or capability.collections)
                    trace['source_refs'].append(page['source_ref'])
                    observed.append(page['observed_at'])
                    cursor = page.get('next_cursor')
                    if cursor is None:
                        break
                    if not op.paginate or type(cursor) is not str or not cursor or cursor in seen or len(cursor) > 4096:
                        raise QueryError('QUERY_CURSOR_INVALID', 'Unexpected, repeated or invalid cursor')
                    seen.add(cursor)
                    if op.max_pages_per_batch is not None and batch_pages >= op.max_pages_per_batch:
                        op_partial = True
                        break
            if 'output_schema' in descriptor:
                _schema(op_facts, descriptor['output_schema'], partial=op_partial)
            elif not op_partial:
                _schema(op_facts, capability.output_schema, partial=True)
            trace['operations'].append(op.id)
            trace['operation_statuses'][op.id] = 'PARTIAL' if op_partial else 'SUCCEEDED'
            if op_partial:
                unavailable.add(op.id)
                partial = True
            else:
                prior[op.id] = op_facts
                if capability.output_bindings is None:
                    _merge_facts(merged, op_facts, capability.collections)
        if capability.output_bindings is not None:
            partial |= bool(unavailable)
            for name, binding in capability.output_bindings.items():
                value = _bind(binding, inputs, prior, bind_context)
                if value is not _MISSING:
                    merged[name] = value
                    json_object(merged, limit=capability.budget.max_response_bytes)
                elif name not in capability.optional_outputs:
                    partial = True
        elif unavailable:
            partial = True
        guard()
        missing = set(capability.output_schema.get('required', [])) - set(merged)
        optional_missing = sorted(set(capability.optional_outputs) - set(merged))
        trace.update(observed_at=observed, unknown_outputs=optional_missing,
                     partial=partial, facts_retained=False)
        if missing or (partial and (capability.output_bindings is None or any(name not in merged and name not in capability.optional_outputs for name in capability.output_bindings))):
            return _result('UNKNOWN', 'QUERY_PARTIAL_RESULT', trace=trace, provenance=provenance)
        _schema(merged, capability.output_schema)
        result = json_object(_result('SUCCEEDED', 'OK', outputs=merged, trace=trace, provenance=provenance), limit=MAX_RESPONSE_BYTES)
        guard()
        return result
    except QueryError as exc:
        status = {'QUERY_CANCELLED': 'CANCELLED', 'QUERY_NOT_AUTHORIZED': 'BLOCKED',
                  'QUERY_TIMEOUT': 'UNKNOWN', 'QUERY_BUDGET_EXCEEDED': 'UNKNOWN',
                  'QUERY_ASSET_LOCK_MISMATCH': 'BLOCKED', 'QUERY_ENVIRONMENT_MISMATCH': 'BLOCKED',
                  'QUERY_STALE_RESPONSE': 'UNKNOWN', 'QUERY_INPUT_UNAVAILABLE': 'BLOCKED',
                  'QUERY_SCHEMA_BUDGET_EXCEEDED': 'UNKNOWN'}.get(exc.code, 'FAILED')
        return _result(status, exc.code, trace=trace, provenance=provenance)
    except TimeoutError:
        return _result('UNKNOWN', 'QUERY_TIMEOUT', trace=trace, provenance=provenance)
    except Exception:
        # Do not leak transport exceptions, secrets, input values or stale facts.
        return _result('FAILED', 'QUERY_ADAPTER_ERROR', trace=trace, provenance=provenance)


@dataclass(frozen=True)
class FixedHttpReadTransport:
    """Optional fixed GET/read-only POST adapter, built by trusted host code only.

    Real endpoints require HTTPS + globally routable literal IP + certificate
    verification. Plain HTTP is allowed only for explicit SYNTHETIC loopback.
    Static headers are host-only; their values are never placed in an asset or
    trace. No ambient credentials or dynamic headers are loaded. This narrow
    transport is not a general business-API client. A watchdog shuts down the
    socket on total-deadline expiry or trusted cancellation, including slow
    response headers/body; failed calls are never retried.
    """
    url: str
    input_fields: tuple[str, ...] = ()
    batch_parameter: str | None = None
    cursor_parameter: str = 'cursor'
    environment: str = 'TRUSTED_HOST'
    cancelled: Callable[[], bool] = lambda: False
    method: str = 'GET'
    post_read_only: bool = False
    headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        self._endpoint()
        if self.method not in ('GET', 'POST') or type(self.post_read_only) is not bool or (self.method == 'POST' and not self.post_read_only):
            raise QueryError('INVALID_DEPLOYMENT', 'Only GET or explicitly reviewed read-only POST is supported')
        if type(self.headers) is not tuple or len(self.headers) > 32:
            raise QueryError('INVALID_DEPLOYMENT', 'Headers must be statically registered')
        header_names, header_bytes = set(), 0
        for item in self.headers:
            if type(item) is not tuple or len(item) != 2:
                raise QueryError('INVALID_DEPLOYMENT', 'Invalid static header declaration')
            name, value = item
            if type(name) is not str or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or type(value) is not str:
                raise QueryError('INVALID_DEPLOYMENT', 'Invalid static header')
            key = name.lower()
            if key in header_names or key in {'host', 'content-length', 'transfer-encoding', 'connection', 'upgrade', 'te', 'trailer', 'accept', 'content-type', 'accept-encoding'} or key.startswith('proxy-') or any(ord(ch) < 32 or ord(ch) > 126 for ch in value):
                raise QueryError('INVALID_DEPLOYMENT', 'Static header cannot override network or protocol controls')
            header_names.add(key)
            header_bytes += len(name) + len(value)
        if header_bytes > 16384:
            raise QueryError('INVALID_DEPLOYMENT', 'Static headers exceed their budget')
        names = list(self.input_fields) + [self.cursor_parameter]
        if self.batch_parameter is not None:
            names.append(self.batch_parameter)
        if any(type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name) for name in names) or len(set(names)) != len(names):
            raise QueryError('INVALID_DEPLOYMENT', 'Transport parameter names must be distinct static identifiers')

    def _endpoint(self):
        try:
            parsed = urlsplit(self.url)
            if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or '%' in (parsed.hostname or ''):
                raise ValueError
            address = ipaddress.ip_address(parsed.hostname or '')
            # is_global alone includes multicast on supported Python versions.
            # Require unicast public destinations; only synthetic loopback is an exception.
            if address.is_multicast or address.is_unspecified:
                raise ValueError
            public_unicast = address.is_global and not (
                address.is_reserved or address.is_private or address.is_link_local
                or address.is_loopback or getattr(address, 'is_site_local', False))
            synthetic = self.environment == 'SYNTHETIC' and address.is_loopback
            if not ((parsed.scheme == 'https' and public_unicast) or (parsed.scheme in {'http', 'https'} and synthetic)):
                raise ValueError
            port = parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)
            if not 1 <= port <= 65535 or not parsed.path.startswith('/') or any(ord(c) < 32 or ord(c) == 127 for c in self.url):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise QueryError('QUERY_ENDPOINT_REJECTED', 'Endpoint must be fixed HTTPS literal public IP or explicit SYNTHETIC loopback') from None
        return parsed, address, port

    @property
    def asset(self):
        asset = {'kind': 'fixed-literal-ip-get-v1', 'url': self.url, 'input_fields': list(self.input_fields),
                 'batch_parameter': self.batch_parameter, 'cursor_parameter': self.cursor_parameter,
                 'environment': self.environment}
        if self.method != 'GET' or self.headers:
            asset.update(kind='fixed-literal-ip-read-v2', method=self.method,
                         post_read_only=self.post_read_only,
                         headers_sha256=digest([list(h) for h in self.headers]))
        return asset

    def __call__(self, payload: dict, *, timeout_seconds: float) -> str:
        parsed, address, port = self._endpoint()
        maximum = payload['max_response_bytes']
        if type(maximum) is not int or not 0 < maximum <= MAX_RESPONSE_BYTES:
            raise QueryError('QUERY_BUDGET_EXCEEDED', 'No response byte budget remains')
        if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 300:
            raise QueryError('QUERY_TIMEOUT', 'No valid deadline remains')
        try:
            initially_cancelled = self.cancelled()
        except Exception:
            raise QueryError('QUERY_ADAPTER_ERROR', 'Cancellation policy failed') from None
        if initially_cancelled:
            raise QueryError('QUERY_CANCELLED', 'Transport was cancelled')
        parameters, body_values = [], {}
        for key in self.input_fields:
            if key not in payload['inputs']:
                continue
            value = payload['inputs'][key]
            if self.method == 'GET':
                if type(value) not in (str, int, float, bool) and value is not None:
                    raise QueryError('INVALID_PARAMETERS', 'GET parameters must be scalar JSON values')
                parameters.append((key, value if type(value) is str else json.dumps(value)))
            else:
                body_values[key] = deepcopy(value)
        if payload['cursor'] is not None:
            parameters.append((self.cursor_parameter, payload['cursor']))
            body_values[self.cursor_parameter] = payload['cursor']
        if payload['batch'] is not None:
            if self.batch_parameter is None:
                raise QueryError('INVALID_QUERY_PLAN', 'HTTP batch parameter is not registered')
            parameters.append((self.batch_parameter, json.dumps(payload['batch'], separators=(',', ':'))))
            body_values[self.batch_parameter] = deepcopy(payload['batch'])
        body = None
        headers = {'Accept': 'application/json', **dict(self.headers)}
        if self.method == 'POST':
            body_values = json_object(body_values)
            body = json.dumps(body_values, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        target = parsed.path + ('?' + urlencode(parameters) if parameters and self.method == 'GET' else '')
        if len(target.encode('utf-8')) > 16384:
            raise QueryError('QUERY_BUDGET_EXCEEDED', 'Encoded request URL exceeds the safe limit')
        connection = http.client.HTTPConnection(str(address), port=port, timeout=timeout_seconds)
        raw = socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(timeout_seconds)
        active = [raw]
        done = threading.Event()
        halted = []
        deadline = time.monotonic() + timeout_seconds

        def watchdog():
            while not done.is_set():
                remaining = deadline - time.monotonic()
                try:
                    cancellation = self.cancelled()
                except Exception:
                    reason = 'QUERY_ADAPTER_ERROR'
                else:
                    reason = 'QUERY_CANCELLED' if cancellation else 'QUERY_TIMEOUT' if remaining <= 0 else None
                if reason is not None:
                    halted.append(reason)
                    try:
                        active[0].shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    active[0].close()
                    return
                done.wait(min(remaining, 0.02))

        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        try:
            # Direct numeric connect avoids DNS and ambient proxy settings.
            raw.connect((str(address), port))
            if parsed.scheme == 'https':
                active[0] = ssl.create_default_context().wrap_socket(
                    raw, server_hostname=str(address), do_handshake_on_connect=False)
                active[0].settimeout(max(0.001, deadline - time.monotonic()))
                active[0].do_handshake()
            connection.sock = active[0]
            connection.request(self.method, target, body=body, headers=headers)
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise QueryError('QUERY_REDIRECT_REJECTED', 'Redirects are never followed')
            if response.status != 200:
                raise QueryError('QUERY_HTTP_STATUS', 'Endpoint did not return successful JSON')
            content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
            if content_type != 'application/json' or response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                raise QueryError('QUERY_CONTENT_TYPE', 'Only uncompressed application/json responses are accepted')
            content_length = response.getheader('Content-Length')
            if content_length is not None and (not content_length.isdecimal() or int(content_length) > maximum):
                raise QueryError('QUERY_BUDGET_EXCEEDED', 'Response Content-Length exceeds the budget')
            data = response.read(maximum + 1)
            if len(data) > maximum:
                raise QueryError('QUERY_BUDGET_EXCEEDED', 'Response body exceeds the budget')
            if halted or time.monotonic() >= deadline:
                raise QueryError(halted[0] if halted else 'QUERY_TIMEOUT', 'Transport deadline or cancellation stopped the response')
            try:
                decoded = data.decode('utf-8')
                json_object(decoded, limit=maximum)
                return decoded  # Preserve raw byte accounting across pages.
            except UnicodeDecodeError:
                raise QueryError('INVALID_QUERY_RESPONSE', 'Response is not valid UTF-8 JSON') from None
        except (OSError, http.client.HTTPException):
            if halted:
                raise QueryError(halted[0], 'Transport stopped by deadline or cancellation') from None
            if time.monotonic() >= deadline:
                raise QueryError('QUERY_TIMEOUT', 'Transport deadline exceeded') from None
            raise QueryError('QUERY_TRANSPORT_ERROR', 'Fixed HTTP transport failed') from None
        finally:
            done.set()
            connection.close()
            active[0].close()
            thread.join(timeout=0.1)
