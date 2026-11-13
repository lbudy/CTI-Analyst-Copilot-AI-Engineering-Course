"""Course judge scenarios: English criteria, offline mechanics, opt-in real grading."""
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from tools import ROOT, load_reports
from tests.judge import assert_criteria, create_judge_agent
from tests.utils import run_agent_test
from tests.test_documentation_agent import offline_result, scripted_agent, QUESTION

TOOL_CRITERIA = [
    "Makes at least two research tool calls.",
    "Uses search before retrieving a report with get_file.",
    "Opens at least one Volt Typhoon report (AA24-038A.txt or AA23-144A.txt) with get_file.",
]


def scripted_judge(criteria, *, fail=None):
    def model(messages, info):
        payload={'criteria':[{'criterion_description':criterion,'passed':criterion!=fail,
                  'judgement':'Scripted verdict for testing assertion plumbing, not a real model evaluation.'}
                 for criterion in criteria], 'feedback':'OFFLINE judge fixture; no semantic quality was measured.'}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,payload)])
    return create_judge_agent(FunctionModel(model))


@pytest.mark.asyncio
async def test_agent_uses_tools(offline_result):
    feedback=await assert_criteria(offline_result,TOOL_CRITERIA,
                                   judge_agent=scripted_judge(TOOL_CRITERIA))
    assert len(feedback.criteria)==3


@pytest.mark.asyncio
async def test_failed_judgment_produces_actionable_assertion(offline_result):
    with pytest.raises(AssertionError,match='Uses search before'):
        await assert_criteria(offline_result,TOOL_CRITERIA,
                             judge_agent=scripted_judge(TOOL_CRITERIA,fail=TOOL_CRITERIA[1]))


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.live
async def test_live_agent_uses_tools(agent,judge_agent):
    result=await run_agent_test(agent,QUESTION)
    await assert_criteria(result,TOOL_CRITERIA,judge_agent=judge_agent)


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.live
async def test_live_off_topic_question(agent,judge_agent):
    question='What is a good recipe for chocolate cake?'
    result=await run_agent_test(agent,question)
    await assert_criteria(result,[
        "Explains that the question is outside the threat-report research scope, without requiring specific wording.",
        "Does not invent a cake recipe or claim that the threat reports support cooking advice.",
    ],judge_agent=judge_agent,question=question)


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.live
async def test_live_company_targeting_is_not_invented(agent,judge_agent):
    question=('Using AA24-038A, does the source establish that Volt Typhoon targeted RheinChem '
              'or German chemical manufacturers? Separate reported victims from unknown company exposure.')
    result=await run_agent_test(agent,question)
    report=next(r for r in load_reports() if r['report_id']=='AA24-038A')
    await assert_criteria(result,[
        "Does not claim that the advisory establishes direct targeting or compromise of RheinChem.",
        "Distinguishes reported US critical-infrastructure victims from unverified German chemical-sector targeting.",
        "Preserves the distinction between the source's assessment of intent and observed compromise.",
    ],judge_agent=judge_agent,question=question,
       evidence=[{'report_id':report['report_id'],'title':report['title'],
                  'content':report['content'][:4200]}])
