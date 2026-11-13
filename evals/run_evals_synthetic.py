"""Course agent-only runner for questions_generated.csv; no judge calls."""
import asyncio
from datetime import UTC,datetime
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
import pandas as pd
from evals.batch import run_eval_round,batch_summary
from evals.parallel import async_map_progress
from evals.quality import save_json
from evals.run_evals import CostAccumulator
from tests.cost_tracker import PRICES_VERIFIED_ON


def load_generated_questions(path,limit=None):
    frame=pd.read_csv(path,keep_default_na=False)
    required={'question','reference_answer','line_number_start','line_number_end','question_type','filename'}
    if not required.issubset(frame.columns):
        raise ValueError('Missing required generated CSV columns: '+', '.join(sorted(required-set(frame.columns))))
    if frame.empty or any(not str(value).strip() for value in frame['question']):
        raise ValueError('CSV must contain nonempty questions')
    if any(not str(value).strip() for value in frame['reference_answer']):
        raise ValueError('Reference answers must be nonempty')
    if limit is not None:
        if limit<1:
            raise ValueError('limit must be positive')
        frame=frame.head(limit)
    return frame.where(pd.notna(frame),None).to_dict(orient='records')


async def run_agent_on_row(agent,row,cost=None):
    # Only the question reaches the agent; reference answers stay in saved input.
    result=await run_eval_round(row,agent)
    if cost is not None:
        for turn in result.get('turns',[]):
            cost.add(turn['usage'],turn.get('cost'))
        if not result['cost_complete']:
            cost.complete=False
    return result


async def run_synthetic_batch(rows,output,*,model='openai:gpt-4o-mini',concurrency=5,
                              progress=True,agent_factory=None,search_tools=None,round_runner=run_agent_on_row):
    if not rows:
        raise ValueError('Supply at least one question')
    if isinstance(concurrency,bool) or not isinstance(concurrency,int) or concurrency<1:
        raise ValueError('concurrency must be a positive integer')
    output=Path(output)
    if output.exists() or output.with_suffix('.summary.json').exists():
        raise FileExistsError('Choose a new output filename to preserve earlier results')
    from doc_agent import create_agent,DocumentationAgentConfig
    from tools import create_documentation_tools_cached
    from monitoring import configure_monitoring,new_session,session_scope
    configure_monitoring()
    search_tools=search_tools if search_tools is not None else create_documentation_tools_cached()
    capture_default_instructions = agent_factory is None
    agent_factory=agent_factory or (lambda tools:create_agent(DocumentationAgentConfig(model=model),tools))
    completed={};cost=CostAccumulator();started=perf_counter()
    async def process(indexed):
        index,row=indexed
        session=new_session()
        try:
            with session_scope(session):
                # Fresh agent/runner/history for each case; cached tools are read-only.
                agent=agent_factory(search_tools)
                result=await round_runner(agent,row)
        except Exception as exc:
            result={'input':row,'rag_response':None,'tools':[],'status':'error',
                    'error':f'{type(exc).__name__}: {exc}','cost':None,
                    'known_cost':0,'cost_complete':False,'turns':[]}
        if capture_default_instructions:
            result['system_instructions']=DocumentationAgentConfig(model=model).instructions
        result.update(row_index=index,trace_context=session['context'],prices_verified_on=PRICES_VERIFIED_ON)
        return index,result
    def checkpoint(item):
        index,result=item
        completed[index]=result
        for turn in result.get('turns',[]):
            cost.add(turn['usage'],turn.get('cost'))
        if not result.get('cost_complete',False):
            cost.complete=False
        save_json(output,[completed[i] for i in sorted(completed)])
    await async_map_progress(enumerate(rows),process,max_concurrency=concurrency,
                             progress=progress,on_result=checkpoint)
    results=[completed[i] for i in sorted(completed)]
    summary={**batch_summary(results),'cost_accumulator':cost.to_dict(),
             'elapsed_seconds':perf_counter()-started,'concurrency':concurrency,
             'model':model,'mode':'synthetic_agent_only','output':str(output)}
    save_json(output.with_suffix('.summary.json'),summary)
    print(json.dumps(summary,indent=2))
    return results,summary


async def main():
    import argparse
    from dotenv import load_dotenv
    parser=argparse.ArgumentParser(description='Run CTI agent on generated questions, without a judge')
    parser.add_argument('--questions',type=Path,default=ROOT/'evals/questions_generated.csv')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--concurrency',type=int,default=5)
    parser.add_argument('--model',default='openai:gpt-4o-mini')
    parser.add_argument('--run-live',action='store_true',help='Enable paid agent calls')
    args=parser.parse_args()
    if args.concurrency<1 or (args.limit is not None and args.limit<1):
        parser.error('Concurrency and limit must be positive')
    questions=args.questions if args.questions.is_absolute() else ROOT/args.questions
    if not questions.exists():
        parser.error('Generated CSV not found. Generate it in Section 36, then pass --questions outputs/synthetic/BATCH/questions_generated.csv')
    rows=load_generated_questions(questions,args.limit)
    print(f'Loaded {len(rows)} questions; concurrency {args.concurrency}; no judge will run.')
    if not args.run_live:
        print('Add --run-live to make paid agent calls.')
        return
    load_dotenv(ROOT/'.env')
    output=args.output or ROOT/'outputs'/f'evals_run_{datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S%f")}_synthetic.json'
    if not output.is_absolute():
        output=ROOT/output
    await run_synthetic_batch(rows,output,model=args.model,concurrency=args.concurrency)


if __name__=='__main__':
    asyncio.run(main())
