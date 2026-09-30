import hashlib
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import yaml

from client import DMNError, EngineClient, parse_inputs, engine_origin, exact_json
from tools.evaluate import EvaluateDMNTool
from dify_plugin.entities.tool import ToolConfiguration, ToolProviderConfiguration

XML = '<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="test" />'
PARAMS = {"model_xml": XML, "decision_id": "eligibility", "facts_json": '{"age":25,"income":6000}'}
DIGEST = hashlib.sha256(XML.encode()).hexdigest()
REPLY = {"status": "matched", "result": {"eligible": True}, "matched_rule_ids": ["approved"], "model_version": DIGEST}


def make_client(fn):
    def streaming_handler(request):
        response = fn(request)
        if response.is_stream_consumed:
            # Response(json=...) is eagerly read by HTTPX. Recreate real transport
            # streaming semantics so tests exercise iter_raw, never decoded content.
            return httpx.Response(response.status_code, headers=response.headers,
                                  stream=httpx.ByteStream(response.content))
        return response
    return EngineClient({"engine_url": "https://internal.test", "api_token": "test-token"},
                        transport=httpx.MockTransport(streaming_handler))


def test_contract_request_success():
    def handler(req):
        assert req.url == "https://internal.test/evaluate"
        assert req.headers['authorization'] == 'Bearer test-token'
        assert req.headers['content-type'] == 'application/json'
        assert req.headers['accept-encoding'] == 'identity'
        assert json.loads(req.content) == {"model_xml": XML, "decision_id": "eligibility", "facts": {"age": 25, "income": 6000}}
        return httpx.Response(200, json=REPLY)
    assert make_client(handler).evaluate(PARAMS) == REPLY


@pytest.mark.parametrize('facts', ['null', '[]', 'false', '', '{broken}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e10001}', '{"x":1,"x":2}'])
def test_invalid_facts(facts):
    with pytest.raises(DMNError, match='INVALID_FACTS'):
        parse_inputs({**PARAMS, 'facts_json': facts})


def test_depth_limit():
    with pytest.raises(DMNError, match='nesting'):
        parse_inputs({**PARAMS, 'facts_json': '{"x":' + '[' * 33 + '0' + ']' * 33 + '}'})


@pytest.mark.parametrize('replacement,code', [({'model_xml': ''}, 'INVALID_MODEL'), ({'model_xml': '<!DOCTYPE x><x/>'}, 'UNSAFE_XML'), ({'model_xml': 'x' * (512*1024+1)}, 'INVALID_MODEL'), ({'decision_id': ''}, 'INVALID_DECISION'), ({'facts_json': 'x' * (128*1024+1)}, 'INVALID_FACTS')])
def test_input_limits(replacement, code):
    with pytest.raises(DMNError, match=code):
        parse_inputs({**PARAMS, **replacement})


@pytest.mark.parametrize('origin', ['file:///etc/passwd', 'https://a/b', 'https://a?q=1', 'https://a#fragment', 'https://u:p@a', 'not-url', 'https://a:wrong', None])
def test_bad_origin(origin):
    with pytest.raises(DMNError, match='INVALID_ENDPOINT'):
        engine_origin(origin)


def test_no_match_is_success():
    reply = {**REPLY, 'status': 'no_match', 'result': None, 'matched_rule_ids': []}
    assert make_client(lambda req: httpx.Response(200, json=reply)).evaluate(PARAMS) == reply


@pytest.mark.parametrize('code,http_status', [('MISSING_FACT', 422), ('HIT_POLICY_VIOLATION',422), ('INVALID_XML',400), ('UNKNOWN_DECISION',404), ('UNAUTHORIZED',401)])
def test_engine_error_does_not_leak_business_inputs(code,http_status):
    client = make_client(lambda req: httpx.Response(http_status, json={'error': {'code': code, 'message': 'secret business fact'}}))
    with pytest.raises(DMNError, match=code) as error:
        client.evaluate(PARAMS)
    assert 'secret business' not in str(error.value)


def test_timeout():
    def handler(req):
        raise httpx.ReadTimeout('secret endpoint')
    with pytest.raises(DMNError, match='ENGINE_TIMEOUT'):
        make_client(handler).evaluate(PARAMS)


def test_redirect_is_not_followed():
    count = 0
    def handler(req):
        nonlocal count
        count += 1
        return httpx.Response(307, headers={'location': 'https://evil.example'}, json={})
    with pytest.raises(DMNError, match='ENGINE_REJECTED'):
        make_client(handler).evaluate(PARAMS)
    assert count == 1


@pytest.mark.parametrize('reply', [{**REPLY,'model_version':'wrong'}, {**REPLY,'status':'unknown'}, {**REPLY,'matched_rule_ids':[2]}, ['not object']])
def test_bad_response(reply):
    with pytest.raises(DMNError, match='ENGINE_RESPONSE'):
        make_client(lambda req: httpx.Response(200, json=reply)).evaluate(PARAMS)


def test_response_limit():
    with pytest.raises(DMNError, match='exceeds 1 MiB'):
        make_client(lambda req: httpx.Response(200, content=b'x'*(1024*1024+1))).evaluate(PARAMS)


def test_health():
    make_client(lambda req: httpx.Response(200, json={'status':'ok'})).health()


def test_sdk_variable_outputs(monkeypatch):
    monkeypatch.setattr(EngineClient, 'evaluate', lambda self, params: REPLY)
    tool = EvaluateDMNTool.from_credentials({'engine_url':'https://internal.test'})
    messages = list(tool._invoke(PARAMS))
    variables = {m.message.variable_name:m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert variables['result'] == {'value': {'eligible':True}}
    assert json.loads(variables['result_json']) == {'eligible':True}
    assert variables['model_version'] == DIGEST
    assert variables['status'] == 'matched'
    assert variables['matched_rule_ids'] == ['approved']
    assert len(messages) == 6


def test_no_match_sdk_outputs(monkeypatch):
    monkeypatch.setattr(EngineClient, 'evaluate', lambda self, params: {**REPLY,'status':'no_match','result':None,'matched_rule_ids':[]})
    values = list(EvaluateDMNTool.from_credentials({'engine_url':'https://internal.test'})._invoke(PARAMS))
    outputs={m.message.variable_name:m.message.variable_value for m in values if m.type.value=='variable'}
    assert outputs['result'] == {'value':None}
    assert outputs['result_json'] == 'null'


def test_yaml_validates_against_real_sdk(monkeypatch):
    root=Path(__file__).resolve().parents[1]/'plugin'
    monkeypatch.chdir(root)
    tool=ToolConfiguration.model_validate(yaml.safe_load((root/'tools/evaluate.yaml').read_text()))
    provider=ToolProviderConfiguration.model_validate(yaml.safe_load((root/'provider/dmn.yaml').read_text()))
    assert tool.identity.name == 'evaluate'
    assert provider.identity.name == 'dmn'
    assert {p.name:p.form.value for p in tool.parameters} == {'model_xml':'form','decision_id':'form','facts_json':'llm'}


def test_decimal_request_and_response_are_exact():
    number = '0.123456789012345678901234567890123456789'
    raw_facts = '{"amount":' + number + ',"large":9007199254740993.0,"scale":1e999}'
    expected = json.loads(raw_facts, parse_float=Decimal)
    reply = {**REPLY, 'result': expected}
    def handler(request):
        assert json.loads(request.content, parse_float=Decimal)['facts'] == expected
        assert number.encode() in request.content
        assert b'9007199254740993.0' in request.content
        return httpx.Response(200, content=exact_json(reply).encode('utf-8'))
    result = make_client(handler).evaluate({**PARAMS, 'facts_json': raw_facts})
    assert result == reply
    assert isinstance(result['result']['amount'], Decimal)


def test_sdk_decimal_and_large_integer_output_contract(monkeypatch):
    native = {
        'decimal': Decimal('0.12345678901234567890123456789'),
        'nested': [Decimal('2.0'), 2**53 - 1, 2**53, -(2**53), True, False, None],
    }
    monkeypatch.setattr(EngineClient, 'evaluate', lambda self, params: {**REPLY, 'result': native})
    messages = list(EvaluateDMNTool.from_credentials({'engine_url': 'https://internal.test'})._invoke(PARAMS))
    outputs = {m.message.variable_name: m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert outputs['result']['value'] == {
        'decimal': '0.12345678901234567890123456789',
        'nested': ['2.0', 2**53 - 1, str(2**53), str(-(2**53)), True, False, None],
    }
    assert json.loads(outputs['result_json'], parse_float=Decimal) == native
    assert '"decimal":0.12345678901234567890123456789' in outputs['result_json']
    assert '[2.0,9007199254740991,9007199254740992,-9007199254740992,true,false,null]' in outputs['result_json']
    # Verify the actual SDK's wire serialization, not only the Python message.
    encoded = [json.loads(m.model_dump_json()) for m in messages]
    value_message = next(m for m in encoded if m['type'] == 'variable' and m['message']['variable_name'] == 'result')
    assert value_message['message']['variable_value'] == outputs['result']


@pytest.mark.parametrize('number', ['9' * 5000, '0.' + '1' * 256, '1e10001', '1e-10001', '0e10001', '9.9e10001'])
def test_numbers_outside_bounds_fail_cleanly(number):
    with pytest.raises(DMNError, match='^INVALID_FACTS:'):
        parse_inputs({**PARAMS, 'facts_json': '{"x":' + number + '}'})


@pytest.mark.parametrize('number', ['1e10000', '1e-10000', '0e10000', '9' * 256])
def test_numbers_at_bounds_are_exact(number):
    _, _, facts = parse_inputs({**PARAMS, 'facts_json': '{"x":' + number + '}'})
    assert Decimal(str(facts['x'])) == Decimal(number)


@pytest.mark.parametrize('replacement,code', [
    ({'model_xml': '<x>\ud800</x>'}, 'INVALID_MODEL'),
    ({'decision_id': 'private\ud800'}, 'INVALID_DECISION'),
    ({'facts_json': '{"x":"\ud800"}'}, 'INVALID_FACTS'),
    ({'facts_json': '{"x":"\\ud800"}'}, 'INVALID_FACTS'),
    ({'facts_json': '{"\\ud800":1}'}, 'INVALID_FACTS'),
])
def test_invalid_unicode_is_sanitized(replacement, code):
    with pytest.raises(DMNError, match='^' + code + ':') as error:
        make_client(lambda request: pytest.fail('Invalid Unicode must fail before transport')).evaluate({**PARAMS, **replacement})
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('origin', [
    'https://exa\nmple.com', 'https://example.com\x00', 'https://example.com\t',
    'https://\ud800', 'https://@example.com', 'https://example.com:999999',
])
def test_invalid_origins_are_sanitized(origin):
    with pytest.raises(DMNError, match='^INVALID_ENDPOINT:'):
        EngineClient({'engine_url': origin})


@pytest.mark.parametrize('token', ['private\r\nsecret', 'private\x00secret', 'private secret', '秘密', False, 123])
def test_invalid_credentials_are_sanitized(token):
    with pytest.raises(DMNError, match='^INVALID_CREDENTIAL:') as error:
        EngineClient({'engine_url': 'https://internal.test', 'api_token': token})
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('raw_result', [
    'NaN', 'Infinity', '1e10001', '1e-10001', '9' * 5000,
    '"\\ud800"', '{"x":1,"x":2}',
])
def test_invalid_engine_json_is_response_error(raw_result):
    raw = json.dumps({**REPLY, 'result': None}).replace('null', raw_result)
    with pytest.raises(DMNError, match='^ENGINE_RESPONSE:'):
        make_client(lambda request: httpx.Response(200, content=raw.encode())).evaluate(PARAMS)


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'br', 'gzip, identity'])
def test_encoded_response_rejected_before_reading_stream(encoding):
    class UnreadStream(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail('Encoded content must not be read or decompressed')
            yield b''
    def handler(request):
        assert request.headers['accept-encoding'] == 'identity'
        return httpx.Response(200, headers={'Content-Encoding': encoding}, stream=UnreadStream())
    with pytest.raises(DMNError, match='compressed engine responses'):
        make_client(handler).evaluate(PARAMS)


def test_raw_response_limit_stops_consumption():
    class OversizeStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'x' * (1024 * 1024)
            yield b'x'
            pytest.fail('Must stop reading immediately after the byte limit')
    with pytest.raises(DMNError, match='exceeds 1 MiB'):
        make_client(lambda request: httpx.Response(200, stream=OversizeStream())).evaluate(PARAMS)


def test_response_allows_engine_result_depth_with_envelope():
    result = None
    for _ in range(32):
        result = [result]
    reply = {**REPLY, 'result': result}
    assert make_client(lambda request: httpx.Response(200, json=reply)).evaluate(PARAMS) == reply
