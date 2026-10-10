"""Validate captured messages and provider with unmodified pinned Dify API models.

Run in a separate process with PYTHONPATH pointing at official Dify 1.11.1 api.
This is not an installed host or workflow-engine test.
"""
import argparse
import json
from pathlib import Path
from pydantic import ValidationError
from core.tools.entities.tool_entities import ToolInvokeMessage, ToolProviderEntityWithPlugin


def check(evidence_files, declaration, output):
    provider=json.loads(declaration.read_text())
    for tool in provider['tools']:
        tool['identity']['provider']=provider['identity']['name']
    parsed=ToolProviderEntityWithPlugin.model_validate(provider)
    assert {tool.identity.name for tool in parsed.tools}=={'evaluate','evaluate_json_table','evaluate_decision','query_local','execute_query','execute_json_plan'}
    assert len(parsed.credentials_schema)==0
    variables=messages=0
    for file in evidence_files:
        evidence=json.loads(file.read_text())
        for event in evidence['events']:
            if event.get('event')!='session' or event.get('data',{}).get('type')!='stream':continue
            value=event['data']['data']
            if 'type' not in value:continue
            message=ToolInvokeMessage.model_validate(value);messages+=1
            if message.type.value=='variable':
                variables+=1
                assert message.message.variable_value is not None
    try:ToolInvokeMessage.VariableMessage.model_validate({'variable_name':'null','variable_value':None})
    except ValidationError:pass
    else:raise AssertionError('Unexpected change in Dify top-level null restriction')
    result={'status':'PASS','dify_commit':'2058186f22b4e4d4e155f380c130f4e8f21622fa','tools':len(parsed.tools),'messages':messages,'variables':variables,'scope':'Official API models only; not installed host'}
    output.write_text(json.dumps(result,indent=2)+'\n');print(result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',nargs='+',type=Path,required=True);p.add_argument('--declaration',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();check(a.evidence,a.declaration,a.output)
