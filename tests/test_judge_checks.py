import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic_ai.usage import RunUsage
from evals.judge_checks import CorrectnessResult,TrajectoryResult,CHECK_KEYS,format_correctness_prompt
from evals.run_judge_checks import run_checks


@pytest.mark.asyncio
async def test_independent_checks_errors_missing_and_checkpoint(tmp_path):
    calls=[]
    class Judge:
        model='function:fixture'
        def __init__(self,key):self.key=key
        async def run(self,prompt,usage_limits):
            calls.append((self.key,prompt))
            if self.key=='judge_trajectory':raise RuntimeError('fixture provider failure')
            return SimpleNamespace(output=CorrectnessResult(reasoning='Observed evidence',score='good'),
                usage=RunUsage(input_tokens=10,output_tokens=3),
                response=SimpleNamespace(model_name='function:fixture',provider_name='function'))
    entry={'input':{'question':'Q','reference_answer':'REF'},'rag_response':{'answer':'A'},'tools':[],
           'status':'completed','label':'bad','comments':'SECRET_HUMAN_COMMENT'}
    path=tmp_path/'example_judged.json'
    results,summary=await run_checks([entry],path,judges={key:Judge(key) for _,key in CHECK_KEYS},progress=False)
    assert results[0]['judge_answer_correctness']['score']=='good'
    assert results[0]['judge_instruction_following']['status']=='missing'
    assert results[0]['judge_trajectory']['status']=='error'
    assert results[0]['judge_trajectory']['score'] is None
    assert len(calls)==2
    assert all('SECRET_HUMAN_COMMENT' not in prompt for _,prompt in calls)
    assert summary['judge_trajectory']['bad']==0
    assert json.loads(path.read_text())==results
    assert 'judge_answer_correctness' not in entry


def test_explorer_filters_errors_separately_from_bad():
    pytest.importorskip('streamlit')
    from evals.explore_judge_results import filter_entries
    entries=[{'judge_trajectory':{'score':'bad','status':'completed'}},
             {'judge_trajectory':{'score':None,'status':'error'}}]
    assert filter_entries(entries,{'judge_trajectory':'bad'})==[(0,entries[0])]
    assert filter_entries(entries,{'judge_trajectory':'error'})==[(1,entries[1])]


def test_explorer_ui_filters_and_handles_unknown_cost(tmp_path,monkeypatch):
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    entries=[]
    for score in ['good','bad']:
        entries.append({'input':{'question':score+' question','reference_answer':'Reference'},
            'rag_response':{'answer':'Agent '+score},'cost':None,'tools':[],
            **{key:{'score':score,'status':'completed','reasoning':'Reason '+score} for _,key in CHECK_KEYS}})
    (tmp_path/'test_judged.json').write_text(json.dumps(entries))
    monkeypatch.setenv('CTI_JUDGED_DIR',str(tmp_path))
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'evals/explore_judge_results.py',default_timeout=20).run()
    assert not app.exception
    app.selectbox(key='judge_answer_correctness').set_value('bad').run()
    assert not app.exception
    assert any('bad question'==text.value for text in app.markdown)
    assert not any('good question'==text.value for text in app.markdown)
