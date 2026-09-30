import json

import pytest

from tools.evaluate import EvaluateDMNTool, TableInvocationError
from dify_plugin.core.entities.message import SessionMessage
from dify_plugin.core.server.__base.writer_entities import Event, StreamOutputMessage


def invoke(model, values):
    return EvaluateDMNTool.from_credentials({})._invoke({
        'table_json': json.dumps(model, ensure_ascii=False),
        'values_json': json.dumps(values, ensure_ascii=False),
    })


def test_tool_sends_all_seventeen_bindable_variables_and_one_json_message():
    model = {'id': 'synthetic', 'hit_policy': 'FIRST', 'rules': [{'id': 'r', 'when': True, 'output': '中文\n"\\'}]}
    messages = list(invoke(model, {}))
    assert len(messages) == 18
    assert len([m for m in messages if m.type.value == 'variable']) == 17
    assert messages[-1].type.value == 'json'
    assert set(messages[-1].message.json_object) == {'result', 'result_json', 'matched', 'outputs', 'evaluations', 'matched_rule_ids', 'status', 'table_id', 'table_version'}
    for msg in messages:
        frame = StreamOutputMessage(event=Event.SESSION, session_id='', data=SessionMessage(type=SessionMessage.Type.STREAM, data=msg.model_dump()).model_dump())
        assert len(frame.model_dump_json().encode()) + 2 < 4 * 1024 * 1024


def test_error_precedes_all_outputs():
    model = {'id': 'synthetic', 'hit_policy': 'FIRST', 'rules': [{'id': 'a', 'when': True}, {'id': 'b', 'when': {'gt': ['x', 1]}}]}
    stream = invoke(model, {'x': 'PRIVATE-INPUT'})
    with pytest.raises(TableInvocationError) as exc:
        next(stream)
    details = json.loads(str(exc.value))
    assert details['code'] == 'INVALID_VALUE'
    assert 'PRIVATE-INPUT' not in str(exc.value)


def test_oversized_aggregate_sdk_frame_fails_before_first_yield():
    key = 'k' * 400
    model = {'id': 'large', 'hit_policy': 'COLLECT', 'rules': [{'id': str(i), 'when': {'eq': [key, 1]}} for i in range(1000)]}
    assert len(json.dumps(model).encode()) < 512 * 1024
    with pytest.raises(TableInvocationError) as exc:
        next(invoke(model, {key: 1}))
    assert json.loads(str(exc.value))['code'] == 'LIMIT_EXCEEDED'


def test_wire_guard_uses_actual_escaping_and_runs_before_yield(monkeypatch):
    monkeypatch.setattr('tools.evaluate.MAX_WIRE_BYTES', 1024)
    model = {'id': 'escaping', 'hit_policy': 'FIRST', 'rules': [{'id': 'r', 'when': True, 'output': '\\"\n' * 80}]}
    with pytest.raises(TableInvocationError) as exc:
        next(invoke(model, {}))
    assert json.loads(str(exc.value))['code'] == 'LIMIT_EXCEEDED'


def test_legacy_large_frame_remains_accepted_despite_new_diagnostics():
    key = 'k' * 280
    model = {'id': 'large-compatible', 'hit_policy': 'COLLECT', 'rules': [{'id': 'r'+str(i), 'when': {'eq': [key, 1]}} for i in range(1000)]}
    messages = list(invoke(model, {key: 1}))
    assert len(messages) == 18
    # All 17 variable messages are present; the one JSON aggregation stays v0.2.0.
    assert 'all_matches' not in messages[-1].message.json_object
    assert [m.message.variable_name for m in messages[:-1]].count('all_matches') == 1
