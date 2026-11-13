"""A judge cannot silently pass by dropping, duplicating or changing a criterion."""
import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from tests.judge import JudgeCriterion, JudgeFeedback, validate_criterion_coverage, assert_criteria, create_judge_agent
from tests.test_documentation_agent import offline_result, scripted_agent


def verdict(description):
    return JudgeCriterion(criterion_description=description,judgement='Fixture explanation.',passed=True)


@pytest.mark.parametrize('descriptions',[['A'],['A','A'],['A','C']])
def test_coverage_rejects_omission_duplicates_or_substitution(descriptions):
    feedback=JudgeFeedback(criteria=[verdict(d) for d in descriptions],feedback='Fixture')
    with pytest.raises(ValueError):
        validate_criterion_coverage(feedback,['A','B'])


def test_coverage_allows_reordering_and_boolean_is_strict():
    validate_criterion_coverage(JudgeFeedback(criteria=[verdict('B'),verdict('A')],feedback='Fixture'),['A','B'])
    with pytest.raises(ValidationError):
        JudgeCriterion(criterion_description='A',judgement='Fixture',passed='true')


@pytest.mark.asyncio
async def test_judge_coverage_retries_are_bounded(offline_result):
    attempts=[]
    def model(messages,info):
        attempts.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            {'criteria':[verdict('A').model_dump()],'feedback':'Omitted B on purpose.'})])
    judge=create_judge_agent(FunctionModel(model))
    with pytest.raises(UnexpectedModelBehavior,match='retries'):
        await assert_criteria(offline_result,['A','B'],judge_agent=judge)
    assert len(attempts)==3


@pytest.mark.asyncio
async def test_empty_or_duplicate_input_criteria_fail_before_model_call(offline_result):
    with pytest.raises(ValueError):
        await assert_criteria(offline_result,[])
    with pytest.raises(ValueError):
        await assert_criteria(offline_result,['A','A'])


@pytest.mark.asyncio
async def test_judge_has_no_research_tools_and_prompt_omits_large_tool_returns(offline_result):
    seen=[]
    def model(messages,info):
        assert not info.function_tools
        prompt='\n'.join(p.content for m in messages for p in m.parts
                         if p.part_kind=='user-prompt' and isinstance(p.content,str))
        seen.append(prompt)
        assert 'How does Volt Typhoon use ntdsutil' in prompt
        assert 'get_file' in prompt and 'AA24-038A.txt' in prompt
        assert 'SOURCE_WITNESS' in prompt
        assert 'The Cybersecurity and Infrastructure Security Agency (CISA), National Security Agency' not in prompt
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            {'criteria':[verdict('Formats the answer clearly.').model_dump()], 'feedback':'Offline prompt contract fixture.'})])
    await assert_criteria(offline_result,['Formats the answer clearly.'],
                          judge_agent=create_judge_agent(FunctionModel(model)),evidence=['SOURCE_WITNESS'])
    assert len(seen)==1


@pytest.mark.asyncio
async def test_plain_text_judge_input_preserves_code_and_does_not_trust_self_checks(offline_result):
    from types import SimpleNamespace
    from models import Check
    annotated=SimpleNamespace(output=offline_result.output.model_copy(update={
        'checks':[Check(rule='Formatting',passed=True,explanation='Model claims compliance.')] }),
        new_messages=offline_result.new_messages)
    def model(messages,info):
        prompt='\n'.join(p.content for m in messages for p in m.parts
                         if p.part_kind=='user-prompt' and isinstance(p.content,str))
        assert annotated.output.answer in prompt
        assert 'found_answer: True' in prompt
        assert 'self_check: [+] Formatting' in prompt
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{
            'criteria':[{'criterion_description':'Formatting meets the requested style.',
                         'judgement':'Independent judge fixture rejects the claim.', 'passed':False}],
            'feedback':'Self-check claims do not force a passing judge verdict.'})])
    with pytest.raises(AssertionError,match='Independent judge fixture rejects'):
        await assert_criteria(annotated,['Formatting meets the requested style.'],
                              judge_agent=create_judge_agent(FunctionModel(model)))
