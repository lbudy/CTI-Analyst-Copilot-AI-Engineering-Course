"""Course CLI: compare independent judge verdicts with saved human labels."""
import asyncio
from datetime import UTC,datetime
import json
from pathlib import Path
import re
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

import pandas as pd
from tqdm.auto import tqdm
from pydantic_ai.usage import UsageLimits
from evals.llm_judge import create_log_judge_agent,format_judge_prompt,JudgeEvaluation,JUDGE_INSTRUCTIONS
from evals.quality import digest,save_json,load_cases
from tests.cost_tracker import calculate_cost,identify_model


async def evaluate_sample(judge,row):
    prompt=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',format_judge_prompt(row))
    result=await judge.run(prompt,usage_limits=UsageLimits(request_limit=3))
    return result.output


def calculate_metrics(frame):
    """Bad is the positive class. Unlabeled rows/errors are not negative verdicts."""
    valid=frame[frame.human_label.isin(['good','bad']) & frame.llm_label.isin(['good','bad'])]
    truth=valid.human_label.eq('bad');pred=valid.llm_label.eq('bad')
    tp=int((truth & pred).sum());fp=int((~truth & pred).sum())
    fn=int((truth & ~pred).sum());tn=int((~truth & ~pred).sum())
    def ratio(a,b):return a/b if b else None
    return {'attempted':len(frame),'compared':len(valid),'excluded':len(frame)-len(valid),
            'judge_errors':int(frame.status.eq('judge_error').sum()),
            'accuracy':ratio(tp+tn,len(valid)),'precision_bad':ratio(tp,tp+fp),
            'recall_bad':ratio(tp,tp+fn),'tp':tp,'fp':fp,'fn':fn,'tn':tn}


async def evaluate_rows(results,judge,*,progress=True,on_result=None):
    rows=[]
    rubric_hash=digest(JUDGE_INSTRUCTIONS)
    for index,row in enumerate(tqdm(results,desc='Evaluating',disable=not progress)):
        base={'row_index':index,'question':row['input']['question'],
              'llm_answer':(row.get('rag_response') or {}).get('answer',''),
              'human_label':row.get('label'),'human_comment':row.get('comments',''),
              'record_hash':digest({k:v for k,v in row.items() if k not in {'label','comments','reviewer','failure_tags'}}),
              'rubric_hash':rubric_hash,'timestamp':datetime.now(UTC).isoformat()}
        started=perf_counter()
        if row.get('status')=='error' or row.get('rag_response') is None:
            base.update(status='agent_error',llm_label=None,llm_reasoning='No completed agent response; review execution separately.')
        else:
            try:
                prompt=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',format_judge_prompt(row))
                result=await judge.run(prompt,usage_limits=UsageLimits(request_limit=3))
                output=JudgeEvaluation.model_validate(result.output)
                model=identify_model(judge,result)
                usage=result.usage
                base.update(status='completed',llm_label=output.label,llm_reasoning=output.reasoning,
                    model=model,input_tokens=usage.input_tokens,output_tokens=usage.output_tokens,
                    cached_input_tokens=usage.cache_read_tokens,
                    estimated_usd=calculate_cost(model,usage.input_tokens,usage.output_tokens,usage.cache_read_tokens))
            except Exception as exc:
                base.update(status='judge_error',llm_label=None,llm_reasoning=f'{type(exc).__name__}: {exc}')
        base['latency_seconds']=perf_counter()-started
        rows.append(base)
        if on_result is not None:
            on_result(rows)
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=['question','human_label','llm_label','status',
                                 'llm_answer','human_comment','llm_reasoning'])


def disagreement_rows(frame):
    return frame[frame.human_label.isin(['good','bad']) & frame.llm_label.isin(['good','bad']) &
                 frame.human_label.ne(frame.llm_label)]


async def main():
    import argparse
    from dotenv import load_dotenv
    parser=argparse.ArgumentParser(description='Run the CTI course LLM judge evaluation')
    parser.add_argument('--data',type=Path,required=True,help='Labeled _results.json file, relative to repository root or absolute')
    parser.add_argument('--model',default='openai:gpt-4o-mini')
    parser.add_argument('--split',choices=['calibration','holdout','all'],default='calibration')
    parser.add_argument('--run-live',action='store_true',help='Enable paid judge requests')
    args=parser.parse_args()
    path=args.data if args.data.is_absolute() else ROOT/args.data
    results=json.loads(path.read_text())
    if not isinstance(results,list) or not results:
        parser.error('Input must be a nonempty list of labeled results')
    if any(row.get('label') not in {'good','bad'} for row in results):
        parser.error('Finish manual labels first: every row must have label good or bad')
    if args.split!='all':
        split_by_question={case.question:case.split for case in load_cases()}
        if any(row['input']['question'] not in split_by_question for row in results):
            parser.error('Custom cases need reviewed split metadata; --split all explicitly evaluates without a holdout')
        results=[row for row in results if split_by_question[row['input']['question']]==args.split]
    if not results:
        parser.error('No rows match the selected split')
    print(f'Loaded {len(results)} labeled rows ({args.split}).')
    if not args.run_live:
        print('Add --run-live to make paid judge calls. No evaluation has run.')
        return
    load_dotenv(ROOT/'.env')
    from monitoring import configure_monitoring
    configure_monitoring()
    judge=create_log_judge_agent(args.model)
    prefix=path.with_name(path.stem+f'_{args.split}_{datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")}_evaluated')
    checkpoint=prefix.with_suffix('.json')
    frame=await evaluate_rows(results,judge,on_result=lambda rows:save_json(checkpoint,rows))
    frame.to_csv(prefix.with_suffix('.csv'),index=False)
    metrics=calculate_metrics(frame)
    save_json(prefix.with_suffix('.metrics.json'),metrics)
    print(json.dumps(metrics,indent=2))
    print("Confusion matrix (bad positive): actual good => predicted good TN, bad FP; actual bad => good FN, bad TP")
    print(f"Actual good: {metrics['tn']} / {metrics['fp']}; actual bad: {metrics['fn']} / {metrics['tp']}")
    print('Disagreements:')
    print(disagreement_rows(frame)[['question','human_label','human_comment','llm_label','llm_reasoning']].to_string(index=False))
    print(f'Detailed results: {prefix.with_suffix(".csv")}')


if __name__=='__main__':
    asyncio.run(main())
