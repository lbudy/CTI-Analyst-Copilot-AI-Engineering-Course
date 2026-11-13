"""Behavioral regression checks for injectable stream handlers and runner reuse."""
import json
import pytest
from jaxn import JSONParserHandler
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import FunctionModel, DeltaToolCall
from pydantic_ai.exceptions import UsageLimitExceeded
from doc_agent import AgentStreamRunner, DocumentationAgentConfig, create_agent, run_agent_stream
from tests.test_pydantic_ai_course import PAYLOAD
from tests.utils import run_agent_test, collect_tools


@pytest.fixture
def refactor_agent(documentation_tools):
    async def model(messages, info):
        returned={p.tool_name for m in messages for p in m.parts if isinstance(p,ToolReturnPart)}
        if 'search' not in returned:
            yield {0:DeltaToolCall(name='search',json_args='{"query":"Akira VMware"}',tool_call_id='s')}
        elif 'get_file' not in returned:
            yield {0:DeltaToolCall(name='get_file',json_args='{"filename":"AA24-109A.txt"}',tool_call_id='f')}
        else:
            raw=json.dumps(PAYLOAD)
            yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=raw[:35],tool_call_id='o')}
            yield {0:DeltaToolCall(json_args=raw[35:])}
    return create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=model)),documentation_tools)


@pytest.mark.asyncio
async def test_noop_runner_is_silent_but_still_executes_tools(refactor_agent,capsys):
    result=await run_agent_test(refactor_agent,'Find Akira evidence')
    assert capsys.readouterr().out==''
    assert result.output.answer==PAYLOAD['answer']
    assert [c.name for c in collect_tools(result.new_messages())]==['search','get_file']
    assert result.usage.tool_calls==2


@pytest.mark.asyncio
async def test_handler_receives_answer_deltas_and_runner_can_be_reused(refactor_agent,capsys):
    chunks=[]
    class RecordingHandler(JSONParserHandler):
        def on_value_chunk(self,path,field_name,chunk):
            if path=='' and field_name=='answer':
                chunks.append(chunk)
    runner=AgentStreamRunner(refactor_agent,RecordingHandler(),verbose=False)
    first=await runner.run('First question')
    second=await runner.run('Second question')
    assert ''.join(chunks)==PAYLOAD['answer']*2
    assert first.output==second.output
    assert first.usage.requests==second.usage.requests==3
    assert len(first.all_messages())==len(second.all_messages())
    assert capsys.readouterr().out==''


@pytest.mark.asyncio
async def test_production_wrapper_renders_answer_and_tool_activity(refactor_agent,capsys):
    result=await run_agent_stream(refactor_agent,'Find evidence')
    printed=capsys.readouterr().out
    assert 'USER PROMPT' in printed and 'TOOL CALL' in printed
    assert PAYLOAD['answer'] in printed
    assert result.output.answer==PAYLOAD['answer']


@pytest.mark.asyncio
async def test_structured_runner_keeps_request_limit(refactor_agent):
    runner=AgentStreamRunner(refactor_agent,JSONParserHandler(),verbose=False,
                            config=DocumentationAgentConfig(request_limit=1))
    with pytest.raises(UsageLimitExceeded):
        await runner.run('Stop before the second model request')


@pytest.mark.asyncio
async def test_json_parser_resets_when_output_validation_retries(refactor_agent):
    requests=[]
    async def retry_model(messages,info):
        requests.append(messages)
        raw=json.dumps({**PAYLOAD,'confidence':-1 if len(requests)==1 else .5})
        yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=raw[:40],tool_call_id=f'o-{len(requests)}')}
        yield {0:DeltaToolCall(json_args=raw[40:])}
    with refactor_agent.override(model=FunctionModel(stream_function=retry_model)):
        result=await AgentStreamRunner(refactor_agent,JSONParserHandler(),verbose=False).run('Retry invalid confidence')
    assert result.output.confidence==.5
    assert result.usage.requests==2


@pytest.mark.asyncio
async def test_interrupted_helper_preserves_known_usage_without_a_final_answer(refactor_agent):
    with pytest.raises(UsageLimitExceeded) as caught:
        await run_agent_test(refactor_agent,'Stop early',config=DocumentationAgentConfig(request_limit=1))
    partial=caught.value.cti_partial_result
    assert partial.completion_status=='interrupted'
    assert partial.usage.requests==1
    assert caught.value.cti_partial_messages
    assert not hasattr(partial,'output')


@pytest.mark.asyncio
async def test_research_budget_leaves_room_for_final_output(documentation_tools):
    async def bounded_model(messages,info):
        if info.function_tools:
            yield {0:DeltaToolCall(name='search',json_args='{"query":"Akira"}',tool_call_id='s')}
        else:
            yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=json.dumps(PAYLOAD),tool_call_id='o')}
    config=DocumentationAgentConfig(model=FunctionModel(stream_function=bounded_model),research_tool_budget=1)
    agent=create_agent(config,documentation_tools)
    result=await AgentStreamRunner(agent,JSONParserHandler(),verbose=False).run('Bound research')
    assert result.usage.requests==2
    assert result.usage.tool_calls==1
    assert result.output.answer==PAYLOAD['answer']
