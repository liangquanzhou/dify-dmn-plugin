from collections.abc import Generator
import json
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.core.entities.message import SessionMessage
from dify_plugin.core.server.__base.writer_entities import Event, StreamOutputMessage

from evaluator import TableError
from io_contract import invoke_table

# Official Dify 1.11.1's daemon defaults to a 5 MiB output scanner. Check the
# real SDK framing at 4 MiB, before emitting anything; never yield partial success.
MAX_WIRE_BYTES = 4 * 1024 * 1024
LEGACY_OUTPUT_NAMES = ("result", "result_json", "matched", "outputs", "evaluations",
                       "matched_rule_ids", "status", "table_id", "table_version")


class TableInvocationError(ValueError):
    """The SDK transports this exception as a failed Tool invocation."""


def check_wire_size(messages: list[ToolInvokeMessage], session_id: str | None) -> None:
    for message in messages:
        session = SessionMessage(type=SessionMessage.Type.STREAM, data=message.model_dump())
        framed = StreamOutputMessage(event=Event.SESSION, session_id=session_id, data=session.model_dump())
        if len(framed.model_dump_json().encode('utf-8')) + 2 > MAX_WIRE_BYTES:
            raise TableError('LIMIT_EXCEEDED', '$', 'The serialized SDK response exceeds the safe wire-size limit')


class EvaluateDMNTool(Tool):
    """Evaluate exactly one saved JSON decision table inside this plugin process."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            outputs = invoke_table(tool_parameters)
            messages = [self.create_variable_message(name, value) for name, value in outputs.items()]
            # Retain the v0.2.0 aggregate JSON shape and size. New diagnostics
            # are independent bindable variables, including decision_result.
            messages.append(self.create_json_message({name: outputs[name] for name in LEGACY_OUTPUT_NAMES}))
            check_wire_size(messages, self.session.session_id if self.session else None)
        except TableError as exc:
            # Explicit Tool failure: never turn invalid input into a no-match result.
            raise TableInvocationError(json.dumps(exc.as_dict(), ensure_ascii=False)) from None
        yield from messages
