from contextlib import nullcontext
import asyncio
import json
import pandas as pd
import pytest
from evals.run_evals_synthetic import load_generated_questions,run_synthetic_batch


def test_load_csv_preserves_reference_and_honors_limit(tmp_path):
    path=tmp_path/'questions.csv'
    pd.DataFrame([{'question':q,'reference_answer':'Reference','line_number_start':1,'line_number_end':2,
                   'question_type':'direct_inquirer','filename':'report.txt'} for q in ['q1','q2']]).to_csv(path,index=False)
    rows=load_generated_questions(path,1)
    assert len(rows)==1 and rows[0]['reference_answer']=='Reference'
    with pytest.raises(ValueError,match='positive'):
        load_generated_questions(path,0)


@pytest.mark.asyncio
async def test_fresh_agents_shared_tools_full_rows_and_continued_errors(tmp_path,monkeypatch):
    import monitoring
    monkeypatch.setattr(monitoring,'configure_monitoring',lambda:None)
    monkeypatch.setattr(monitoring,'new_session',lambda:{'context':{}})
    monkeypatch.setattr(monitoring,'session_scope',lambda _:nullcontext())
    tools=object();agents=[];seen=[]
    def factory(shared):
        assert shared is tools
        agent=object();agents.append(agent);return agent
    async def run(agent,row):
        seen.append(agent)
        if row['question']=='bad':raise RuntimeError('fixture error')
        await asyncio.sleep(.01)
        return {'input':row,'status':'completed','rag_response':{'answer':'answer'},'tools':[],
                'cost':.01,'known_cost':.01,'cost_complete':True,
                'turns':[{'usage':{'input_tokens':10,'output_tokens':2},'cost':.01}]}
    rows=[{'question':q,'reference_answer':'SECRET_REFERENCE'} for q in ['good','bad']]
    output=tmp_path/'run_synthetic.json'
    results,summary=await run_synthetic_batch(rows,output,search_tools=tools,agent_factory=factory,
        round_runner=run,concurrency=5,progress=False)
    assert len(set(agents))==2 and set(seen)==set(agents)
    assert results[0]['input']['reference_answer']=='SECRET_REFERENCE'
    assert results[1]['status']=='error'
    assert results[1]['cost'] is None
    assert summary['errors']==1
    assert summary['cost_accumulator']['input_tokens']==10
    assert summary['total_estimated_usd'] is None
    assert json.loads(output.read_text())==results
    assert output.with_suffix('.summary.json').exists()
