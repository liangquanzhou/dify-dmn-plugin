"""Real Java KIE service -> HTTP -> Python Dify SDK Tool round-trip.

Build engine/target/dmn-engine-service.jar first. This does not install a plugin
into Dify or claim a full Dify deployment test.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest

from client import DMNError, EngineClient
from tools.evaluate import EvaluateDMNTool

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def credentials():
    jar = ROOT/'engine/target/dmn-engine-service.jar'
    if not jar.exists():
        pytest.skip('Build the real engine JAR with mvn package before integration tests')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {**os.environ, 'DMN_ENV':'development','DMN_BIND_HOST':'127.0.0.1','PORT':str(port),'DMN_API_TOKEN':''}
    process = subprocess.Popen(['java','-Xmx512m','-jar',str(jar)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    credentials = {'engine_url':f'http://127.0.0.1:{port}'}
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError('Java DMN engine exited before becoming healthy')
            try:
                EngineClient(credentials).health()
                break
            except DMNError:
                time.sleep(.1)
        else:
            raise AssertionError('Java DMN engine did not become healthy in 10 seconds')
        yield credentials
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.fixture
def params():
    return {'model_xml':(ROOT/'examples/eligibility.dmn').read_text(), 'decision_id':'eligibility','facts_json':'{"age":25,"risk_score":30}'}


def test_real_success_and_sdk_outputs(credentials, params):
    messages = list(EvaluateDMNTool.from_credentials(credentials).invoke(params))
    output = {m.message.variable_name:m.message.variable_value for m in messages if m.type.value == 'variable'}
    assert output['status'] == 'matched'
    assert output['result'] == {'value':{'eligible':True,'reason':'low_risk_adult'}}
    assert json.loads(output['result_json']) == {'eligible':True,'reason':'low_risk_adult'}
    assert output['matched_rule_ids'] == ['rule_eligible']
    assert output['model_version'] == hashlib.sha256(params['model_xml'].encode()).hexdigest()


def test_real_no_match(credentials, params):
    result=EngineClient(credentials).evaluate({**params,'facts_json':'{"age":25,"risk_score":101}'})
    assert result['status']=='no_match'
    assert result['matched_rule_ids']==[]
    assert result['result'] is None


@pytest.mark.parametrize('override,code', [
    ({'facts_json':'{"age":25}'}, 'MISSING_FACTS'),
    ({'facts_json':'{"age":"not a number","risk_score":30}'}, 'EVALUATION_ERROR'),
    ({'decision_id':'does-not-exist'}, 'UNKNOWN_DECISION'),
    ({'model_xml':'<definitions'}, 'INVALID_XML'),
])
def test_real_errors(credentials, params, override, code):
    with pytest.raises(DMNError, match=code):
        EngineClient(credentials).evaluate({**params,**override})


def test_real_unique_overlap(credentials,params):
    xml=params['model_xml'].replace('<text>[60..100]</text>', '<text>[0..100]</text>')
    with pytest.raises(DMNError,match='EVALUATION_ERROR'):
        EngineClient(credentials).evaluate({**params,'model_xml':xml})


def test_real_precision_end_to_end(credentials):
    exact='0.12345678901234567890123456789'
    xml='''<?xml version="1.0"?><definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="p" name="precision" namespace="urn:test:precision"><inputData id="i" name="x"><variable name="x" typeRef="number"/></inputData><decision id="echo" name="echo"><variable name="echo" typeRef="number"/><informationRequirement><requiredInput href="#i"/></informationRequirement><literalExpression><text>x</text></literalExpression></decision></definitions>'''
    params={'model_xml':xml,'decision_id':'echo','facts_json':'{"x":'+exact+'}'}
    messages=list(EvaluateDMNTool.from_credentials(credentials).invoke(params))
    output={m.message.variable_name:m.message.variable_value for m in messages if m.type.value=='variable'}
    assert output['result_json']==exact
    assert output['result']=={'value':exact}
