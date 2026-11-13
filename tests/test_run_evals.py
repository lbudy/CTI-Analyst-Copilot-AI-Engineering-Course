import pandas as pd
import pytest
from evals.run_evals import build_report,compare_reports,run_pipeline


def entries():
    return [{'status':'completed','cost_complete':True,'input':{'question':q},'tools':[{'name':'search'}],
        'turns':[{'usage':{'input_tokens':100,'output_tokens':5,'cache_read_tokens':20},'cost':.01}]} for q in ['a','b','c']]


def test_quality_separates_errors_and_counts_costs_trajectories():
    results=entries()
    results[2].update(status='error',cost_complete=False)
    judgments=[{'status':'completed','llm_label':'good','input_tokens':20,'output_tokens':3,'estimated_usd':.002},
               {'status':'judge_error','llm_label':None}, {'status':'agent_error','llm_label':None}]
    report=build_report(results,judgments,2,3,trajectory_threshold=0)['summary']
    assert report['good']==1 and report['bad']==0
    assert report['agent_errors']==1 and report['judge_errors']==1
    assert report['good_pct_all_attempts']==pytest.approx(100/3)
    assert report['good_pct_classified']==100
    assert report['total_usd'] is None
    assert report['known_total_usd']==pytest.approx(.032)
    assert report['total_phase_wall_seconds']==5
    assert report['long_trajectories']==3


def test_comparison_requires_same_questions_judge_and_corpus():
    manifest=dict(questions_hash='q',judge_rubric_hash='j',judge_model='m',corpus_hash='c')
    old={'manifest':manifest,'summary':{'good_pct_all_attempts':50,'classified':10}}
    new={'manifest':dict(manifest),'summary':{'good_pct_all_attempts':60,'classified':10}}
    assert compare_reports(old,new)['delta_percentage_points']==10
    new['manifest']['judge_model']='different'
    with pytest.raises(ValueError,match='judge_model'):
        compare_reports(old,new)


@pytest.mark.asyncio
async def test_pipeline_saves_separate_phases_and_combined_report(tmp_path):
    async def batch(frame,destination,**kw):
        return entries()[:1]
    async def judge(records,instance,progress,on_result):
        rows=[{'status':'completed','llm_label':'good','input_tokens':20,'output_tokens':3,'estimated_usd':.002}]
        on_result(rows)
        return pd.DataFrame(rows)
    directory=tmp_path/'run'
    report=await run_pipeline(pd.DataFrame([{'question':'a','group':'g','type':'t'}]),directory,
        batch_runner=batch,judge_runner=judge,judge_factory=lambda _:object(),progress=False)
    assert report['summary']['good']==1
    assert report['summary']['total_usd']==pytest.approx(.012)
    assert (directory/'evaluation_report.json').exists()
    assert (directory/'judge_results.csv').exists()
    assert (directory/'manifest.json').exists()
