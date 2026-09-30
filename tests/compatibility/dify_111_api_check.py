"""Validate fresh daemon-normalized/wire evidence using Dify 1.11.1 classes.

Set PYTHONPATH to the official, unmodified Dify 1.11.1 api directory.
This imports the actual model definitions, not a copied or simplified schema.
"""
import argparse
import json
from pathlib import Path

from core.tools.entities.tool_entities import ToolInvokeMessage, ToolProviderEntityWithPlugin


def run(evidence_path, declaration_path):
    evidence = json.loads(evidence_path.read_text())
    provider = json.loads(declaration_path.read_text())
    # This is the same provider-name enrichment done by PluginToolManager.
    for tool in provider["tools"]:
        tool["identity"]["provider"] = provider["identity"]["name"]
    normalized = ToolProviderEntityWithPlugin.model_validate(provider)
    assert len(normalized.tools) == 1
    assert len(normalized.credentials_schema) == 2
    assert {p.name: p.form.value for p in normalized.tools[0].parameters} == {
        "model_xml": "form", "decision_id": "form", "facts_json": "llm",
    }
    assert len(normalized.tools[0].output_schema["properties"]) == 5
    variables = json_messages = 0
    for event in evidence["events"]:
        if (event.get("session_id") or "").startswith("invoke-") and event.get("data", {}).get("type") == "stream":
            message = ToolInvokeMessage.model_validate(event["data"]["data"])
            if message.type == ToolInvokeMessage.MessageType.VARIABLE:
                assert isinstance(message.message, ToolInvokeMessage.VariableMessage)
                variables += 1
            elif message.type == ToolInvokeMessage.MessageType.JSON:
                assert isinstance(message.message, ToolInvokeMessage.JsonMessage)
                json_messages += 1
            else:
                raise AssertionError(message)
    assert (variables, json_messages) == (25, 5)
    print("PASS: Dify 1.11.1 provider credentials, form/llm parameters, output_schema, 25 variable and 5 JSON payloads")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("/tmp/dmn-stdio-evidence.json"))
    parser.add_argument("--declaration", type=Path, default=Path("/tmp/dmn-daemon-declaration.json"))
    args = parser.parse_args()
    run(args.evidence, args.declaration)
