from dify_plugin import Tool
from json_profiles import evaluate_json_table
from tools.evaluate import check_wire_size


class EvaluateJSONProfileTool(Tool):
    def _invoke(self, tool_parameters):
        result = evaluate_json_table(tool_parameters.get('table_json'), tool_parameters.get('inputs_json'), tool_parameters.get('expected_sha256'))
        messages = [self.create_variable_message('results', result), self.create_json_message({'results': result})]
        check_wire_size(messages, self.session.session_id if self.session else None)
        yield from messages
