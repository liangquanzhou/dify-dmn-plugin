from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from json_query import query_local
from tools.evaluate import check_wire_size


class QueryLocalTool(Tool):
    """Offline SYNTHETIC fixture adapter; never performs real business queries."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        result = query_local(tool_parameters.get('request_json'))
        messages = [self.create_variable_message('results', result),
                    self.create_variable_message('status', result['status']),
                    self.create_variable_message('outputs', result['outputs'] if result['outputs'] is not None else {}),
                    self.create_json_message(result)]
        check_wire_size(messages, self.session.session_id if self.session else None)
        yield from messages
