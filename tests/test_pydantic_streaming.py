"""Course streaming behavior tested with the real framework and fake model streams."""
import contextlib
import io
from unittest.mock import patch
import pytest
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel, DeltaToolCall
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.exceptions import UsageLimitExceeded
from doc_agent import (DocumentationAgentConfig, create_agent, run_agent_stream_simple,
                       run_agent_stream_text)
from tools import create_documentation_tools_cached


@pytest.fixture(autouse=True)
def disable_real_requests():
    with patch.object(models, 'ALLOW_MODEL_REQUESTS', False):
        yield


@pytest.mark.asyncio
async def test_simple_text_stream_completes():
    async def stream(messages, info):
        yield 'Offline '
        yield 'answer.'
    agent = create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=stream)),
                         create_documentation_tools_cached(), output_type=str)
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await run_agent_stream_simple(agent, 'A test question')
    assert await result.get_output() == 'Offline answer.'
    assert 'Offline answer.' in capture.getvalue()
    assert result.usage.requests == 1


@pytest.mark.asyncio
async def test_graph_executes_tools_despite_intermediate_text_and_keeps_history():
    calls = []
    async def stream(messages, info):
        calls.append(messages)
        if len(calls) == 1:
            yield 'Searching the reports.'
            yield {0: DeltaToolCall(name='search', json_args='{"query":"Akira VMware"}', tool_call_id='s')}
        elif len(calls) == 2:
            yield 'Opening the source.'
            yield {0: DeltaToolCall(name='get_file', json_args='{"filename":"AA24-109A.txt"}', tool_call_id='f')}
        else:
            yield 'Offline final '
            yield 'answer after tool execution.'
    agent = create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=stream)),
                         create_documentation_tools_cached(), output_type=str)
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = await run_agent_stream_text(agent, 'Find Akira evidence')
    assert result.output == 'Offline final answer after tool execution.'
    assert result.usage.requests == 3
    assert result.usage.tool_calls == 2
    assert 'Searching the reports.' in capture.getvalue()
    assert 'TOOL CALL (search): search' in capture.getvalue()
    assert 'TOOL CALL (search): get_file' in capture.getvalue()
    returns = [p.tool_name for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]
    assert returns == ['search', 'get_file']
    with contextlib.redirect_stdout(io.StringIO()):
        followup = await run_agent_stream_text(agent, 'What remains unknown?', result.all_messages())
    assert len(followup.all_messages()) > len(result.all_messages())


@pytest.mark.asyncio
async def test_graph_stream_respects_request_limit():
    async def stream(messages, info):
        yield {0: DeltaToolCall(name='search', json_args='{"query":"Akira"}', tool_call_id='s')}
    config = DocumentationAgentConfig(model=FunctionModel(stream_function=stream), request_limit=1)
    agent = create_agent(config, create_documentation_tools_cached(), output_type=str)
    with contextlib.redirect_stdout(io.StringIO()), pytest.raises(UsageLimitExceeded):
        await run_agent_stream_text(agent, 'Find evidence', config=config)
