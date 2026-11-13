import json
from pathlib import Path
import pytest
from evals.labeling import load_records,save_records,get_results_path,find_next_unlabelled,export_gold_labels
from evals.quality import load_cases


def fixture_rows():
    cases=load_cases()
    return [{'input':{'question':c.question},'status':'completed',
             'rag_response':{'answer':'Review this fixture','confidence':.5,'references':[
                 {'file_path':'AA24-109A.txt','explanation':'Fixture source'}]},
             'tools':[{'name':'search','args':{'query':'fixture'}}], 'messages':[]} for c in cases[:2]]


def test_save_resume_next_and_stale_source(tmp_path):
    path=tmp_path/'batch.json';path.write_text(json.dumps(fixture_rows()))
    records=load_records(path)
    assert records[0]['label'] is None
    records[0].update(label='bad',reviewer='analyst',comments='Unsupported fixture')
    save_records(records,get_results_path(path))
    assert json.loads(path.read_text())[0].get('label') is None
    assert load_records(path)[0]['label']=='bad'
    assert find_next_unlabelled(records,0)==1
    assert export_gold_labels(records)[0]['good'] is False
    rows=fixture_rows();rows[0]['rag_response']['answer']='changed'
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='changed'):
        load_records(path)


def test_navigation_wraps_and_finishes():
    assert find_next_unlabelled([{'label':None}],0)==0
    assert find_next_unlabelled([{'label':None},{'label':'good'}],1)==0
    assert find_next_unlabelled([{'label':'good'}],0) is None


def test_label_ui_saves_advances_and_resumes(tmp_path,monkeypatch):
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    path=tmp_path/'batch.json';path.write_text(json.dumps(fixture_rows()))
    monkeypatch.setenv('CTI_EVALS_DIR',str(tmp_path))
    app_path=Path(__file__).resolve().parents[1]/'evals/label_evals.py'
    app=AppTest.from_file(app_path,default_timeout=20).run()
    assert not app.exception
    assert any('Review this fixture' in m.value for m in app.markdown)
    app.text_input(key=f'reviewer-{path}-0').set_value('Analyst One')
    app.radio[0].set_value('Not Good')
    app.text_area[0].set_value('The claim is unsupported by the evidence.')
    next(button for button in app.button if button.label=='Save Label & Next').click().run()
    assert not app.exception
    saved=json.loads(get_results_path(path).read_text())
    assert saved[0]['label']=='bad'
    assert saved[0]['reviewer']=='Analyst One'
    assert app.session_state['label_index']==1
    resumed=AppTest.from_file(app_path,default_timeout=20).run()
    assert not resumed.exception
    assert resumed.session_state['label_index']==1


def test_logfire_archive_resume_uses_stable_source_hash(tmp_path):
    trace={'all_messages':[{'role':'user','parts':[{'type':'text','content':'question'}]},
                           {'role':'assistant','parts':[{'type':'text','content':'answer'}]}],
           'input_tokens':10,'output_tokens':3}
    path=tmp_path/'traces.json';path.write_text(json.dumps({'a'*32:trace}))
    records=load_records(path)
    records[0].update(label='good',reviewer='analyst',comments='Reviewed original source')
    save_records(records,get_results_path(path))
    assert load_records(path)[0]['label']=='good'
