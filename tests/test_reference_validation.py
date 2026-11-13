"""Invalid source paths trigger correction; the model cannot cite unopened files."""
import json
import pytest
from pydantic_ai.models.function import FunctionModel,DeltaToolCall
from pydantic_ai.exceptions import UnexpectedModelBehavior
from doc_agent import create_agent,DocumentationAgentConfig,AgentStreamRunner
from jaxn import JSONParserHandler
from tests.test_pydantic_ai_course import PAYLOAD


@pytest.mark.asyncio
async def test_unopened_reference_is_rejected_then_corrected(documentation_tools):
    calls=[]
    async def model(messages,info):
        calls.append(messages)
        raw=json.dumps({**PAYLOAD,'references':[
            {'file_path':'AA24-038A.txt','explanation':'Unopened source'}] if len(calls)==1 else []})
        yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=raw,tool_call_id=f'o{len(calls)}')}
    agent=create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=model)),documentation_tools)
    result=await AgentStreamRunner(agent,JSONParserHandler(),verbose=False).run('Fixture question')
    assert result.output.references==[]
    assert result.usage.requests==2


@pytest.mark.asyncio
async def test_persistent_invented_reference_fails_instead_of_appearing_valid(documentation_tools):
    async def model(messages,info):
        raw=json.dumps({**PAYLOAD,'references':[{'file_path':'invented.txt','explanation':'Not a source'}]})
        yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=raw,tool_call_id='o')}
    agent=create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=model)),documentation_tools)
    with pytest.raises(UnexpectedModelBehavior,match='retries'):
        await AgentStreamRunner(agent,JSONParserHandler(),verbose=False).run('Fixture question')


@pytest.mark.asyncio
async def test_new_response_must_search_and_supply_checks(documentation_tools):
    attempts=[]
    async def model(messages,info):
        attempts.append(messages)
        if len(attempts)==2:
            yield {0:DeltaToolCall(name='search',json_args='{"query":"fixture"}',tool_call_id='s')}
        else:
            checks=[] if len(attempts)==1 else [{'rule':'Scope','passed':True,'explanation':'Searched; no source answer.'}]
            payload={**PAYLOAD,'found_answer':False,'checks':checks,'references':[]}
            yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=json.dumps(payload),tool_call_id='o')}
    agent=create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=model)),documentation_tools)
    result=await AgentStreamRunner(agent,JSONParserHandler(),verbose=False).run('New response policy')
    assert result.output.checks
    assert result.usage.requests==3
    assert result.usage.tool_calls==1
