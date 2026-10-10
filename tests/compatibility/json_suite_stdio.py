"""New 0.7 candidate tools through the pinned SDK's actual stdio process.

Works against source or the exact unpacked official package. Fixtures are all
SYNTHETIC. A query without trusted deployment must remain blocked.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import zipfile
import tempfile

ROOT=Path(__file__).resolve().parents[2]


def scenarios():
    table=json.loads((ROOT/'examples/json-suite/table-profile.json').read_text())
    yield 'table-object','evaluate_json_table',{'table_json':table,'inputs_json':{'customer':{'confirmed_at':None}}},('status','SUCCEEDED')
    yield 'table-string','evaluate_json_table',{'table_json':json.dumps(table),'inputs_json':'{}'},('status','WAITING_INPUT')
    yield 'table-error','evaluate_json_table',{'table_json':table,'inputs_json':'{"x":1,"x":2}'},('status','FAILED')
    typed=json.loads((ROOT/'examples/json-suite/typed-decision-request.json').read_text())
    yield 'typed-success','evaluate_decision',typed,('execution_status','SUCCEEDED')
    bad=deepcopy(typed);bad['inputs_json']['parameter_snapshot']['parameters']['eligible'].update(quality='UNKNOWN',value=None)
    yield 'typed-blocked','evaluate_decision',bad,('execution_status','BLOCKED')
    bad=deepcopy(typed);bad['inputs_json']['parameter_snapshot']['parameters']['eligible']['value']='true'
    yield 'typed-type-failed','evaluate_decision',bad,('execution_status','FAILED')
    for suffix,status in [('100','SUCCEEDED'),('MISSING','SUCCEEDED'),('UNKNOWN','WAITING_INPUT'),('TIMEOUT','FAILED'),('ERROR','FAILED')]:
        yield 'local-'+suffix.lower(),'query_local',{'request_json':json.dumps({'capability_id':'demo.ticket_lookup','parameters':{'ticket_id':'T-'+suffix}})},('status',status)
    yield 'query-closed','execute_query',{'request_json':(ROOT/'examples/json-suite/unconfigured-query-request.json').read_text()},('execution_status','BLOCKED')
    node=json.loads((ROOT/'examples/json-suite/query-node-request.json').read_text())
    yield 'query-node-closed','execute_query',node,('execution_status','BLOCKED')
    sys.path.insert(0,str(ROOT/'plugin'))
    from json_profiles import canonical_digest
    table=dict(format='json-table-v1',id='synthetic',version='1',hit_policy='FIRST',rules=[dict(id='r',when=[],output={'answer':'SYNTHETIC'})])
    request={'plan':{'format':'json-plan-v1','id':'stdio-plan','version':'0.3.0','flow':'locate_problem',
                     'phases':[{'id':'LOCATE','steps':[{'id':'d','kind':'decision','depends_on':[],'model_id':'m','hit_policy':'FIRST','inputs':{}}]}],
                     'outputs':{'answer':{'from':['steps','d','result','answer']}}},'models':{'m':{'table':table,'sha256':canonical_digest(table)}},'inputs':{}}
    yield 'plan-success','execute_json_plan',{'request_json':json.dumps(request)},('status','SUCCEEDED')
    request['models']['m']['sha256']='0'*64
    yield 'plan-pin-failed','execute_json_plan',{'request_json':json.dumps(request)},('status','FAILED')


def run(root,output,package=None):
    assert sys.version_info[:2]==(3,12)
    assert importlib.metadata.version('dify-plugin')=='0.10.2'
    cleanup=None
    if package:
        cleanup=tempfile.TemporaryDirectory(prefix='dmn-070-suite-')
        root=Path(cleanup.name)
        with zipfile.ZipFile(package) as archive:
            for item in archive.infolist():
                assert (root/item.filename).resolve().is_relative_to(root.resolve())
            archive.extractall(root)
    proc=subprocess.Popen([sys.executable,'-u','main.py'],cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                          env={**os.environ,'INSTALL_METHOD':'local','PYTHONUNBUFFERED':'1'})
    incoming=queue.Queue();stderr=[];events=[];max_frame=0
    def reader():
        for line in proc.stdout:
            incoming.put(line)
    threading.Thread(target=reader,daemon=True).start()
    threading.Thread(target=lambda:stderr.extend(proc.stderr.readlines()),daemon=True).start()
    def receive_until(predicate):
        nonlocal max_frame
        deadline=time.monotonic()+30;seen=[]
        while time.monotonic()<deadline:
            try:line=incoming.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:break
            max_frame=max(max_frame,len(line.encode()))
            if not line.strip():continue
            event=json.loads(line);events.append(event);seen.append(event)
            if predicate(event):return seen
        raise AssertionError(f'SDK process did not finish session; exit={proc.poll()} stderr={stderr!r}')
    records=[]
    try:
        boot=receive_until(lambda e:e.get('type')=='plugin')[-1]
        assert boot['version']=='0.7.0'
        for session,tool,parameters,(field,expected) in scenarios():
            payload={'session_id':session,'conversation_id':None,'message_id':None,'app_id':None,'endpoint_id':None,'context':None,'event':'request',
                     'data':{'user_id':'synthetic-validation','type':'tool','action':'invoke_tool','provider':'dmn','credentials':{},'tool':tool,'tool_parameters':parameters}}
            proc.stdin.write(json.dumps(payload)+'\n');proc.stdin.flush()
            replies=receive_until(lambda e:e.get('event')=='session' and e.get('session_id')==session and e.get('data',{}).get('type')=='end')
            streams=[e['data']['data'] for e in replies if e.get('session_id')==session and e.get('data',{}).get('type')=='stream']
            assert not [e for e in replies if e.get('session_id')==session and e.get('data',{}).get('type')=='error'],replies
            variables={e['message']['variable_name']:e['message']['variable_value'] for e in streams if e['type']=='variable'}
            result=variables['results']
            assert result[field]==expected,(session,result)
            assert any(e['type']=='json' for e in streams)
            if tool=='evaluate_decision' and expected!='SUCCEEDED':
                assert variables['state']=='' and variables['data']=={} and variables['actions']==[]
            if tool=='query_local':assert result['provenance']['environment']=='SYNTHETIC'
            if tool=='execute_query':assert result['diagnostics'][0]['code']=='QUERY_CONNECTION_NOT_CONFIGURED'
            records.append({'session':session,'tool':tool,'assertion':{field:expected},'passed':True})
        assert max_frame<=4*1024*1024
        evidence={'version':'0.7.0','sdk':'0.10.2','python':sys.version.split()[0],'sessions':records,'max_wire_frame_bytes':max_frame,
                  'package_sha256':hashlib.sha256(package.read_bytes()).hexdigest() if package else None,
                  'scope':'SYNTHETIC stdio; not Dify host installation or production authorization','events':events}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print(f'PASS: {len(records)} new-tool SDK stdio sessions; max frame {max_frame}; evidence {output}')
    finally:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if cleanup:cleanup.cleanup()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plugin-root',type=Path,default=ROOT/'plugin');parser.add_argument('--output',type=Path,default=ROOT/'evidence/json-suite-stdio.json');parser.add_argument('--package',type=Path)
    args=parser.parse_args();run(args.plugin_root,args.output,args.package)
