from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

import json_query
import json_query_node
from tools.evaluate import check_wire_size


class ExecuteQueryTool(Tool):
    """Fixed host-registered read-only capability. Default installation is blocked."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        node_fields = ('definition_bundle_json', 'node_ref', 'expected_definition_sha256',
                       'inputs_json', 'execution_context_json')
        if 'request_json' in tool_parameters and any(key in tool_parameters for key in node_fields):
            result = json_query._result('FAILED', 'INVALID_REQUEST')
        elif any(key in tool_parameters for key in node_fields):
            result = json_query_node.execute_query_node(*(tool_parameters.get(key) for key in node_fields),
                                                       deployment=json_query_node.SDK_NODE_DEPLOYMENT)
        else:
            result = json_query.execute_query(tool_parameters.get('request_json'), deployment=json_query.SDK_DEPLOYMENT)
        messages = [self.create_variable_message('results', result)]
        messages.extend(self.create_variable_message(name, {} if name == 'outputs' and result[name] is None else result[name]) for name in
                        ('execution_status', 'output_port', 'outputs', 'diagnostics', 'trace'))
        messages.append(self.create_json_message(result))
        check_wire_size(messages, self.session.session_id if self.session else None)
        yield from messages
