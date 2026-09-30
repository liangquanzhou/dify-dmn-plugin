"""Validate fresh evidence with official, unmodified Dify 1.11.1 API classes.

Set PYTHONPATH to the official Dify 1.11.1 api directory. These are real model
imports, not simplified copied schemas. This does not claim an installed Dify
instance, database/workflow execution, custom frontend, or signature trust.
"""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError
from core.tools.entities.tool_entities import ToolInvokeMessage, ToolProviderEntityWithPlugin

OUTPUT_NAMES = {"result", "result_json", "matched", "outputs", "evaluations",
                "matched_rule_ids", "status", "table_id", "table_version"}


def run(evidence_path, declaration_path):
    evidence = json.loads(evidence_path.read_text())
    provider = json.loads(declaration_path.read_text())
    # Exactly the provider-name enrichment performed by PluginToolManager.
    for tool in provider["tools"]:
        tool["identity"]["provider"] = provider["identity"]["name"]
    normalized = ToolProviderEntityWithPlugin.model_validate(provider)
    assert normalized.identity.name == "dmn"
    assert len(normalized.tools) == 1 and len(normalized.credentials_schema) == 0
    tool = normalized.tools[0]
    assert tool.identity.name == "evaluate"
    assert {parameter.name: parameter.form.value for parameter in tool.parameters} == {
        "table_json": "form", "values_json": "llm",
    }
    assert all(parameter.required and parameter.type.value == "string" for parameter in tool.parameters)
    assert set(tool.output_schema["properties"]) == OUTPUT_NAMES
    assert tool.output_schema["properties"]["outputs"]["type"] == "array"
    assert tool.output_schema["properties"]["outputs"].get("items", {}) == {}
    variables = json_messages = errors = credentials = ends = 0
    success_ids = set(evidence["compatibility"]["success_sessions"])
    error_ids = set(evidence["compatibility"]["error_sessions"])
    assert len(success_ids) == 6 and len(error_ids) == 18
    captured = {}
    for event in evidence["events"]:
        if event.get("event") != "session":
            continue
        session_id, frame = event["session_id"], event["data"]
        if frame["type"] == "end":
            ends += 1
            continue
        if session_id == "credential-empty":
            assert frame == {"type": "stream", "data": {"result": True}}
            credentials += 1
            continue
        if session_id in error_ids:
            assert frame["type"] == "error" and frame["data"]["error_type"] == "TableInvocationError"
            errors += 1
            continue
        assert session_id in success_ids and frame["type"] == "stream"
        message = ToolInvokeMessage.model_validate(frame["data"])
        if message.type == ToolInvokeMessage.MessageType.VARIABLE:
            assert isinstance(message.message, ToolInvokeMessage.VariableMessage)
            original = frame["data"]["message"]
            # API validation must preserve list members, scalar types and nulls.
            assert message.message.variable_value == original["variable_value"]
            captured.setdefault(session_id, {})[message.message.variable_name] = message.message.variable_value
            variables += 1
        elif message.type == ToolInvokeMessage.MessageType.JSON:
            assert isinstance(message.message, ToolInvokeMessage.JsonMessage)
            assert message.message.json_object == frame["data"]["message"]["json_object"]
            json_messages += 1
        else:
            raise AssertionError(message)
    assert (variables, json_messages, errors, credentials, ends) == (54, 6, 18, 1, 25)
    assert all(set(outputs) == OUTPUT_NAMES for outputs in captured.values())
    raw_outputs = captured["invoke-raw-outputs"]["outputs"]
    assert raw_outputs == [{"nested": [None, {"text": "保留"}]}, "text", True, 1.25, [1, "x", False, None], None, None]
    assert isinstance(raw_outputs[2], bool) and isinstance(raw_outputs[3], float)
    assert captured["invoke-unknown"]["evaluations"][0]["condition"] is None
    assert captured["invoke-no-match"]["matched"] == []
    # Guard the real legacy restriction: top-level null cannot be a VARIABLE.
    # The plugin avoids it by using object/list/string at every top-level output.
    try:
        ToolInvokeMessage.VariableMessage.model_validate({"variable_name": "top_level_null", "variable_value": None})
    except ValidationError:
        pass
    else:
        raise AssertionError("Unexpected change to Dify 1.11.1 top-level null restriction")
    print("PASS: real Dify 1.11.1 credential-free provider; form/llm string parameters; 9 output fields; 54 variable + 6 JSON messages; mixed/null array preservation; 18 explicit errors")
    print("Scope: API declaration/message-model compatibility; frontend renders unconstrained outputs as Array[Unknown]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("/tmp/dmn-v020-stdio-evidence.json"))
    parser.add_argument("--declaration", type=Path, default=Path("/tmp/dmn-v020-daemon-declaration.json"))
    args = parser.parse_args()
    run(args.evidence, args.declaration)
