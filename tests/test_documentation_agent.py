"""First course pytest scenarios for the existing Pydantic AI CTI agent."""
import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import FunctionModel, DeltaToolCall
from models import RAGResponse
from tools import ROOT, load_reports
from tests.helpers import collect_tools, code_blocks, source_references
from tests.utils import collect_tools as collect_tool_records, ToolCall, run_agent_test

QUESTION = ('How does Volt Typhoon use ntdsutil for credential access? '
            'Quote a command from the advisory in a fenced code block and cite the original source URL. '
            'Distinguish reported behavior from a proposed hunt; do not execute commands.')
SOURCE = 'https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a'


@pytest.fixture
def scripted_agent(agent):
    import json
    payload = {'answer':'Offline fixture, not intelligence. Source: '+SOURCE+
               '\n```text\nntdsutil\n```\nThis is a quoted utility name, not an executed hunt.',
               'references':[{'file_path':'AA24-038A.txt','explanation':'Supports the reported credential-access behavior.'}],
               'found_answer':True,'confidence':.5,'confidence_explanation':'Scripted software fixture.',
               'answer_type':'explanation','followup_questions':['What remains unknown?']}
    async def stream(messages, info):
        returned = {p.tool_name for m in messages for p in m.parts if isinstance(p, ToolReturnPart)}
        if 'search' not in returned:
            yield {0:DeltaToolCall(name='search',json_args='{"query":"Volt Typhoon ntdsutil"}',tool_call_id='search')}
        elif 'get_file' not in returned:
            yield {0:DeltaToolCall(name='get_file',json_args='{"filename":"AA24-038A.txt"}',tool_call_id='file')}
        else:
            yield {0:DeltaToolCall(name=info.output_tools[0].name,json_args=json.dumps(payload),tool_call_id='output')}
    with agent.override(model=FunctionModel(stream_function=stream)):
        yield agent


@pytest.fixture
async def offline_result(scripted_agent):
    result = await run_agent_test(scripted_agent, QUESTION)
    return result


@pytest.mark.asyncio
async def test_agent_runs(offline_result):
    output = offline_result.output
    assert isinstance(output,RAGResponse)
    assert output.answer.strip()
    assert 0 <= output.confidence <= 1
    assert output.found_answer is True
    assert output.followup_questions


@pytest.mark.asyncio
async def test_agent_calls_search_then_get_file(offline_result):
    calls = collect_tools(offline_result.new_messages())
    assert [c['name'] for c in calls]==['search','get_file']
    assert calls[0]['args']['query']=='Volt Typhoon ntdsutil'
    assert calls[1]['args']['filename']=='AA24-038A.txt'


@pytest.mark.asyncio
async def test_agent_uses_tools(offline_result):
    tool_calls = collect_tool_records(offline_result.new_messages())
    assert len(tool_calls) >= 2
    assert isinstance(tool_calls[0], ToolCall)
    assert tool_calls[0].name == 'search'
    assert tool_calls[1].name == 'get_file'
    assert tool_calls[-1].name == 'get_file'
    assert all(call.name != 'final_result' for call in tool_calls)


@pytest.mark.asyncio
async def test_output_has_code_block_and_reference(offline_result):
    answer = offline_result.output.answer
    assert code_blocks(answer)
    assert source_references(answer,[SOURCE])
    # These are formatting assertions, not a correctness or grounding judgment.


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.live
async def test_live_agent_runs(agent):
    result = await run_agent_test(agent,QUESTION)
    output = result.output
    assert isinstance(output,RAGResponse)
    assert output.answer.strip()
    assert 0 <= output.confidence <= 1
    assert output.found_answer is True
    assert output.followup_questions
    calls = collect_tools(result.new_messages())
    names = [c['name'] for c in calls]
    assert 'search' in names and 'get_file' in names
    assert names.index('search') < names.index('get_file')
    fetched = {c['args'].get('filename') for c in calls if c['name']=='get_file'}
    retrieved_urls = [r['source_url'] for r in load_reports()
                      if f"{r['report_id']}.txt" in fetched]
    assert retrieved_urls, 'The agent must open a report from the actual corpus.'
    assert code_blocks(output.answer)
    assert source_references(output.answer,retrieved_urls), 'Cite a report actually opened in this run.'
    assert output.references
    assert all(reference.file_path in fetched and reference.explanation.strip()
               for reference in output.references)


@pytest.mark.asyncio
async def test_agent_includes_code_in_answer(offline_result, documentation_tools):
    blocks = code_blocks(offline_result.output.answer)
    assert blocks, 'Include a fenced source example when the question requests one.'
    source_text = documentation_tools.get_file('AA24-038A.txt')
    assert any(block.strip() and block.strip() in source_text for block in blocks)


@pytest.mark.asyncio
async def test_agent_includes_references(offline_result):
    references = offline_result.output.references
    assert references
    assert all(reference.file_path.strip() and reference.explanation.strip() for reference in references)
    assert 'AA24-038A.txt' in {reference.file_path for reference in references}
    opened = {call.args.get('filename') for call in collect_tool_records(offline_result.new_messages())
              if call.name == 'get_file'}
    assert all(reference.file_path in opened for reference in references)
