from collections.abc import Generator
from decimal import Decimal
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from client import EngineClient, exact_json

MAX_SAFE_INTEGER = 2**53 - 1


def workflow_value(value: Any) -> Any:
    """Use decimal strings where Dify/JavaScript numeric values would lose precision.

    result_json remains authoritative numeric JSON. The convenient result.value
    wrapper keeps booleans, null, and safe integers native; every Decimal and
    integer outside JavaScript's safe range becomes a string, recursively.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal) or isinstance(value, int) and abs(value) > MAX_SAFE_INTEGER:
        return str(value)
    if isinstance(value, dict):
        return {key: workflow_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [workflow_value(child) for child in value]
    return value


class EvaluateDMNTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        value = EngineClient(self.runtime.credentials).evaluate(tool_parameters)
        outputs = {
            "status": value["status"],
            "result": {"value": workflow_value(value["result"])},
            "result_json": exact_json(value["result"]),
            "matched_rule_ids": value["matched_rule_ids"],
            "model_version": value["model_version"],
        }
        for name, output in outputs.items():
            yield self.create_variable_message(name, output)
        yield self.create_json_message(outputs)
