"""Run three independent judges in bounded parallel jobs, without rerunning agents."""
import asyncio
from copy import deepcopy
from datetime import UTC,datetime
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from pydantic_ai.usage import UsageLimits
from evals.judge_checks import *
from evals.parallel import async_map_progress
from evals.quality import save_json,digest
from tests.cost_tracker import identify_model,calculate_cost


def check_summary(entries):
    summary={}
    for name,key in CHECK_KEYS:
        scores=[entry.get(key,{}) for entry in entries]
        good=sum(s.get('status')=='completed' and s.get('score')=='good' for s in scores)
        bad=sum(s.get('status')=='completed' and s.get('score')=='bad' for s in scores)
        errors=sum(s.get('status')=='error' for s in scores)
        costs=[s.get('estimated_usd') for s in scores if s.get('status')=='completed']
        summary[key]={'name':name,'attempted_entries':len(entries),'good':good,'bad':bad,
            'errors':errors,'unclassified':len(entries)-good-bad,
            'good_pct_all':100*good/len(entries) if entries else None,
            'good_pct_classified':100*good/(good+bad) if good+bad else None,
            'known_estimated_usd':sum(c for c in costs if c is not None),
            'cost_complete':not errors and all(c is not None for c in costs)}
    return summary


async def run_checks(entries,output,*,model='openai:gpt-4o-mini',concurrency=5,progress=True,judges=None):
    if not isinstance(entries,list) or not entries:
        raise ValueError('Supply a nonempty list of agent results')
    if concurrency<1:raise ValueError('concurrency must be positive')
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a new judged output filename')
    results=deepcopy(entries)
    judges=judges or {'judge_answer_correctness':create_correctness_judge(model),
        'judge_instruction_following':create_instruction_judge(model),'judge_trajectory':create_trajectory_judge(model)}
    formatters={'judge_answer_correctness':format_correctness_prompt,
        'judge_instruction_following':format_instruction_prompt,'judge_trajectory':format_trajectory_prompt}
    jobs=[(i,key) for i in range(len(results)) for _,key in CHECK_KEYS]
    async def process(job):
        index,key=job;entry=results[index];started=perf_counter()
        missing=None
        if entry.get('status')=='error' or not entry.get('rag_response'):
            missing='No completed agent response'
        elif key=='judge_answer_correctness' and not reference_data(entry).get('reference_answer'):
            missing='Reference answer unavailable'
        elif key=='judge_instruction_following' and not captured_instructions(entry):
            missing='Historical instructions unavailable; current instructions are not substituted'
        elif key=='judge_trajectory' and 'tools' not in entry:
            missing='Tool trajectory was not captured'
        if missing:return index,key,{'status':'missing','score':None,'reasoning':missing}
        try:
            judge=judges[key]
            result=await judge.run(formatters[key](entry),usage_limits=UsageLimits(request_limit=3))
            usage=result.usage; actual=identify_model(judge,result)
            verdict={**result.output.model_dump(),'status':'completed','model':actual,
                'usage':vars(usage),'estimated_usd':calculate_cost(actual,usage.input_tokens,usage.output_tokens,usage.cache_read_tokens),
                'elapsed_seconds':perf_counter()-started}
        except Exception as exc:
            verdict={'status':'error','score':None,'reasoning':f'{type(exc).__name__}: {exc}',
                     'elapsed_seconds':perf_counter()-started}
        return index,key,verdict
    def checkpoint(item):
        index,key,verdict=item
        results[index][key]=verdict
        save_json(output,results)
    await async_map_progress(jobs,process,concurrency,progress=progress,on_result=checkpoint)
    summary=check_summary(results)
    save_json(output.with_suffix('.summary.json'),summary)
    save_json(output.with_suffix('.manifest.json'),{'model':model,'concurrency':concurrency,
        'input_hash':digest(entries),'rubric_hash':digest([CORRECTNESS_INSTRUCTIONS,INSTRUCTION_FOLLOWING_INSTRUCTIONS,TRAJECTORY_INSTRUCTIONS]),
        'timestamp':datetime.now(UTC).isoformat()})
    return results,summary


async def main():
    import argparse
    from dotenv import load_dotenv
    parser=argparse.ArgumentParser(description='Three-dimensional synthetic evaluation judges')
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--concurrency',type=int,default=5)
    parser.add_argument('--model',default='openai:gpt-4o-mini')
    parser.add_argument('--run-live',action='store_true')
    args=parser.parse_args()
    path=args.data if args.data.is_absolute() else ROOT/args.data
    entries=json.loads(path.read_text())
    if not isinstance(entries,list) or not entries:parser.error('Select nonempty agent results')
    if args.concurrency<1:parser.error('Concurrency must be positive')
    if not args.run_live:
        print(f'Loaded {len(entries)} entries. Add --run-live for up to three paid judge evaluations per entry.')
        return
    load_dotenv(ROOT/'.env')
    from monitoring import configure_monitoring
    configure_monitoring()
    output=args.output or path.with_name(path.stem+'_'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')+'_judged.json')
    if not output.is_absolute():output=ROOT/output
    _,summary=await run_checks(entries,output,model=args.model,concurrency=args.concurrency)
    print(json.dumps(summary,indent=2));print(output)


if __name__=='__main__':asyncio.run(main())
