from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from json_plan import execute_json_plan
from tools.evaluate import check_wire_size


class ExecuteJsonPlanTool(Tool):
    """Advisory local plan adapter; not a controller or action runtime."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        result = execute_json_plan(tool_parameters.get('request_json'), tool_parameters.get('expected_sha256'))
        messages = [self.create_variable_message('results', result),
                    self.create_variable_message('status', result['status']),
                    self.create_variable_message('outputs', result['outputs'] if result['outputs'] is not None else {}),
                    self.create_json_message(result)]
        check_wire_size(messages, self.session.session_id if self.session else None)
        yield from messages
