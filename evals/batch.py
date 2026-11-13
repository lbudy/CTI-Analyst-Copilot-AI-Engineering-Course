"""Course CSV batch evaluation, using the same graph runner as Streamlit."""
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from time import perf_counter

import pandas as pd
from evals.parallel import async_map_progress
from jaxn import JSONParserHandler
from doc_agent import AgentStreamRunner, DocumentationAgentConfig, create_agent
from tools import create_documentation_tools_cached
from tests.utils import collect_tools, get_model_name
from tests.cost_tracker import calculate_cost, PRICES_VERIFIED_ON
from evals.quality import load_cases, save_json


def load_questions(path=None):
    frame = pd.read_csv(path or Path(__file__).parent/'questions.csv', keep_default_na=False)
    if list(frame.columns) != ['question', 'group', 'type']:
        raise ValueError('CSV columns must be question,group,type in that order')
    if frame.empty or any(not str(value).strip() for value in frame.to_numpy().flatten()):
        raise ValueError('Questions, groups and types must be nonempty')
    return frame


def _turn_record(agent, result):
    usage = result.usage
    model = get_model_name(agent, result)
    return {'model':model, 'usage':vars(usage),
            'cost':calculate_cost(model, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens),
            'tools':[asdict(tool) for tool in collect_tools(result.new_messages())]}


async def run_eval_round(row, agent, *, setup_questions=(), runner_factory=AgentStreamRunner):
    """One CSV question, optionally preceded by genuine setup turns, no UI."""
    runner = runner_factory(agent, JSONParserHandler(), verbose=False)
    started = perf_counter()
    history, turns = [], []
    for prompt in [*setup_questions, row['question']]:
        try:
            result = await runner.run(prompt, history)
        except Exception as exc:
            partial = getattr(exc, 'cti_partial_result', None)
            if partial is not None:
                partial_turn = {'model':get_model_name(agent, partial), 'usage':vars(partial.usage),
                    'cost':calculate_cost(get_model_name(agent, partial), partial.usage.input_tokens,
                        partial.usage.output_tokens, partial.usage.cache_read_tokens),
                    'tools':[asdict(tool) for tool in collect_tools(getattr(exc,'cti_partial_messages',[]))]}
                turns.append(partial_turn)
            output = {'input':dict(row), 'status':'error', 'error':f'{type(exc).__name__}: {exc}',
                      'rag_response':None, 'turns':turns,
                      'tools':[tool for turn in turns for tool in turn['tools']],
                      'cost':None, 'cost_complete':False,
                      'known_cost':sum(turn['cost'] or 0 for turn in turns),
                      'latency_seconds':perf_counter()-started}
            return output
        history = result.all_messages()
        turns.append(_turn_record(agent, result))
    costs = [turn['cost'] for turn in turns]
    return {'input':dict(row), 'status':'completed', 'rag_response':result.output.model_dump(),
            'tools':[tool for turn in turns for tool in turn['tools']],
            'turns':turns, 'messages':json.loads(result.all_messages_json()),
            'cost':sum(costs) if all(value is not None for value in costs) else None,
            'cost_complete':all(value is not None for value in costs),
            'known_cost':sum(value for value in costs if value is not None),
            'latency_seconds':perf_counter()-started}


async def run_batch(frame, destination, *, agent=None, model='openai:gpt-4o-mini',
                    progress=True, setup_by_question=None, round_runner=run_eval_round, max_concurrency=4):
    """Bounded async cases; checkpoint completions and return CSV input order."""
    if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
        raise ValueError("max_concurrency must be a positive integer")
    from monitoring import configure_monitoring, new_session, session_scope
    configure_monitoring()
    capture_default_instructions = agent is None
    if agent is None:
        agent = create_agent(DocumentationAgentConfig(model=model), create_documentation_tools_cached())
    if setup_by_question is None:
        setup_by_question={case.question:case.setup_questions for case in load_cases()}
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('Use a new batch filename to preserve previous results')
    outputs = {}
    async def process(indexed_row):
        index, row = indexed_row
        session = new_session()
        try:
            with session_scope(session):
                output = await round_runner(dict(row), agent,
                    setup_questions=setup_by_question.get(row["question"], []))
        except Exception as exc:
            output={'input':dict(row),'status':'error','error':f'{type(exc).__name__}: {exc}',
                    'rag_response':None,'tools':[],'cost':None,'known_cost':0,'cost_complete':False}
        if capture_default_instructions:
            output['system_instructions']=DocumentationAgentConfig(model=model).instructions
        output['trace_context']=session['context']
        output['prices_verified_on']=PRICES_VERIFIED_ON
        output['row_index'] = index
        return index, output

    def checkpoint(completed):
        index, output = completed
        outputs[index] = output
        # Only the parent consumer writes: no worker/file races.
        save_json(destination, [outputs[key] for key in sorted(outputs)])

    await async_map_progress(enumerate(frame.to_dict('records')), process,
        max_concurrency=max_concurrency, progress=progress, on_result=checkpoint)
    return [outputs[key] for key in sorted(outputs)]


def batch_summary(outputs):
    complete=bool(outputs) and all(row.get('cost_complete',False) for row in outputs)
    return {'attempted':len(outputs), 'completed':sum(row['status']=='completed' for row in outputs),
            'errors':sum(row['status']=='error' for row in outputs),
            'known_estimated_usd':sum(row.get('known_cost',0) for row in outputs),
            'total_estimated_usd':sum(row['cost'] for row in outputs) if complete else None,
            'cost_complete':complete}


def batch_to_quality_records(outputs, cases):
    """Bridge course-shaped outputs into the existing human-labeling workflow."""
    from evals.quality import digest, RUBRIC
    catalog = {case.question:case for case in cases}
    records=[]
    seen=set()
    for output in outputs:
        question=output['input']['question']
        if question not in catalog:
            raise ValueError('Add reviewed case metadata before labeling a custom CSV question')
        if question in seen:
            raise ValueError('Duplicate CSV question; preserve one response per case in each batch')
        seen.add(question)
        record={'case':catalog[question].model_dump(), 'status':output['status'],
                'output':output.get('rag_response'), 'messages':output.get('messages',[]),
                'usage':[turn['usage'] for turn in output.get('turns',[])],
                'trace_context':output.get('trace_context',{}),
                'cost':output.get('cost'), 'rubric':RUBRIC}
        if output.get('error'):
            record['error']=output['error']
        record['record_hash']=digest(record)
        records.append(record)
    return records


async def main():
    import argparse
    from dotenv import load_dotenv
    from tools import ROOT
    parser = argparse.ArgumentParser(description='Run the course CSV batch against the CTI agent')
    parser.add_argument('--csv', type=Path, default=Path(__file__).parent/'questions.csv')
    parser.add_argument('--model', default='openai:gpt-4o-mini')
    parser.add_argument('--max-concurrency', type=int, default=4)
    parser.add_argument('--run-live', action='store_true', help='Authorize paid agent requests')
    args = parser.parse_args()
    if args.max_concurrency < 1:
        parser.error("--max-concurrency must be positive")
    frame=load_questions(args.csv)
    if not args.run_live:
        print(f'Loaded {len(frame)} questions. Add --run-live to make paid agent calls.')
        return
    load_dotenv(ROOT/'.env')
    destination=ROOT/'outputs'/f'evals_run_{datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S%f")}.json'
    outputs=await run_batch(frame,destination,model=args.model, max_concurrency=args.max_concurrency)
    summary=batch_summary(outputs)
    save_json(destination.with_suffix('.summary.json'),summary)
    print(destination)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
