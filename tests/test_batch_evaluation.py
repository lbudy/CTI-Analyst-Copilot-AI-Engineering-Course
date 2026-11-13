import json
from types import SimpleNamespace
import pandas as pd
import pytest
from pydantic_ai.messages import ModelResponse,ToolCallPart
from pydantic_ai.usage import RunUsage
from evals.batch import load_questions,run_eval_round,run_batch,batch_summary
from evals.quality import load_cases


def test_csv_matches_reviewed_cases_and_original_reference():
    frame=load_questions()
    assert list(frame.columns)==['question','group','type']
    assert len(frame)==27
    assert list(frame.question)==[case.question for case in load_cases()]
    reference=load_questions('evals/questions_course_reference.csv')
    assert len(reference)==27
    assert reference.iloc[0].question=='How do I set up LLM as a judge?'


@pytest.mark.asyncio
async def test_round_uses_real_history_normalized_tools_and_cached_cost():
    requests=[]
    result=SimpleNamespace(usage=RunUsage(input_tokens=100,output_tokens=20,cache_read_tokens=50),
        response=SimpleNamespace(model_name='gpt-4o-mini',provider_name='openai'),
        output=SimpleNamespace(model_dump=lambda:{'answer':'Fixture'}),
        all_messages=lambda:['history'],all_messages_json=lambda:b'[]',
        new_messages=lambda:[ModelResponse(parts=[ToolCallPart('search','{"query":"q"}')])])
    class Runner:
        def __init__(self,agent,handler,verbose):
            assert verbose is False
        async def run(self,prompt,history):
            requests.append((prompt,list(history)))
            return result
    output=await run_eval_round({'question':'followup','group':'g','type':'followup'},
        SimpleNamespace(model='openai:gpt-4o-mini'),setup_questions=['setup'],runner_factory=Runner)
    assert requests==[('setup',[]),('followup',['history'])]
    assert output['tools'][0]['args']=={'query':'q'}
    assert len(output['turns'])==2
    assert output['cost']==pytest.approx(.0000465)


@pytest.mark.asyncio
async def test_batch_checkpoints_continues_and_does_not_report_unknown_cost_as_free(tmp_path,monkeypatch):
    import monitoring
    from contextlib import nullcontext
    monkeypatch.setattr(monitoring,'configure_monitoring',lambda:None)
    monkeypatch.setattr(monitoring,'new_session',lambda:{'context':{}})
    monkeypatch.setattr(monitoring,'session_scope',lambda _:nullcontext())
    calls=[]
    async def fake(row,agent,setup_questions):
        calls.append(row['question'])
        if len(calls)==1:
            raise RuntimeError('fixture failure')
        return {'input':row,'status':'completed','rag_response':{'answer':'ok'},'tools':[],
                'cost':.02,'known_cost':.02,'cost_complete':True}
    frame=pd.DataFrame([{'question':'bad','group':'g','type':'t'},{'question':'good','group':'g','type':'t'}])
    path=tmp_path/'batch.json'
    outputs=await run_batch(frame,path,agent=object(),progress=False,round_runner=fake)
    assert len(json.loads(path.read_text()))==2
    summary=batch_summary(outputs)
    assert summary['errors']==1
    assert summary['completed']==1
    assert summary['known_estimated_usd']==.02
    assert summary['total_estimated_usd'] is None
    with pytest.raises(FileExistsError):
        await run_batch(frame,path,agent=object(),progress=False)


def test_batch_records_feed_existing_human_label_workflow():
    from evals.batch import batch_to_quality_records
    from evals.quality import labeling_template,validate_labels
    case=load_cases()[0]
    records=batch_to_quality_records([{'input':{'question':case.question},'status':'completed',
        'rag_response':{'answer':'fixture'},'turns':[],'messages':[]}],[case])
    labels=labeling_template(records)
    assert labels[0]['good'] is None
    labels[0].update(good=False,reviewer='analyst',rationale='Fixture review')
    assert len(validate_labels(records,labels))==1
