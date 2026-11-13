import json
from types import SimpleNamespace
import pytest
from trace_replay import fetch_trace, trace_to_run_result
from trace_replay.converter import _trace_data_from_rows, otel_to_model_messages


def user(text):
    return {'role':'user','parts':[{'type':'text','content':text}]}


def assistant(text):
    return {'role':'assistant','parts':[{'type':'text','content':text}]}


def test_grouped_trace_merges_cumulative_history_and_sums_usage():
    first=[user('question'),assistant('answer')]
    second=first+[user('followup'),assistant('second answer')]
    trace=_trace_data_from_rows([
        {'all_messages':json.dumps(first),'input_tokens':'10','output_tokens':'3'},
        {'all_messages':second,'input_tokens':'20','output_tokens':'4'}])
    assert trace.all_messages==second
    run=trace_to_run_result(trace)
    assert run.output=='second answer'
    assert run.usage.input_tokens==30
    assert run.usage.output_tokens==7
    assert len(run.all_messages())==4


def test_disjoint_runs_keep_repeated_questions():
    a=[user('again'),assistant('one')];b=[user('again'),assistant('two')]
    assert _trace_data_from_rows([{'all_messages':a},{'all_messages':b}]).all_messages==a+b


def test_tool_calls_and_structured_output():
    from models import RAGResponse
    payload={'answer':'Evidence','found_answer':False,'confidence':0.0,
             'confidence_explanation':'Fixture','answer_type':'reference','followup_questions':[]}
    messages=[user('question'),{'role':'assistant','parts':[{'type':'tool_call','name':'search','id':'s','arguments':{'query':'q'}}]},
              {'role':'user','parts':[{'type':'tool_call_response','name':'search','id':'s','result':'evidence'}]},
              {'role':'assistant','parts':[{'type':'tool_call','name':'final_result','id':'f','arguments':payload}]}]
    trace=_trace_data_from_rows([{'all_messages':messages}])
    run=trace_to_run_result(trace,RAGResponse)
    assert run.output.answer=='Evidence'
    assert run.all_messages()[1].parts[0].tool_call_id=='s'
    assert run.all_messages()[2].parts[0].content=='evidence'


def test_missing_content_or_unsupported_parts_fail():
    with pytest.raises(ValueError,match='content missing'):
        _trace_data_from_rows([{'all_messages':None}])
    with pytest.raises(ValueError,match='Unsupported'):
        otel_to_model_messages([{'role':'assistant','parts':[{'type':'image'}]}])


def test_query_validates_id_ascending_all_spans_and_unique_usage():
    calls=[]
    def query(**kw):
        calls.append(kw)
        row={'span_id':'s','all_messages':[user('q'),assistant('a')],'input_tokens':5}
        return {'rows':[row,row]}
    client=SimpleNamespace(query_json_rows=query)
    result=fetch_trace('a'*32,client)
    assert result.input_tokens==5
    assert 'ORDER BY start_timestamp ASC' in calls[0]['sql']
    assert 'invoke_agent %' in calls[0]['sql']
    assert calls[0]['min_timestamp'].tzinfo is not None
    with pytest.raises(ValueError,match='hexadecimal'):
        fetch_trace("' OR 1=1",client)


def test_sdk_roundtrip_preserves_text_and_tool_arguments():
    from pydantic_ai.messages import ModelRequest,ModelResponse,UserPromptPart,ToolCallPart,ToolReturnPart,TextPart
    from pydantic_ai.models.instrumented import InstrumentationSettings
    original=[ModelRequest(parts=[UserPromptPart(content='question')]),
              ModelResponse(parts=[ToolCallPart('search',{'query':'threat'},tool_call_id='s')]),
              ModelRequest(parts=[ToolReturnPart('search','evidence',tool_call_id='s')]),
              ModelResponse(parts=[TextPart('answer')])]
    otel=InstrumentationSettings().messages_to_otel_messages(original)
    restored=otel_to_model_messages(otel)
    assert restored[0].parts[0].content=='question'
    assert restored[1].parts[0].args_as_dict()=={'query':'threat'}
    assert restored[2].parts[0].content=='evidence'
    assert restored[3].parts[0].content=='answer'
