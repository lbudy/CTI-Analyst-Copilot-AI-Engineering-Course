"""Course pytest examples: deterministic checks plus real framework/fake model runs."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel, DeltaToolCall
from pydantic_ai.usage import RunUsage
from tools import create_documentation_tools_cached, load_reports
from models import RAGResponse
from doc_agent import DocumentationAgentConfig, create_agent, run_agent, run_agent_stream
from cost_tracker import TokenPrices, calculate_cost
from evals.evaluation import (EvalCase, JudgeVerdict, retrieval_metrics, evaluate_search,
                              validate_case_evidence, create_judge, evaluate_answers, evidently_report)
from tests.test_pydantic_ai_course import PAYLOAD, research_model


@pytest.fixture(autouse=True)
def no_paid_requests():
    with patch.object(models, 'ALLOW_MODEL_REQUESTS', False):
        yield


def cases():
    return [EvalCase.model_validate(c) for c in json.loads(Path('evals/data/retrieval_smoke.json').read_text())]


def test_hit_rate_mrr_and_duplicate_reports():
    assert retrieval_metrics(['b'], ['a', 'a', 'b']) == {'hit_rate': 1, 'reciprocal_rank': .5}
    assert retrieval_metrics(['z'], ['a'])['hit_rate'] == 0
    with pytest.raises(ValueError):
        retrieval_metrics([], [])


def test_whole_corpus_retrieval_and_evidence():
    tools = create_documentation_tools_cached()
    reports = load_reports()
    assert len(tools.file_index) == len(reports) == 13
    for case in cases():
        validate_case_evidence(case, reports)
    metrics = evaluate_search(tools, cases())
    assert metrics['hit_rate_at_k'] == 1
    assert metrics['mrr_at_k'] > .8
    bad = cases()[0].model_copy(update={'supporting_quote': 'NOT A REAL QUOTE 12345'})
    with pytest.raises(ValueError):
        validate_case_evidence(bad, reports)


@pytest.mark.parametrize('field,value', [('confidence', -0.1), ('confidence', 1.1),
    ('confidence', float('nan')), ('answer_type', 'invented'), ('unexpected', True)])
def test_response_schema_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        RAGResponse.model_validate({**PAYLOAD, field: value})


def test_cost_counts_cached_input_once():
    usage = RunUsage(input_tokens=1000, output_tokens=200, cache_read_tokens=400)
    assert calculate_cost(usage, TokenPrices(1, 2, .5)) == pytest.approx(.0012)
    with pytest.raises(ValueError):
        TokenPrices(-1, 2)


@pytest.mark.asyncio
async def test_first_async_structured_agent_and_history():
    model, calls = research_model(structured=True)
    agent = create_agent(DocumentationAgentConfig(model=model), create_documentation_tools_cached())
    result = await run_agent(agent, 'What does the Akira report say?')
    assert isinstance(result.output, RAGResponse)
    assert result.usage.tool_calls == 2
    assert result.usage.requests == 3
    result2 = await run_agent(agent, 'What evidence is missing?', result.all_messages())
    assert len(result2.all_messages()) > len(result.all_messages())


@pytest.mark.asyncio
async def test_judge_pipeline_separates_agent_and_judge_usage(tmp_path):
    model, _ = research_model(structured=True)
    agent = create_agent(DocumentationAgentConfig(model=model), create_documentation_tools_cached())
    verdict = dict(groundedness=2, correctness=2, relevance=3, citation_quality=1,
                   unsupported_claims=['Fixture output has no citations'], explanation='Offline judge fixture',
                   needs_analyst_review=True)
    def judge_model(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, verdict)])
    judge = create_judge(FunctionModel(judge_model))
    checkpoints = []
    rows = await evaluate_answers(agent, judge, cases()[:1], load_reports(), on_result=checkpoints.append)
    assert checkpoints == rows
    assert rows[0]['judge']['citation_quality'] == 1
    assert rows[0]['agent_usage']['requests'] == 3
    assert rows[0]['latency_seconds'] >= 0
    pytest.importorskip('evidently')
    report = evidently_report(rows, tmp_path/'report.html')
    assert report.is_file()


@pytest.mark.asyncio
async def test_graph_stream_completes_tools_and_structured_output():
    from structured_stream import StructuredStreamDisplay
    stage = 0
    async def stream(messages, info):
        nonlocal stage
        stage += 1
        if stage == 1:
            yield {0: DeltaToolCall(name='search', json_args='{"query":"Akira VMware"}', tool_call_id='s')}
        elif stage == 2:
            yield {0: DeltaToolCall(name='get_file', json_args='{"filename":"AA24-109A.txt"}', tool_call_id='f')}
        else:
            raw = json.dumps(PAYLOAD)
            yield {0: DeltaToolCall(name=info.output_tools[0].name, json_args=raw[:30], tool_call_id='o')}
            yield {0: DeltaToolCall(json_args=raw[30:])}
    agent = create_agent(DocumentationAgentConfig(model=FunctionModel(stream_function=stream)),
                         create_documentation_tools_cached())
    events, fields = [], []
    display = StructuredStreamDisplay(lambda name, value: fields.append((name, value)))
    async def capture(event):
        events.append(event)
        await display(event)
    result = await run_agent_stream(agent, 'Find Akira', on_event=capture)
    assert result.output.answer == PAYLOAD['answer']
    assert [e['tool'] for e in events if e['kind']=='tool-call'] == ['search', 'get_file']
    assert ''.join(v for n,v in fields if n == 'answer_chunk') == PAYLOAD['answer']

@pytest.mark.asyncio
async def test_synthetic_questions_require_real_source_quote():
    from evals.evaluation import generate_synthetic_cases
    report = load_reports()[0]
    quote = report['content'][:120]
    candidate = dict(case_id='generated-test', question='What is the report title?',
                     expected_report_ids=[report['report_id']], reference_answer=report['title'],
                     supporting_quote=quote, analyst_reviewed=True)
    def generate(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, candidate)])
    checkpoints = []
    generated, usage = await generate_synthetic_cases([report], FunctionModel(generate), on_case=checkpoints.append)
    assert checkpoints == generated
    assert generated[0].analyst_reviewed is False
    assert generated[0].supporting_quote == quote
    candidate['supporting_quote'] = 'fabricated quotation 778899'
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    with pytest.raises(UnexpectedModelBehavior, match='retries'):
        await generate_synthetic_cases([report], FunctionModel(generate))


def test_judge_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        JudgeVerdict(groundedness=5, correctness=4, relevance=4, citation_quality=4,
                     unsupported_claims=[], explanation='Invalid score')

@pytest.mark.asyncio
async def test_synthetic_generator_corrects_quote_after_validation_feedback():
    from evals.evaluation import generate_synthetic_cases
    from pydantic_ai.messages import RetryPromptPart
    report = load_reports()[0]
    attempts = []
    def generate(messages, info):
        attempts.append(messages)
        payload = dict(case_id='retry-test', question='What does the report describe?',
                       expected_report_ids=[report['report_id']], reference_answer=report['title'],
                       supporting_quote=('invented quote' if len(attempts)==1 else report['content'][:120]),
                       analyst_reviewed=False)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
    checkpoints = []
    cases, usage = await generate_synthetic_cases([report], FunctionModel(generate), on_case=checkpoints.append)
    assert len(attempts) == 2
    assert any(isinstance(part, RetryPromptPart) for msg in attempts[1] for part in msg.parts)
    assert cases[0].supporting_quote in report['content']
    assert len(checkpoints) == 1
    assert usage.requests == 2

@pytest.mark.asyncio
async def test_generator_restores_exact_source_whitespace():
    from evals.evaluation import generate_synthetic_cases
    report = {**load_reports()[0], 'content': 'Original evidence about\n\ncredential theft and persistence.'}
    def generate(messages, info):
        payload = dict(case_id='whitespace', question='What behavior is reported?',
                       expected_report_ids=[report['report_id']], reference_answer='Credential theft.',
                       supporting_quote='evidence about credential theft', analyst_reviewed=False)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
    cases, _ = await generate_synthetic_cases([report], FunctionModel(generate))
    assert cases[0].supporting_quote == 'evidence about\n\ncredential theft'
    assert cases[0].supporting_quote in report['content']

@pytest.mark.asyncio
async def test_generator_selects_source_passage_without_retyping_quote():
    from evals.evaluation import generate_synthetic_cases
    report = load_reports()[0]
    def generate(messages, info):
        payload = dict(case_id='passage-id', question='What is reported?',
                       expected_report_ids=[report['report_id']], reference_answer='Review the report.',
                       supporting_quote='', evidence_passage_id=0, analyst_reviewed=False)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
    cases, _ = await generate_synthetic_cases([report], FunctionModel(generate))
    assert cases[0].supporting_quote == report['content'][:800]
    assert 'evidence_passage_id' not in cases[0].model_dump()
