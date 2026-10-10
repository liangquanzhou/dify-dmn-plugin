from dify_plugin import Tool
from json_decision import evaluate_decision, decision_tool_outputs
from tools.evaluate import check_wire_size


class EvaluateTypedDecisionTool(Tool):
    def _invoke(self, tool_parameters):
        result = evaluate_decision(*(tool_parameters.get(key) for key in (
            'definition_bundle_json', 'node_ref', 'expected_definition_sha256', 'inputs_json', 'execution_context_json')))
        outputs = decision_tool_outputs(result)
        messages = [self.create_variable_message(key, value) for key, value in outputs.items()]
        messages.append(self.create_json_message({'results': result}))
        check_wire_size(messages, self.session.session_id if self.session else None)
        yield from messages
