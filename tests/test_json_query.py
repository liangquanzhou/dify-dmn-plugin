"""Independent synthetic vectors, never executed against business systems."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from json_query import (QueryBudget, QueryCapability, QueryDeployment, QueryError,
                        QueryOperation, digest, execute_query, json_object, query_local)

NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


def setup_query(**overrides):
    calls = []
    capability = QueryCapability('test.read', 'a' * 64,
        {'type': 'object', 'properties': {'subject_id': {'type': 'string'}, 'ids': {'type': 'array', 'items': {'type': 'string'}}},
         'required': ['subject_id'], 'additionalProperties': False},
        {'type': 'object', 'properties': {'state': {'type': 'string'}, 'hint': {'type': 'string'}},
         'required': ['state'], 'additionalProperties': False},
        (QueryOperation('read', 'fixed-read'),), 'subject_id', optional_outputs=('hint',))
    capability = replace(capability, **overrides)

    def transport(payload, timeout_seconds):
        calls.append(deepcopy(payload))
        return page()
    deployment = QueryDeployment({'test.read': capability}, {'fixed-read': transport},
                                 {'fixed-read': {'read_only': True, 'version': '1', 'source_refs': ['synthetic-source']}},
                                 lambda req: True, environment='SYNTHETIC', now=lambda: NOW)
    inputs = {'subject_id': 'SYNTHETIC-1'}
    request = {'capability_id': 'test.read', 'definition_sha256': capability.definition_sha256,
               'query_plan_sha256': capability.query_plan_sha256,
               'operation_registry_sha256': deployment.operation_registry_sha256,
               'inputs': inputs, 'context': {'subject_id': 'SYNTHETIC-1', 'run_id': 'run-1',
               'activation_id': 'activation-1', 'node_ref': 'LOCATE/read',
               'selected_intent': {'kind': 'QUERY', 'capability_id': 'test.read', 'inputs_sha256': digest(inputs)}}}
    return request, deployment, calls


def page(**changes):
    value = {'subject_id': 'SYNTHETIC-1', 'source_ref': 'synthetic-source',
             'observed_at': NOW.isoformat(), 'facts': {'state': 'READY'}}
    value.update(changes)
    return value


def code(result):
    return result['diagnostics'][0]['code']


@pytest.mark.parametrize('capability,key,prefix', [('demo.ticket_lookup', 'ticket_id', 'T'), ('demo.order_lookup', 'order_id', 'O')])
@pytest.mark.parametrize('suffix,status,outcome', [('100', 'SUCCEEDED', 'FOUND'), ('MISSING', 'SUCCEEDED', 'NOT_FOUND'),
    ('UNKNOWN', 'WAITING_INPUT', 'UNKNOWN'), ('TIMEOUT', 'FAILED', 'TIMEOUT'), ('ERROR', 'FAILED', 'ERROR')])
def test_synthetic_outcomes(capability, key, prefix, suffix, status, outcome):
    result = query_local({'capability_id': capability, 'parameters': {key: prefix + '-' + suffix}})
    assert (result['status'], result['outcome']) == (status, outcome)
    assert result['provenance']['mock'] is True
    assert result['provenance']['environment'] == 'SYNTHETIC'
    assert result['provenance']['advisory_only'] is True
    if outcome != 'FOUND':
        assert result['outputs'] is None


@pytest.mark.parametrize('value', [None, ''])
def test_missing_local_identifier_waits(value):
    assert query_local({'capability_id': 'demo.ticket_lookup', 'parameters': {'ticket_id': value}})['status'] == 'WAITING_INPUT'


@pytest.mark.parametrize('raw_request', [None, [], '"{}"', '{"capability_id":"x","capability_id":"y"}',
    {'capability_id': [], 'parameters': {}}, {'capability_id': 'demo.ticket_lookup', 'parameters': {'url': 'https://example.invalid'}},
    {'capability_id': 'demo.ticket_lookup', 'parameters': {'ticket_id': True}},
    {'capability_id': 'unknown', 'parameters': {}}])
def test_local_invalid_inputs_fail(raw_request):
    result = query_local(raw_request)
    assert result['status'] == 'FAILED'
    assert result['outputs'] is None


@pytest.mark.parametrize('raw', [{'__proto__': {}}, {'x': float('nan')}, {'x': 2**53}, {'x': '\ud800'}, '{"x":1,"x":2}', '"{}"'])
def test_strict_json_boundary(raw):
    with pytest.raises(QueryError):
        json_object(raw)


def test_cycle_and_depth_are_rejected():
    value = {}
    value['x'] = value
    with pytest.raises(QueryError):
        json_object(value)
    value = {}
    for _ in range(66):
        value = {'x': value}
    with pytest.raises(QueryError):
        json_object(value)


def test_no_deployment_never_falls_back_to_fixture():
    request, _, calls = setup_query()
    result = execute_query(request)
    assert result['execution_status'] == 'BLOCKED'
    assert code(result) == 'QUERY_CONNECTION_NOT_CONFIGURED'
    assert calls == [] and result['outputs'] is None
    assert result['provenance']['mock'] is False


def test_registered_query_success_and_optional_unknown():
    request, deployment, calls = setup_query()
    result = execute_query(request, deployment=deployment)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['outputs'] == {'state': 'READY'}
    assert result['trace']['unknown_outputs'] == ['hint']
    assert len(calls) == 1
    assert result['provenance']['authorization'] == 'TRUSTED_HOST_POLICY'


@pytest.mark.parametrize('key', ['definition_sha256', 'query_plan_sha256', 'operation_registry_sha256'])
def test_each_asset_lock_is_checked_before_io(key):
    request, deployment, calls = setup_query()
    request[key] = 'b' * 64
    assert code(execute_query(request, deployment=deployment)) == 'QUERY_ASSET_LOCK_MISMATCH'
    assert calls == []


@pytest.mark.parametrize('change,expected', [
    (lambda r: r['inputs'].update(url='https://example.invalid'), 'SCHEMA_MISMATCH'),
    (lambda r: r['inputs'].update(subject_id=True), 'SCHEMA_MISMATCH'),
    (lambda r: r['context'].update(subject_id='another'), 'QUERY_SUBJECT_MISMATCH'),
    (lambda r: r['context']['selected_intent'].update(kind='BUSINESS'), 'QUERY_INTENT_MISMATCH'),
    (lambda r: r['context'].update(activation_id=''), 'INVALID_CONTEXT'),
    (lambda r: r.update(headers={}), 'INVALID_REQUEST'),
])
def test_identity_schema_intent_network_rejection_precedes_io(change, expected):
    request, deployment, calls = setup_query()
    change(request)
    assert code(execute_query(request, deployment=deployment)) == expected
    assert calls == []


def test_online_policy_denial_and_revocation():
    request, deployment, calls = setup_query()
    denied = replace(deployment, authorize=lambda req: False)
    assert code(execute_query(request, deployment=denied)) == 'QUERY_NOT_AUTHORIZED'
    assert calls == []
    approvals = iter([True, True, False])
    revoked = replace(deployment, authorize=lambda req: next(approvals))
    result = execute_query(request, deployment=revoked)
    assert code(result) == 'QUERY_NOT_AUTHORIZED'
    assert result['outputs'] is None and len(calls) == 1


def test_policy_must_return_literal_true():
    request, deployment, calls = setup_query()
    assert code(execute_query(request, deployment=replace(deployment, authorize=lambda req: 1))) == 'QUERY_NOT_AUTHORIZED'
    assert calls == []


@pytest.mark.parametrize('guard_number', [4, 5])
@pytest.mark.parametrize('age', [2, -1])
def test_observations_remain_fresh_through_final_authorization(guard_number, age):
    request, deployment, calls = setup_query(max_age_seconds=1)
    clock, checks = [NOW], []

    def authorize(_):
        checks.append(True)
        if len(checks) == guard_number:
            clock[0] = NOW + timedelta(seconds=age)
        return True

    result = execute_query(request, deployment=replace(deployment, authorize=authorize, now=lambda: clock[0]))
    assert result['execution_status'] == 'UNKNOWN'
    assert code(result) == 'QUERY_STALE_RESPONSE'
    assert result['outputs'] is None and len(calls) == 1
    assert len(checks) == guard_number


@pytest.mark.parametrize('mode', ['pages', 'operations'])
def test_fresh_last_response_cannot_hide_expired_earlier_observation(mode):
    operations = ((QueryOperation('read', 'fixed-read', paginate=True),) if mode == 'pages' else
                  (QueryOperation('first', 'fixed-read'), QueryOperation('second', 'fixed-read')))
    request, deployment, calls = setup_query(max_age_seconds=1, operations=operations)
    clock = [NOW]

    def transport(payload, timeout_seconds):
        calls.append(payload)
        if len(calls) == 1:
            return page(**({'next_cursor': 'next'} if mode == 'pages' else {}))
        clock[0] = NOW + timedelta(seconds=2)
        return page(observed_at=clock[0].isoformat())

    result = execute_query(request, deployment=replace(deployment,
        transports={'fixed-read': transport}, now=lambda: clock[0]))
    assert len(calls) == 2
    assert result['execution_status'] == 'UNKNOWN'
    assert code(result) == 'QUERY_STALE_RESPONSE' and result['outputs'] is None


@pytest.mark.parametrize('capability,expected', [
    ({'operations': (QueryOperation('read', 'fixed-read', ('missing',)),)}, 'INVALID_QUERY_PLAN'),
    ({'operations': (QueryOperation('read', 'fixed-read', ('read',)),)}, 'INVALID_QUERY_PLAN'),
    ({'operations': (QueryOperation('read', 'missing'),)}, 'QUERY_OPERATION_NOT_REGISTERED'),
    ({'output_schema': {'type': 'object', 'pattern': '['}}, 'INVALID_SCHEMA'),
    ({'output_schema': {'type': 'object', 'properties': {'state': {'type': 'imaginary'}}}}, 'INVALID_SCHEMA'),
    ({'budget': QueryBudget(max_calls=0)}, 'INVALID_DEPLOYMENT'),
])
def test_registered_assets_are_preflighted(capability, expected):
    request, deployment, calls = setup_query(**capability)
    assert code(execute_query(request, deployment=deployment)) == expected
    assert calls == []


@pytest.mark.parametrize('response,expected,status', [
    (page(subject_id='other'), 'QUERY_SOURCE_MISMATCH', 'FAILED'),
    (page(source_ref=''), 'QUERY_SOURCE_MISMATCH', 'FAILED'),
    (page(observed_at=(NOW - timedelta(seconds=301)).isoformat()), 'QUERY_STALE_RESPONSE', 'UNKNOWN'),
    (page(observed_at=(NOW + timedelta(seconds=1)).isoformat()), 'QUERY_STALE_RESPONSE', 'UNKNOWN'),
    (page(observed_at='2026-10-09T12:00:00'), 'QUERY_STALE_RESPONSE', 'UNKNOWN'),
    (page(partial=True), 'QUERY_PARTIAL_RESULT', 'UNKNOWN'),
    (page(facts={}), 'QUERY_PARTIAL_RESULT', 'UNKNOWN'),
    (page(facts={'state': 2}), 'SCHEMA_MISMATCH', 'FAILED'),
    (page(next_cursor='unexpected'), 'QUERY_CURSOR_INVALID', 'FAILED'),
])
def test_untrustworthy_or_partial_responses_never_publish_facts(response, expected, status):
    request, deployment, _ = setup_query()
    deployment = replace(deployment, transports={'fixed-read': lambda *a, **k: response})
    result = execute_query(request, deployment=deployment)
    assert code(result) == expected and result['execution_status'] == status
    assert result['outputs'] is None


def test_pagination_is_bounded_and_detects_repeated_cursor():
    request, deployment, _ = setup_query(operations=(QueryOperation('read', 'fixed-read', paginate=True),))
    pages = iter([page(next_cursor='next'), page(next_cursor='next')])
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': lambda *a, **k: next(pages)}))
    assert code(result) == 'QUERY_CURSOR_INVALID'
    assert result['trace']['calls'] == 2
    request, deployment, _ = setup_query(operations=(QueryOperation('read', 'fixed-read', paginate=True),), budget=QueryBudget(max_pages=1))
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': lambda *a, **k: page(next_cursor='next')}))
    assert code(result) == 'QUERY_BUDGET_EXCEEDED' and result['trace']['calls'] == 1
    assert result['outputs'] is None


def test_paginated_success_and_fact_conflict():
    request, deployment, _ = setup_query(operations=(QueryOperation('read', 'fixed-read', paginate=True),))
    for final, expected in [(page(facts={'hint': 'CHECK'}), 'SUCCEEDED'), (page(facts={'state': 'DIFFERENT'}), 'FAILED')]:
        pages = iter([page(next_cursor='next'), final])
        result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': lambda *a, **k: next(pages)}))
        assert result['execution_status'] == expected
        if expected == 'SUCCEEDED':
            assert result['outputs'] == {'state': 'READY', 'hint': 'CHECK'}
        else:
            assert code(result) == 'QUERY_FACT_CONFLICT' and result['outputs'] is None


def test_batches_reset_cursor_and_follow_dependencies():
    ops = (QueryOperation('second', 'fixed-read', ('first',), 'ids', 2, True), QueryOperation('first', 'fixed-read'))
    request, deployment, calls = setup_query(operations=ops)
    request['inputs']['ids'] = ['a', 'b', 'c']
    request['context']['selected_intent']['inputs_sha256'] = digest(request['inputs'])
    result = execute_query(request, deployment=deployment)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['trace']['operations'] == ['first', 'second']
    assert [c['batch'] for c in calls] == [None, ['a', 'b'], ['c']]
    assert calls[1]['dependencies'] == {'first': {'state': 'READY'}}
    assert calls[2]['cursor'] is None


def test_cancellation_timeout_and_transport_failure_no_retry():
    request, deployment, calls = setup_query()
    assert execute_query(request, deployment=replace(deployment, cancelled=lambda: True))['execution_status'] == 'CANCELLED'
    assert calls == []
    ticks = iter([0, 0, 0, 0, 0, 11])
    assert code(execute_query(request, deployment=replace(deployment, monotonic=lambda: next(ticks)))) == 'QUERY_TIMEOUT'
    assert len(calls) == 1
    count = []
    def broken(*args, **kwargs):
        count.append(1)
        raise RuntimeError('PRIVATE TOKEN MUST NOT LEAK')
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': broken}))
    assert count == [1] and result['outputs'] is None
    assert 'PRIVATE' not in json.dumps(result)


def test_response_size_failure_clears_outputs():
    request, deployment, _ = setup_query(budget=QueryBudget(max_response_bytes=100))
    result = execute_query(request, deployment=deployment)
    assert result['execution_status'] == 'FAILED'
    assert result['outputs'] is None


def test_sdk_real_wrappers_match_pure_results():
    from tools.query_local import QueryLocalTool
    from tools.execute_query import ExecuteQueryTool
    params = {'capability_id': 'demo.ticket_lookup', 'parameters': {'ticket_id': 'T-100'}}
    local = list(QueryLocalTool.from_credentials({})._invoke({'request_json': json.dumps(params)}))
    assert local[-1].message.json_object == query_local(params)
    request, _, _ = setup_query()
    messages = list(ExecuteQueryTool.from_credentials({})._invoke({'request_json': request}))
    assert messages[-1].message.json_object['execution_status'] == 'BLOCKED'
    assert len(messages) == 7


@pytest.mark.parametrize('url,environment', [
    ('http://8.8.8.8/read', 'TRUSTED_HOST'), ('https://example.invalid/read', 'TRUSTED_HOST'),
    ('https://127.0.0.1/read', 'TRUSTED_HOST'), ('https://10.1.2.3/read', 'TRUSTED_HOST'),
    ('http://169.254.169.254/latest', 'SYNTHETIC'), ('http://127.0.0.1/read?url=x', 'SYNTHETIC'),
    ('http://user:pass@127.0.0.1/read', 'SYNTHETIC'), ('http://[::1%25lo]/read', 'SYNTHETIC'),
    ('ftp://127.0.0.1/read', 'SYNTHETIC'), ('https://[fc00::1]/read', 'TRUSTED_HOST'),
])
def test_fixed_transport_rejects_ssrf_destinations_and_dynamic_configuration(url, environment):
    from json_query import FixedHttpReadTransport
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(url, environment=environment)
    assert exc.value.code == 'QUERY_ENDPOINT_REJECTED'


@pytest.fixture
def synthetic_http():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    import time
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            paths.append(self.path)
            route = self.path.split('?', 1)[0]
            if route == '/redirect':
                self.send_response(302)
                self.send_header('Location', 'http://169.254.169.254/latest')
                self.end_headers()
                return
            if route == '/slow':
                time.sleep(0.5)
            if route == '/status':
                self.send_response(503)
                self.end_headers()
                return
            raw = json.dumps(page()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html' if route == '/html' else 'application/json')
            if route == '/gzip':
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (OSError, ValueError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', paths
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_real_synthetic_http_get_ignores_proxy_and_uses_locked_asset(synthetic_http, monkeypatch):
    from json_query import FixedHttpReadTransport
    base, paths = synthetic_http
    transport = FixedHttpReadTransport(base + '/read', input_fields=('subject_id',), environment='SYNTHETIC')
    monkeypatch.setenv('HTTP_PROXY', 'http://192.0.2.1:9')
    monkeypatch.setenv('HTTPS_PROXY', 'http://192.0.2.1:9')
    monkeypatch.setenv('ALL_PROXY', 'http://192.0.2.1:9')
    request, deployment, _ = setup_query()
    registry = deepcopy(deployment.operation_registry)
    registry['fixed-read']['transport_sha256'] = digest(transport.asset)
    deployment = replace(deployment, transports={'fixed-read': transport}, operation_registry=registry)
    request['operation_registry_sha256'] = deployment.operation_registry_sha256
    result = execute_query(request, deployment=deployment)
    assert result['execution_status'] == 'SUCCEEDED'
    assert paths == ['/read?subject_id=SYNTHETIC-1']
    assert result['provenance']['environment'] == 'SYNTHETIC'
    # Changing the configured endpoint without updating the pinned registry is rejected before I/O.
    changed = replace(deployment, transports={'fixed-read': replace(transport, url=base + '/other')})
    assert code(execute_query(request, deployment=changed)) == 'QUERY_ASSET_LOCK_MISMATCH'
    assert len(paths) == 1
    misleading = replace(deployment, environment='TRUSTED_HOST')
    assert code(execute_query(request, deployment=misleading)) == 'QUERY_ENVIRONMENT_MISMATCH'
    assert len(paths) == 1


@pytest.mark.parametrize('route,expected', [('/redirect', 'QUERY_REDIRECT_REJECTED'), ('/status', 'QUERY_HTTP_STATUS'),
    ('/html', 'QUERY_CONTENT_TYPE'), ('/gzip', 'QUERY_CONTENT_TYPE')])
def test_real_http_protocol_failures_are_fail_closed(synthetic_http, route, expected):
    from json_query import FixedHttpReadTransport
    base, paths = synthetic_http
    transport = FixedHttpReadTransport(base + route, environment='SYNTHETIC')
    with pytest.raises(QueryError) as exc:
        transport({'inputs': {}, 'cursor': None, 'batch': None, 'max_response_bytes': 1000}, timeout_seconds=1)
    assert exc.value.code == expected
    assert paths == [route]  # Especially no second request after a redirect.


def test_real_http_response_body_limit(synthetic_http):
    from json_query import FixedHttpReadTransport
    base, _ = synthetic_http
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(base + '/read', environment='SYNTHETIC')(
            {'inputs': {}, 'cursor': None, 'batch': None, 'max_response_bytes': 30}, timeout_seconds=1)
    assert exc.value.code == 'QUERY_BUDGET_EXCEEDED'


def test_real_http_total_deadline_and_active_cancellation(synthetic_http):
    from json_query import FixedHttpReadTransport
    import threading
    import time
    base, _ = synthetic_http
    payload = {'inputs': {}, 'cursor': None, 'batch': None, 'max_response_bytes': 1000}
    start = time.monotonic()
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(base + '/slow', environment='SYNTHETIC')(payload, timeout_seconds=0.08)
    assert exc.value.code == 'QUERY_TIMEOUT'
    assert time.monotonic() - start < 0.4
    cancelled = threading.Event()
    timer = threading.Timer(0.05, cancelled.set)
    timer.start()
    start = time.monotonic()
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(base + '/slow', environment='SYNTHETIC', cancelled=cancelled.is_set)(payload, timeout_seconds=1)
    timer.join()
    assert exc.value.code == 'QUERY_CANCELLED'
    assert time.monotonic() - start < 0.4


def test_watchdog_cancellation_callback_exception_closes_socket(synthetic_http):
    from json_query import FixedHttpReadTransport
    import time
    base, _ = synthetic_http
    calls = []
    def cancellation():
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError('PRIVATE host callback failure')
        return False
    start = time.monotonic()
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(base + '/slow', environment='SYNTHETIC', cancelled=cancellation)(
            {'inputs': {}, 'cursor': None, 'batch': None, 'max_response_bytes': 1000}, timeout_seconds=1)
    assert exc.value.code == 'QUERY_ADAPTER_ERROR'
    assert 'PRIVATE' not in str(exc.value)
    assert time.monotonic() - start < 0.4


def test_watchdog_owns_tls_wrapper_before_handshake(synthetic_http, monkeypatch):
    """Lifecycle regression with a mocked TLS wrapper, not a TLS acceptance test."""
    from json_query import FixedHttpReadTransport
    import threading
    import time
    base, _ = synthetic_http
    observed = []
    class Wrapper:
        def __init__(self, raw):
            self.raw = raw
            self.stopped = threading.Event()
        def settimeout(self, value):
            self.raw.settimeout(value)
        def do_handshake(self):
            observed.append('handshake')
            self.stopped.wait(timeout=1)
            if self.stopped.is_set():
                raise OSError('handshake interrupted')
            raise AssertionError('Watchdog did not own the wrapped socket')
        def shutdown(self, mode):
            observed.append('shutdown-wrapper')
            self.stopped.set()
            self.raw.shutdown(mode)
        def close(self):
            self.raw.close()
    class Context:
        def wrap_socket(self, raw, *, server_hostname, do_handshake_on_connect):
            assert do_handshake_on_connect is False
            assert server_hostname == '127.0.0.1'
            return Wrapper(raw)
    monkeypatch.setattr('json_query.ssl.create_default_context', lambda: Context())
    start = time.monotonic()
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(base.replace('http:', 'https:') + '/slow', environment='SYNTHETIC')(
            {'inputs': {}, 'cursor': None, 'batch': None, 'max_response_bytes': 1000}, timeout_seconds=0.08)
    assert exc.value.code == 'QUERY_TIMEOUT'
    assert observed == ['handshake', 'shutdown-wrapper']
    assert time.monotonic() - start < 0.4


@pytest.mark.parametrize('identifier', ['T-100', 'T-MISSING', 'T-UNKNOWN', 'T-TIMEOUT', 'T-ERROR', None, True])
def test_local_sdk_variables_never_emit_top_level_null(identifier):
    from tools.query_local import QueryLocalTool
    messages = list(QueryLocalTool.from_credentials({})._invoke({'request_json':
                    {'capability_id': 'demo.ticket_lookup', 'parameters': {'ticket_id': identifier}}}))
    variables = {m.message.variable_name: m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert all(value is not None for value in variables.values())
    assert variables['outputs'] == (variables['results']['outputs'] if variables['results']['outputs'] is not None else {})
    assert messages[-1].message.json_object == variables['results']


@pytest.mark.parametrize('mode,expected', [('success', 'SUCCEEDED'), ('unconfigured', 'BLOCKED'),
    ('denied', 'BLOCKED'), ('cancelled', 'CANCELLED'), ('partial', 'UNKNOWN'), ('error', 'FAILED')])
def test_query_sdk_variables_never_emit_top_level_null(mode, expected, monkeypatch):
    from tools.execute_query import ExecuteQueryTool
    request, deployment, _ = setup_query()
    if mode == 'unconfigured':
        deployment = None
    elif mode == 'denied':
        deployment = replace(deployment, authorize=lambda r: False)
    elif mode == 'cancelled':
        deployment = replace(deployment, cancelled=lambda: True)
    elif mode == 'partial':
        deployment = replace(deployment, transports={'fixed-read': lambda *a, **k: page(partial=True)})
    elif mode == 'error':
        deployment = replace(deployment, transports={'fixed-read': lambda *a, **k: page(subject_id='wrong')})
    monkeypatch.setattr('json_query.SDK_DEPLOYMENT', deployment)
    messages = list(ExecuteQueryTool.from_credentials({})._invoke({'request_json': request}))
    variables = {m.message.variable_name: m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert all(value is not None for value in variables.values())
    assert variables['execution_status'] == expected
    if expected != 'SUCCEEDED':
        assert variables['outputs'] == {} and variables['results']['outputs'] is None
    assert messages[-1].message.json_object == variables['results']


@pytest.mark.parametrize('host', ['224.0.0.1', '[ff02::1]', '[ff0e::1]', '239.255.255.255',
    '0.0.0.0', '[::]', '255.255.255.255', '240.0.0.1', '[fec0::1]'])
@pytest.mark.parametrize('environment', ['TRUSTED_HOST', 'SYNTHETIC'])
def test_fixed_transport_rejects_non_unicast_before_socket_creation(host, environment, monkeypatch):
    from json_query import FixedHttpReadTransport
    def unexpected_socket(*args, **kwargs):
        raise AssertionError('A rejected endpoint must not create a network socket')
    monkeypatch.setattr('json_query.socket.socket', unexpected_socket)
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport('https://' + host + '/', environment=environment)
    assert exc.value.code == 'QUERY_ENDPOINT_REJECTED'


@pytest.mark.parametrize('url,environment', [
    ('https://8.8.8.8:0/', 'TRUSTED_HOST'),
    ('https://[2606:4700:4700::1111]:0/', 'TRUSTED_HOST'),
    ('http://127.0.0.1:0/', 'SYNTHETIC'),
    ('https://[::1]:0/', 'SYNTHETIC'),
])
def test_fixed_transport_rejects_explicit_zero_port_before_io(url, environment, monkeypatch):
    from json_query import FixedHttpReadTransport
    def unexpected_socket(*args, **kwargs):
        raise AssertionError('Explicit invalid ports must not create a socket')
    monkeypatch.setattr('json_query.socket.socket', unexpected_socket)
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport(url, environment=environment)
    assert exc.value.code == 'QUERY_ENDPOINT_REJECTED'

# New independent vectors for the declared API-plan profile.
from json_query import (QueryCollection, compile_query_plan, validate_json_schema,
                        validate_schema_value)


def source(source, path, node_id=None):
    origin = {'source': source, 'path': path}
    if node_id is not None:
        origin['node_id'] = node_id
    return {'from': origin}


def declared_query(operations, output_bindings, descriptors, *, output_schema=None,
                   optional_outputs=(), budget=None):
    request, deployment, calls = setup_query(
        operations=operations, output_bindings=output_bindings,
        output_schema=output_schema or {'type': 'object', 'properties': {'answer': {'type': 'string'}},
                                       'required': ['answer'], 'additionalProperties': False},
        optional_outputs=optional_outputs, budget=budget or QueryBudget())
    registry = deepcopy(deployment.operation_registry)
    registry.update(descriptors)
    deployment = replace(deployment, operation_registry=registry)
    request['operation_registry_sha256'] = deployment.operation_registry_sha256
    return request, deployment, calls


def descriptor(inputs, outputs):
    return {'read_only': True, 'source_refs': ['synthetic-source'], 'version': '1',
            'input_schema': inputs, 'output_schema': outputs}


def test_declared_chain_and_fan_in_bind_only_registered_api_fields():
    ops = (QueryOperation('join', 'join', ('left', 'right'), input_bindings={
                'a': source('api', ['data', 'value'], 'left'), 'b': source('api', ['data', 'value'], 'right')}),
           QueryOperation('left', 'left', input_bindings={'subject': source('inputs', ['subject_id'])}),
           QueryOperation('right', 'right', ('left',), input_bindings={'seed': source('api', ['data', 'value'], 'left')}))
    registry = {name: descriptor({'type': 'object'}, {'type': 'object'}) for name in ('left', 'right', 'join')}
    request, deployment, calls = declared_query(ops, {'answer': source('api', ['data', 'answer'], 'join')}, registry)
    def transport(name):
        def read(payload, **kwargs):
            calls.append((name, deepcopy(payload)))
            return page(facts={'value': name} if name != 'join' else {'answer': payload['inputs']['a'] + '+' + payload['inputs']['b']})
        return read
    deployment = replace(deployment, transports={name: transport(name) for name in registry})
    result = execute_query(request, deployment=deployment)
    assert result['outputs'] == {'answer': 'left+right'}
    assert [name for name, _ in calls] == ['left', 'right', 'join']
    assert calls[0][1]['inputs'] == {'subject': 'SYNTHETIC-1'}
    assert calls[1][1]['inputs'] == {'seed': 'left'}
    assert calls[2][1]['inputs'] == {'a': 'left', 'b': 'right'}


@pytest.mark.parametrize('binding', [source('api', ['data'], 'missing'), source('api', ['data'], 'other'),
                                    source('node', ['query'], 'other'), {'literal': 1, 'from': {}},
                                    source('inputs', ['__proto__'])])
def test_all_bad_bindings_fail_before_first_transport(binding):
    ops = (QueryOperation('read', 'fixed-read', input_bindings={'x': binding}), QueryOperation('other', 'fixed-read'))
    request, deployment, calls = declared_query(ops, {'answer': {'literal': 'x'}},
        {'fixed-read': descriptor({'type': 'object'}, {'type': 'object'})})
    assert code(execute_query(request, deployment=deployment)) == 'INVALID_QUERY_PLAN'
    assert calls == []


def test_declared_missing_input_and_future_operation_schema_fail_before_io():
    ops = (QueryOperation('read', 'fixed-read', input_bindings={'x': source('inputs', ['absent'])}),)
    request, deployment, calls = declared_query(ops, {'answer': {'literal': 'x'}},
        {'fixed-read': descriptor({'type': 'object'}, {'type': 'object'})})
    assert code(execute_query(request, deployment=deployment)) == 'QUERY_INPUT_UNAVAILABLE'
    assert calls == []
    request, deployment, calls = setup_query(operations=(QueryOperation('read', 'fixed-read'), QueryOperation('later', 'later')))
    registry = {**deployment.operation_registry, 'later': descriptor({'type': 'object'}, {'$ref': '#/missing'})}
    deployment = replace(deployment, operation_registry=registry, transports={**deployment.transports, 'later': lambda *a, **kw: page()})
    request['operation_registry_sha256'] = deployment.operation_registry_sha256
    assert code(execute_query(request, deployment=deployment)) == 'INVALID_SCHEMA'
    assert calls == []


def collection_query(*, identity=(('id',),), batch=True, local_limit=None, optional=False):
    policy = QueryCollection(('items',), identity)
    op = QueryOperation('read', 'fixed-read', batch_input='ids' if batch else None,
                        batch_size=1, paginate=True, collections=(policy,),
                        max_pages_per_batch=local_limit)
    schema = {'type': 'object', 'properties': {'items': {'type': 'array'}},
              'required': [] if optional else ['items'], 'additionalProperties': False}
    request, deployment, calls = setup_query(operations=(op,), output_schema=schema, optional_outputs=('items',) if optional else ())
    request['inputs']['ids'] = ['x', 'y'] if batch else []
    request['context']['selected_intent']['inputs_sha256'] = digest(request['inputs'])
    # Legacy aggregation across operations uses the same explicit identity rule.
    cap = replace(deployment.capabilities['test.read'], collections=(policy,))
    deployment = replace(deployment, capabilities={'test.read': cap})
    request['query_plan_sha256'] = cap.query_plan_sha256
    return request, deployment, calls


def test_batch_pagination_has_independent_cursor_domains_and_identity_deduplication():
    request, deployment, calls = collection_query()
    def read(payload, **kwargs):
        calls.append(deepcopy(payload))
        item = payload['batch'][0]
        if payload['cursor'] is None:
            return page(facts={'items': [{'id': item, 'value': 1}]}, next_cursor='same-token')
        return page(facts={'items': [{'id': item, 'value': 1}, {'id': item + '2', 'value': 2}]})
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': read}))
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['outputs']['items'] == [{'id': 'x', 'value': 1}, {'id': 'x2', 'value': 2}, {'id': 'y', 'value': 1}, {'id': 'y2', 'value': 2}]
    assert [c['cursor'] for c in calls] == [None, 'same-token', None, 'same-token']
    assert [c['inputs']['ids'] for c in calls] == [['x'], ['x'], ['y'], ['y']]


@pytest.mark.parametrize('second,expected', [
    ([{'id': 'x', 'value': 2}], 'QUERY_FACT_CONFLICT'),
    ([{'value': 2}], 'QUERY_COLLECTION_IDENTITY'),
    ([{'id': None, 'value': 2}], 'QUERY_COLLECTION_IDENTITY')])
def test_keyed_collection_conflict_or_missing_identity_never_publishes(second, expected):
    request, deployment, _ = collection_query(batch=False)
    pages = iter([page(facts={'items': [{'id': 'x', 'value': 1}]}, next_cursor='next'), page(facts={'items': second})])
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': lambda *a, **kw: next(pages)}))
    assert code(result) == expected and result['outputs'] is None


def test_unkeyed_collection_dedup_is_json_type_sensitive_and_stable():
    request, deployment, _ = collection_query(identity=(), batch=False)
    pages = iter([page(facts={'items': [True, 1, {'a': 1}]}, next_cursor='next'),
                  page(facts={'items': [1.0, True, {'a': 1.0}, False]})])
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': lambda *a, **kw: next(pages)}))
    assert result['outputs'] == {'items': [True, 1, {'a': 1}, False]}


def test_empty_batch_is_known_empty_and_never_contacts_transport():
    request, deployment, calls = collection_query()
    request['inputs']['ids'] = []
    request['context']['selected_intent']['inputs_sha256'] = digest(request['inputs'])
    assert execute_query(request, deployment=deployment)['outputs'] == {'items': []}
    assert calls == []


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('required', [False, True])
def test_local_truncation_continues_independent_ops_and_blocks_dependents(reverse, required):
    truncated = QueryOperation('cut', 'cut', paginate=True, max_pages_per_batch=1, input_bindings={})
    good = QueryOperation('good', 'good', input_bindings={})
    dependent = QueryOperation('dependent', 'dependent', ('cut',), input_bindings={'x': source('api', ['data', 'value'], 'cut')})
    ops = (good, truncated, dependent) if reverse else (truncated, dependent, good)
    props = {'answer': {'type': 'string'}, 'extra': {'type': 'string'}}
    registry = {name: descriptor({'type': 'object'}, {'type': 'object'}) for name in ('cut', 'good', 'dependent')}
    request, deployment, calls = declared_query(ops, {'answer': source('api', ['data', 'value'], 'good'),
        'extra': source('api', ['data', 'value'], 'dependent')}, registry,
        output_schema={'type': 'object', 'properties': props, 'required': list(props) if required else ['answer']},
        optional_outputs=() if required else ('extra',))
    def read(name):
        def call(payload, **kwargs):
            calls.append(name)
            return page(facts={'value': name}, **({'next_cursor': 'more'} if name == 'cut' else {}))
        return call
    result = execute_query(request, deployment=replace(deployment, transports={name: read(name) for name in registry}))
    assert set(calls) == {'cut', 'good'} and len(calls) == 2
    assert result['trace']['operation_statuses']['dependent'] == 'BLOCKED_DEPENDENCY'
    assert result['trace']['partial'] is True
    if required:
        assert result['execution_status'] == 'UNKNOWN' and result['outputs'] is None
    else:
        assert result['execution_status'] == 'SUCCEEDED' and result['outputs'] == {'answer': 'good'}
        assert result['trace']['unknown_outputs'] == ['extra']


@pytest.mark.parametrize('schema,valid,invalid', [
    ({'type': ['string', 'null'], 'minLength': 2}, None, 'a'),
    ({'const': {'x': True}}, {'x': True}, {'x': 1}),
    ({'enum': [True, 3]}, True, 1),
    ({'type': 'number', 'minimum': 1, 'exclusiveMaximum': 4, 'multipleOf': 0.5}, 2.5, 4),
    ({'type': 'string', 'pattern': '^ab', 'maxLength': 4}, 'abc', 'zabc'),
    ({'type': 'array', 'prefixItems': [{'type': 'string'}], 'items': {'type': 'integer'}, 'minItems': 2, 'maxItems': 3, 'uniqueItems': True}, ['a', 1], ['a', 1, 1.0]),
    ({'type': 'array', 'contains': {'const': 2}, 'minContains': 1, 'maxContains': 1}, [1, 2], [2, 2]),
    ({'type': 'object', 'patternProperties': {'^x': {'type': 'integer'}}, 'additionalProperties': False}, {'x1': 2}, {'z': 2}),
    ({'type': 'object', 'additionalProperties': {'type': 'string'}, 'minProperties': 1}, {'a': 'b'}, {'a': 1}),
    ({'type': 'object', 'propertyNames': {'minLength': 2}, 'maxProperties': 2}, {'ab': 1}, {'a': 1}),
    ({'type': 'object', 'dependentRequired': {'x': ['y']}}, {'x': 1, 'y': 2}, {'x': 1}),
    ({'type': 'object', 'dependentSchemas': {'x': {'required': ['y']}}}, {'x': 1, 'y': 2}, {'x': 1}),
    ({'allOf': [{'type': 'integer'}, {'minimum': 1}]}, 2, 0),
    ({'anyOf': [{'type': 'string'}, {'type': 'boolean'}]}, True, 3),
    ({'oneOf': [{'type': 'integer'}, {'type': 'number'}]}, 1.5, 1),
    ({'not': {'type': 'string'}}, False, 'x'),
    ({'if': {'type': 'integer'}, 'then': {'minimum': 2}, 'else': {'type': 'string'}}, 'x', 1),
    ({'$defs': {'name': {'type': 'string', 'minLength': 1}}, '$ref': '#/$defs/name'}, 'a', ''),
    ({'allOf': [{'properties': {'x': {'type': 'integer'}}}], 'unevaluatedProperties': False}, {'x': 1}, {'y': 1}),
    ({'prefixItems': [{'type': 'string'}], 'unevaluatedItems': False}, ['x'], ['x', 1]),
])
def test_draft202012_schema_acceptance(schema, valid, invalid):
    validate_json_schema(schema)
    validate_schema_value(valid, schema)
    with pytest.raises(QueryError) as exc:
        validate_schema_value(invalid, schema)
    assert exc.value.code == 'SCHEMA_MISMATCH'


def test_boolean_empty_and_recursive_local_schemas_and_format_annotation():
    validate_json_schema(True)
    validate_schema_value({'anything': True}, {})
    validate_schema_value('not-a-date', {'type': 'string', 'format': 'date-time'})
    schema = {'$defs': {'tree': {'anyOf': [{'type': 'null'}, {'type': 'object', 'properties': {'next': {'$ref': '#/$defs/tree'}}, 'required': ['next']}] }}, '$ref': '#/$defs/tree'}
    validate_json_schema(schema)
    validate_schema_value({'next': {'next': None}}, schema)
    with pytest.raises(QueryError):
        validate_schema_value('x', False)


@pytest.mark.parametrize('schema', [{'$ref': 'https://example.invalid/schema'}, {'$defs': {'unused': {'$ref': 'file:///etc/passwd'}}},
    {'$dynamicRef': 'https://example.invalid/schema#x'}, {'$ref': '#/not-there'},
    {'type': 'unrecognized'}, {'required': ['x', 'x']}, {'pattern': '['}])
def test_schema_invalid_or_remote_assets_rejected_without_io(schema):
    with pytest.raises(QueryError) as exc:
        validate_json_schema(schema)
    assert exc.value.code == 'INVALID_SCHEMA'


@pytest.mark.parametrize('schema,value', [({'$ref': '#'}, {}),
    ({'anyOf': [{'$ref': '#'}, {'type': 'null'}]}, {}),
    ({'pattern': '(a+)+$'}, 'a' * 15000 + '!'),
    ({'patternProperties': {'(a+)+$': {}}, 'additionalProperties': False}, {'a' * 15000 + '!': 1}),
    ({'unevaluatedProperties': False, '$ref': '#'}, {})])
def test_schema_work_is_bounded(schema, value):
    import time
    validate_json_schema(schema)
    started = time.monotonic()
    with pytest.raises(QueryError) as exc:
        validate_schema_value(value, schema)
    assert exc.value.code == 'QUERY_SCHEMA_BUDGET_EXCEEDED'
    assert time.monotonic() - started < 2


def public_plan_fixture():
    plan = {'schema_version': 'service-decision-dsl.query-plan.v2', 'plan_id': 'synthetic.plan', 'example_only': True,
            'read_only': True, 'budget': {'max_calls': 4, 'max_pages': 4, 'max_concurrency': 2, 'total_timeout_ms': 2000},
            'nodes': [{'node_id': 'load', 'operation_ref': 'read', 'depends_on': [],
                       'input_bindings': {'subject': source('inputs', ['subject_id'])}}],
            'outputs': {'answer': source('api', ['data', 'state'], 'load')}, 'operation_registry_ref': 'synthetic.registry'}
    registry = {'schema_version': 'service-decision-dsl.operation-registry.v2', 'example_only': True,
                'operations': {'read': {'read_only': True, 'backend': 'SYNTHETIC',
                    'input_schema': {'type': 'object', 'properties': {'subject': {'type': 'string', 'minLength': 1}}, 'required': ['subject']},
                    'output_schema': {'type': 'object', 'properties': {'state': {'type': 'string'}}, 'required': ['state']}}}}
    return plan, registry


def compile_fixture(plan=None, registry=None):
    default_plan, default_registry = public_plan_fixture()
    return compile_query_plan(default_plan if plan is None else plan, default_registry if registry is None else registry,
        capability_id='test.read', definition_sha256='a' * 64,
        input_schema={'type': 'object', 'properties': {'subject_id': {'type': 'string'}}, 'required': ['subject_id']},
        output_schema={'type': 'object', 'properties': {'answer': {'type': 'string'}}, 'required': ['answer']},
        subject_input='subject_id', source_refs={'read': ['synthetic-source']})


def test_public_plan_compiler_preserves_raw_byte_locks_and_declared_execution():
    plan, registry = public_plan_fixture()
    raw = json.dumps(plan, indent=2).encode()
    compiled = compile_fixture(raw, json.dumps(registry).encode())
    import hashlib
    assert compiled.query_plan_bytes_sha256 == hashlib.sha256(raw).hexdigest()
    assert compiled.query_plan_bytes_sha256 != digest(plan)
    request, deployment, calls = setup_query()
    deployment = replace(deployment, capabilities={'test.read': compiled.capability}, operation_registry=compiled.operation_registry,
                         transports={'read': lambda payload, **kwargs: (calls.append(payload) or page())})
    request['query_plan_sha256'] = compiled.capability.query_plan_sha256
    request['operation_registry_sha256'] = deployment.operation_registry_sha256
    assert execute_query(request, deployment=deployment)['outputs'] == {'answer': 'READY'}
    assert calls[0]['inputs'] == {'subject': 'SYNTHETIC-1'}


@pytest.mark.parametrize('mutation', [lambda p: p['nodes'][0]['depends_on'].append('load'),
    lambda p: p['nodes'][0]['input_bindings'].update(x=source('api', [], 'absent')),
    lambda p: p['budget'].update(max_calls=0), lambda p: p.update(read_only=False),
    lambda p: p['nodes'][0].update(url='https://example.invalid')])
def test_public_plan_compilation_rejects_unsafe_or_unbound_declarations(mutation):
    plan, registry = public_plan_fixture()
    mutation(plan)
    with pytest.raises(QueryError):
        compile_fixture(plan, registry)


def test_declared_context_literal_and_transitive_api_bindings():
    ops = (QueryOperation('first', 'first', input_bindings={'run': source('context', ['run_id']), 'constant': {'literal': None}}),
           QueryOperation('middle', 'middle', ('first',), input_bindings={}),
           QueryOperation('last', 'last', ('middle',), input_bindings={'inherited': source('api', ['data', 'token'], 'first')}))
    registry = {name: descriptor({'type': 'object'}, {'type': 'object'}) for name in ('first', 'middle', 'last')}
    request, deployment, calls = declared_query(ops, {'answer': source('api', ['data', 'token'], 'last')}, registry)
    def read(name):
        def call(payload, **kwargs):
            calls.append((name, payload))
            return page(facts={'token': 'value' if name != 'last' else payload['inputs']['inherited']})
        return call
    result = execute_query(request, deployment=replace(deployment, transports={name: read(name) for name in registry}))
    assert result['outputs'] == {'answer': 'value'}
    assert calls[0][1]['inputs'] == {'run': 'run-1', 'constant': None}
    assert set(calls[2][1]['dependencies']) == {'middle'}


def test_declared_operation_receives_only_its_batch_and_enforces_bound_input_schema():
    op = QueryOperation('read', 'fixed-read', batch_input='ids', batch_size=1,
                        input_bindings={'ids': source('inputs', ['ids'])}, collections=(QueryCollection(('items',)),))
    request, deployment, calls = declared_query((op,), {'items': source('api', ['data', 'items'], 'read')},
        {'fixed-read': descriptor({'type': 'object', 'properties': {'ids': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 1}}, 'required': ['ids']},
                                 {'type': 'object', 'properties': {'items': {'type': 'array', 'minItems': 2}}, 'required': ['items']})},
        output_schema={'type': 'object', 'properties': {'items': {'type': 'array'}}, 'required': ['items']})
    request['inputs']['ids'] = ['x', 'y']
    request['context']['selected_intent']['inputs_sha256'] = digest(request['inputs'])
    def read(payload, **kwargs):
        calls.append(payload)
        return page(facts={'items': payload['inputs']['ids']})
    result = execute_query(request, deployment=replace(deployment, transports={'fixed-read': read}))
    assert result['outputs'] == {'items': ['x', 'y']}
    assert [c['inputs']['ids'] for c in calls] == [['x'], ['y']]


def test_coincident_local_and_global_limit_stops_independent_calls():
    ops = (QueryOperation('cut', 'cut', paginate=True, max_pages_per_batch=1, input_bindings={}),
           QueryOperation('next', 'next', input_bindings={}))
    registry = {name: descriptor({'type': 'object'}, {'type': 'object'}) for name in ('cut', 'next')}
    request, deployment, calls = declared_query(ops, {'answer': source('api', ['data', 'value'], 'next')}, registry,
        budget=QueryBudget(max_calls=1, max_pages=1))
    def read(payload, **kwargs):
        calls.append(payload)
        return page(facts={'value': 'not complete'}, next_cursor='more')
    result = execute_query(request, deployment=replace(deployment, transports={'cut': read, 'next': read}))
    assert code(result) == 'QUERY_BUDGET_EXCEEDED'
    assert len(calls) == 1 and result['outputs'] is None


@pytest.fixture
def synthetic_post_http():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            calls.append({'path': self.path, 'headers': dict(self.headers),
                          'body': json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
            if self.path == '/redirect':
                self.send_response(307)
                self.send_header('Location', '/read')
                self.end_headers()
                return
            if self.path == '/fail':
                self.send_response(500)
                self.end_headers()
                return
            data = json.dumps(page()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', calls
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_reviewed_fixed_readonly_post_uses_typed_body_and_static_headers(synthetic_post_http):
    from json_query import FixedHttpReadTransport
    base, calls = synthetic_post_http
    transport = FixedHttpReadTransport(base + '/read', input_fields=('filters',), batch_parameter='ids',
        method='POST', post_read_only=True, environment='SYNTHETIC', headers=(('X-Test-Mode', 'SYNTHETIC'),))
    payload = {'inputs': {'filters': {'active': True}, 'headers': {'Authorization': 'ignored'}},
               'batch': ['a', 'b'], 'cursor': 'next', 'max_response_bytes': 10000}
    assert json.loads(transport(payload, timeout_seconds=1))['facts'] == {'state': 'READY'}
    assert len(calls) == 1
    assert calls[0]['path'] == '/read'
    assert calls[0]['body'] == {'filters': {'active': True}, 'ids': ['a', 'b'], 'cursor': 'next'}
    assert calls[0]['headers']['Content-Type'] == 'application/json'
    assert calls[0]['headers']['X-Test-Mode'] == 'SYNTHETIC'
    assert 'Authorization' not in calls[0]['headers']
    assert 'SYNTHETIC' not in json.dumps(transport.asset['headers_sha256'])
    assert replace(transport, headers=(('X-Test-Mode', 'OTHER'),)).asset != transport.asset


@pytest.mark.parametrize('route,expected', [('/redirect', 'QUERY_REDIRECT_REJECTED'), ('/fail', 'QUERY_HTTP_STATUS')])
def test_readonly_post_does_not_retry_or_follow_redirect(synthetic_post_http, route, expected):
    from json_query import FixedHttpReadTransport
    base, calls = synthetic_post_http
    transport = FixedHttpReadTransport(base + route, method='POST', post_read_only=True, environment='SYNTHETIC')
    with pytest.raises(QueryError) as exc:
        transport({'inputs': {}, 'batch': None, 'cursor': None, 'max_response_bytes': 1000}, timeout_seconds=1)
    assert exc.value.code == expected and len(calls) == 1


@pytest.mark.parametrize('kwargs', [{'method': 'POST'}, {'method': 'DELETE', 'post_read_only': True},
    {'headers': (('Host', 'other'),)}, {'headers': (('X-A', 'value\r\nInjected: true'),)},
    {'headers': (('Content-Length', '1'),)}, {'headers': (('Proxy-Authorization', 'x'),)},
    {'headers': (('X-A', '1'), ('x-a', '2'))}])
def test_static_transport_policy_rejects_unsafe_methods_and_headers(kwargs):
    from json_query import FixedHttpReadTransport
    with pytest.raises(QueryError) as exc:
        FixedHttpReadTransport('http://127.0.0.1/read', environment='SYNTHETIC', **kwargs)
    assert exc.value.code == 'INVALID_DEPLOYMENT'


def test_compiler_maps_registered_batch_pagination_bounds_without_dynamic_transport():
    plan, registry = public_plan_fixture()
    plan['nodes'][0]['input_bindings']['ids'] = {'literal': ['a', 'b', 'c']}
    registry['operations']['read']['pagination'] = {'parameter': 'cursor', 'items_key': 'items', 'max_pages': 2}
    registry['operations']['read']['batch'] = {'parameter': 'ids', 'max_items': 2, 'max_batches': 1}
    compiled = compile_fixture(plan, registry)
    operation = compiled.capability.operations[0]
    assert operation.batch_input == 'ids' and operation.batch_size == 2 and operation.max_batches == 1
    assert operation.paginate is True and operation.max_pages_per_batch == 2
    assert operation.collections == (QueryCollection(('items',)),)


def test_local_batch_limit_truncates_without_publishing_partial_collection():
    request, deployment, calls = collection_query()
    capability = deployment.capabilities['test.read']
    capability = replace(capability, operations=(replace(capability.operations[0], max_batches=1),))
    deployment = replace(deployment, capabilities={'test.read': capability},
        transports={'fixed-read': lambda payload, **kw: (calls.append(payload) or page(facts={'items': [{'id': 'x'}]}))})
    request['query_plan_sha256'] = capability.query_plan_sha256
    result = execute_query(request, deployment=deployment)
    assert result['execution_status'] == 'UNKNOWN' and result['outputs'] is None
    assert len(calls) == 1 and result['trace']['operation_statuses']['read'] == 'PARTIAL'


def test_explicit_nested_dialect_preserves_budgeted_validator_class_and_shared_deadline(monkeypatch):
    import json_query
    from jsonschema import Draft202012Validator
    ticks = [0.0]
    monkeypatch.setattr(json_query.time, 'monotonic', lambda: ticks[0])
    root = json_query._validator({})
    child = root.evolve(schema={'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                'type': 'string', 'pattern': '(a+)+$'})
    assert type(child) is type(root)
    assert child.VALIDATORS['pattern'] is root.VALIDATORS['pattern']
    assert child.VALIDATORS['pattern'] is not Draft202012Validator.VALIDATORS['pattern']
    assert child._registry is root._registry
    ticks[0] = 2.0
    with pytest.raises(QueryError) as exc:
        child.is_valid('a')
    assert exc.value.code == 'QUERY_SCHEMA_BUDGET_EXCEEDED'


@pytest.mark.parametrize('draft', ['https://json-schema.org/draft/2020-12/schema',
                                   'https://json-schema.org/draft/2020-12/schema#'])
def test_explicit_dialect_recursive_reference_keeps_depth_budget(draft):
    schema = {'$schema': draft, '$ref': '#'}
    validate_json_schema(schema)
    with pytest.raises(QueryError) as exc:
        validate_schema_value({}, schema)
    assert exc.value.code == 'QUERY_SCHEMA_BUDGET_EXCEEDED'


def test_unevaluated_item_annotation_recursion_reports_resource_rejection():
    schema = {'unevaluatedItems': False, '$ref': '#'}
    validate_json_schema(schema)
    with pytest.raises(QueryError) as exc:
        validate_schema_value([], schema)
    assert exc.value.code == 'QUERY_SCHEMA_BUDGET_EXCEEDED'


@pytest.mark.parametrize('route', ['allOf', 'ref', 'properties'])
def test_nested_explicit_dialect_regex_has_a_process_bounded_regression(route):
    # A separate process provides a hard safety bound if this regression ever
    # restores stdlib re through jsonschema's validator_for/evolve behavior.
    import os
    from pathlib import Path
    import subprocess
    import sys
    child = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
             'type': 'string', 'pattern': '(a+)+$'}
    instance = 'a' * 15000 + '!'
    if route == 'allOf':
        schema = {'allOf': [child]}
    elif route == 'ref':
        schema = {'$defs': {'text': child}, '$ref': '#/$defs/text'}
    else:
        schema = {'properties': {'text': child}}
        instance = {'text': instance}
    script = '''
import json, sys
from json_query import QueryError, validate_json_schema, validate_schema_value
schema, value = json.loads(sys.stdin.read())
validate_json_schema(schema)
try:
    validate_schema_value(value, schema)
except QueryError as error:
    print(error.code)
else:
    raise AssertionError('Expected a bounded schema rejection')
'''
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'plugin')}
    result = subprocess.run([sys.executable, '-c', script], input=json.dumps([schema, instance]),
                            text=True, capture_output=True, timeout=3, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'QUERY_SCHEMA_BUDGET_EXCEEDED'
