"""User-session cases become live judge tests; default runs validate mechanics only."""
from dataclasses import asdict
from datetime import datetime,timezone
import json
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse,ToolCallPart
from models import RAGResponse
from tools import ROOT,load_reports
from tests.judge import assert_criteria
from tests.scenarios import UserScenario,load_scenarios,assert_scenario_contract
from tests.utils import collect_tools,run_agent_test
from tests.test_pydantic_ai_course import PAYLOAD

CASES=load_scenarios()


def fixture_result(*,answer='Fixture',references=None,found=True,confidence=.5,opened=(),searched=True):
    output=RAGResponse.model_validate({**PAYLOAD,'answer':answer,'references':references or [],
                                     'found_answer':found,'confidence':confidence,
                                     'checks':[{'rule':'Fixture','passed':True,'explanation':'Offline contract fixture only.'}]})
    parts=([ToolCallPart('search',{'query':'fixture'})] if searched else [])
    parts += [ToolCallPart('get_file',{'filename':name}) for name in opened]
    messages=[ModelResponse(parts=parts)]
    return SimpleNamespace(output=output,new_messages=lambda:messages)


def test_catalog_rejects_duplicate_ids_and_conflicting_contracts(tmp_path):
    path=tmp_path/'cases.json'
    row=CASES[0].model_dump()
    path.write_text(json.dumps([row,row]))
    with pytest.raises(ValueError,match='unique case IDs'):
        load_scenarios(path)
    with pytest.raises(ValidationError):
        UserScenario.model_validate({**row,'require_empty_references':True})


@pytest.mark.parametrize('path,opened',[('invented.txt',('invented.txt',)),('AA24-038A.txt',())])
def test_reference_contract_rejects_invented_or_unopened_reports(path,opened):
    case=CASES[0]
    result=fixture_result(references=[{'file_path':path,'explanation':'Fixture'}],opened=opened)
    with pytest.raises(AssertionError):
        assert_scenario_contract(result,case,load_reports())


@pytest.mark.parametrize('found,confidence,reference',[(True,.1,False),(False,.9,False),(False,.1,True)])
def test_off_topic_contract_rejects_false_success_overconfidence_or_irrelevant_citations(found,confidence,reference):
    case=next(c for c in CASES if c.case_id=='off-topic-chess')
    references=[{'file_path':'AA24-038A.txt','explanation':'Fixture'}] if reference else []
    result=fixture_result(found=found,confidence=confidence,references=references,opened=['AA24-038A.txt'])
    with pytest.raises(AssertionError):
        assert_scenario_contract(result,case,load_reports())


def test_python_contract_checks_syntax_without_executing_code():
    case=next(c for c in CASES if c.case_id=='python-formatting')
    # This would raise if the checker executed code; AST parsing alone is safe.
    result=fixture_result(answer="```python\nraise RuntimeError('do not execute')\n```")
    assert_scenario_contract(result,case,load_reports())
    broken=fixture_result(answer='```python\ndef broken(\n```')
    with pytest.raises(AssertionError,match='invalid syntax'):
        assert_scenario_contract(broken,case,load_reports())


@pytest.mark.asyncio(loop_scope='module')
@pytest.mark.live
@pytest.mark.parametrize('scenario',CASES,ids=lambda case:case.case_id)
async def test_user_session_scenario(agent,judge_agent,scenario):
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=ROOT/'outputs/scenario_runs'/scenario.case_id/run_id
    directory.mkdir(parents=True,exist_ok=True)
    record={'case':scenario.model_dump(),'status':'running',
            'notes':'User-session wishlist; not a calibrated benchmark.'}
    path=directory/'result.json'
    path.write_text(json.dumps(record,indent=2)+'\n')
    try:
        result=await run_agent_test(agent,scenario.query)
        record.update(answer=result.output.model_dump(),
                      tool_calls=[asdict(call) for call in collect_tools(result.new_messages())])
        assert_scenario_contract(result,scenario,load_reports())
        feedback=await assert_criteria(result,scenario.criteria,judge_agent=judge_agent,question=scenario.query)
    except Exception as exc:
        record.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        messages=getattr(exc,'cti_partial_messages',None)
        if messages is not None:
            record['tool_calls']=[asdict(call) for call in collect_tools(messages)]
        partial=getattr(exc,'cti_partial_result',None)
        if partial is not None:
            record['known_partial_usage']=vars(partial.usage)
        path.write_text(json.dumps(record,indent=2)+'\n')
        raise
    else:
        record.update(status='passed',judge_feedback=feedback.model_dump())
        path.write_text(json.dumps(record,indent=2)+'\n')


@pytest.mark.parametrize('searched,opened',[(False,()),(True,('AA24-038A.txt',))])
def test_off_topic_contract_requires_search_without_unrelated_file_reads(searched,opened):
    case=next(c for c in CASES if c.case_id=='off-topic-chess')
    with pytest.raises(AssertionError):
        assert_scenario_contract(fixture_result(found=False,confidence=0,searched=searched,opened=opened),case,load_reports())
