"""Course end-to-end quality pipeline: agent batch, judge, cost/time report."""
import asyncio
from dataclasses import dataclass
from datetime import UTC,datetime
from pathlib import Path
from time import perf_counter
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from evals.batch import load_questions,run_batch
from evals.evaluate_judge import evaluate_rows
from evals.llm_judge import create_log_judge_agent,JUDGE_INSTRUCTIONS
from evals.quality import digest,save_json
from tests.cost_tracker import calculate_cost


@dataclass
class CostAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    known_usd: float = 0
    complete: bool = True

    def add(self, usage, estimated_usd):
        self.input_tokens += usage.get('input_tokens',0)
        self.output_tokens += usage.get('output_tokens',0)
        self.cached_input_tokens += usage.get('cache_read_tokens',usage.get('cached_input_tokens',0))
        if estimated_usd is None:
            self.complete=False
        else:
            self.known_usd+=estimated_usd

    def to_dict(self):
        return {**vars(self),'total_usd':self.known_usd if self.complete else None}


def cost_usd(model,input_tokens,output_tokens,cached_input_tokens=0):
    return calculate_cost(model,input_tokens,output_tokens,cached_input_tokens)


def build_report(agent_results,judgments,agent_elapsed,judge_elapsed,*,trajectory_threshold=6):
    if len(agent_results)!=len(judgments):
        raise ValueError('Expected one judge result or error record per attempted agent case')
    agent_cost,judge_cost=CostAccumulator(),CostAccumulator()
    results=[]
    for entry,prediction in zip(agent_results,judgments):
        for turn in entry.get('turns',[]):
            agent_cost.add(turn['usage'],turn.get('cost'))
        if not entry.get('cost_complete',False):
            agent_cost.complete=False
        if prediction['status']=='completed':
            judge_cost.add(prediction,prediction.get('estimated_usd'))
        elif prediction['status']=='judge_error':
            judge_cost.complete=False
        tools=entry.get('tools',[])
        results.append({**entry,'judge':prediction,
                        'trajectory_length':len(tools),
                        'trajectory':[tool['name'] for tool in tools],
                        'long_trajectory':len(tools)>trajectory_threshold})
    total=len(results)
    good=sum(r['judge'].get('llm_label')=='good' and r['judge']['status']=='completed' for r in results)
    bad=sum(r['judge'].get('llm_label')=='bad' and r['judge']['status']=='completed' for r in results)
    agent_errors=sum(r.get('status')=='error' for r in results)
    judge_errors=sum(r['judge']['status']=='judge_error' for r in results)
    classified=good+bad
    ratio=lambda a,b:100*a/b if b else None
    return {'summary':{'attempted':total,'good':good,'bad':bad,'agent_errors':agent_errors,
            'judge_errors':judge_errors,'classified':classified,
            'good_pct_all_attempts':ratio(good,total),'good_pct_classified':ratio(good,classified),
            'judge_coverage_pct':ratio(classified,total),
            'long_trajectories':sum(r['long_trajectory'] for r in results),
            'trajectory_threshold':trajectory_threshold,
            'agent_cost':agent_cost.to_dict(),'judge_cost':judge_cost.to_dict(),
            'known_total_usd':agent_cost.known_usd+judge_cost.known_usd,
            'total_usd':agent_cost.known_usd+judge_cost.known_usd if agent_cost.complete and judge_cost.complete else None,
            'agent_wall_seconds':agent_elapsed,'judge_wall_seconds':judge_elapsed,
            'total_phase_wall_seconds':agent_elapsed+judge_elapsed},'results':results}


async def run_pipeline(frame,directory,*,agent_model='openai:gpt-4o-mini',judge_model='openai:gpt-4o-mini',
                       max_concurrency=4,trajectory_threshold=6,progress=True,
                       batch_runner=run_batch,judge_runner=evaluate_rows,judge_factory=create_log_judge_agent):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    from doc_agent import DEFAULT_INSTRUCTIONS,DocumentationAgentConfig
    from dataclasses import asdict
    from tools import ROOT as project_root
    manifest={'created':datetime.now(UTC).isoformat(),'agent_model':agent_model,'judge_model':judge_model,
              'agent_prompt_hash':digest(DEFAULT_INSTRUCTIONS),'judge_rubric_hash':digest(JUDGE_INSTRUCTIONS),
              'questions_hash':digest(frame.to_dict('records')),
              'corpus_hash':digest(json.loads((project_root/'data/threat_reports.json').read_text())),
              'max_concurrency':max_concurrency,'trajectory_threshold':trajectory_threshold,
              'agent_settings':asdict(DocumentationAgentConfig(model=agent_model)),
              'retrieval_code_hash':digest((project_root/'tools.py').read_text()),
              'agent_code_hash':digest((project_root/'doc_agent.py').read_text()),
              'note':'Judge-estimated correctness, not demonstrated human alignment or analyst approval.'}
    save_json(directory/'manifest.json',manifest)
    started=perf_counter()
    agent_results=await batch_runner(frame,directory/'agent_results.json',model=agent_model,
                                      max_concurrency=max_concurrency,progress=progress)
    agent_elapsed=perf_counter()-started
    judge=judge_factory(judge_model)
    started=perf_counter()
    judgments=await judge_runner(agent_results,judge,progress=progress,
        on_result=lambda rows:save_json(directory/'judge_results.json',rows))
    judge_elapsed=perf_counter()-started
    report=build_report(agent_results,judgments.to_dict('records'),agent_elapsed,judge_elapsed,
                        trajectory_threshold=trajectory_threshold)
    report['manifest']=manifest
    save_json(directory/'evaluation_report.json',report)
    judgments.to_csv(directory/'judge_results.csv',index=False)
    print(json.dumps(report['summary'],indent=2))
    return report


def compare_reports(previous,current):
    required=['questions_hash','judge_rubric_hash','judge_model','corpus_hash']
    mismatches=[key for key in required if previous['manifest'].get(key)!=current['manifest'].get(key)]
    if mismatches:
        raise ValueError('Reports differ in comparison controls: '+', '.join(mismatches))
    before=previous['summary']['good_pct_all_attempts'];after=current['summary']['good_pct_all_attempts']
    return {'previous_good_pct':before,'current_good_pct':after,
            'delta_percentage_points':after-before if before is not None and after is not None else None,
            'previous_classified':previous['summary']['classified'],
            'current_classified':current['summary']['classified'],
            'note':'Inspect coverage, errors, paired cases and stochastic variation before keeping/reverting changes.'}


async def main():
    import argparse
    from dotenv import load_dotenv
    parser=argparse.ArgumentParser(description='Run CTI agent + judge quality evaluation')
    parser.add_argument('--csv',type=Path,default=ROOT/'evals/questions.csv')
    parser.add_argument('--agent-model',default='openai:gpt-4o-mini')
    parser.add_argument('--judge-model',default='openai:gpt-4o-mini')
    parser.add_argument('--max-concurrency',type=int,default=4)
    parser.add_argument('--trajectory-threshold',type=int,default=6)
    parser.add_argument('--compare',type=Path,help='Previous evaluation_report.json')
    parser.add_argument('--run-live',action='store_true',help='Enable paid agent and judge calls')
    args=parser.parse_args()
    if args.max_concurrency<1 or args.trajectory_threshold<0:
        parser.error('Concurrency must be positive and trajectory threshold nonnegative')
    frame=load_questions(args.csv)
    print(f'Questions: {len(frame)}. Agent phase then judge phase then quality/cost/time report.')
    if not args.run_live:
        print('Add --run-live to start paid agent and judge calls.')
        return
    load_dotenv(ROOT/'.env')
    destination=ROOT/'outputs/evaluations'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
    report=await run_pipeline(frame,destination,agent_model=args.agent_model,judge_model=args.judge_model,
        max_concurrency=args.max_concurrency,trajectory_threshold=args.trajectory_threshold)
    if args.compare:
        comparison=compare_reports(json.loads(args.compare.read_text()),report)
        save_json(destination/'comparison.json',comparison)
        print(json.dumps(comparison,indent=2))
    print(f'Saved evaluation: {destination}')


if __name__=='__main__':
    asyncio.run(main())
