"""Message inspection and formatting checks do not substitute for answer evaluation."""
from pydantic_ai.messages import ModelResponse, ModelRequest, ToolCallPart, ToolReturnPart
from tests.helpers import collect_tools, code_blocks, source_references


def test_collect_tools_preserves_names_arguments_and_excludes_results():
    messages = [ModelResponse(parts=[ToolCallPart('search','{"query":"Volt Typhoon"}',tool_call_id='s')]),
                ModelRequest(parts=[ToolReturnPart('search',content=[],tool_call_id='s')]),
                ModelResponse(parts=[ToolCallPart('get_file',{'filename':'AA24-038A.txt'},tool_call_id='f'),
                                     ToolCallPart('final_result',{'answer':'done'},tool_call_id='o')])]
    assert collect_tools(messages)==[
        {'name':'search','args':{'query':'Volt Typhoon'},'call_id':'s'},
        {'name':'get_file','args':{'filename':'AA24-038A.txt'},'call_id':'f'}]


def test_reference_check_rejects_similar_but_wrong_url():
    url='https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a'
    assert source_references(f'[Report]({url})',[url])==[url]
    assert not source_references(url+'.attacker.example',[url])
    assert code_blocks('```powershell\nwhoami\n```')==['whoami\n']
    assert not code_blocks('An answer with no code block.')


def test_course_dataclass_retains_other_real_tools_and_filters_final_output():
    from tests.utils import collect_tools as collect_records, ToolCall
    messages=[ModelResponse(parts=[
        ToolCallPart('search',{'query':'Volt Typhoon'}),
        ToolCallPart('another_registered_tool',{'value':'example'}),
        ToolCallPart('get_file',{'filename':'AA24-038A.txt'}),
        ToolCallPart('final_result',{'answer':'done'})])]
    calls=collect_records(messages)
    assert calls==[ToolCall('search',{'query':'Volt Typhoon'}),
                   ToolCall('another_registered_tool',{'value':'example'}),
                   ToolCall('get_file',{'filename':'AA24-038A.txt'})]
