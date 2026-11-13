import pytest
from evals.synthetic import (GeneratedQuestion,QuestionsResponse,GeneratedQuestions,
    add_line_numbers,create_user_prompt,validate_questions,flatten_questions,question_count)
from evals.quality import digest
from evals.llm_judge import format_judge_prompt


def question(**kw):
    return GeneratedQuestion(user_question='How did the actor get in?',reference_answer='Used a stolen account',
        line_number_start=1,line_number_end=kw.get('end',1),question_type='direct_inquirer')


def test_numbered_prompt_and_bounded_question_count():
    assert add_line_numbers('one\ntwo')=='1: one\n2: two'
    assert question_count('x'*2500)==2
    assert question_count('x'*40000)==16
    assert 'Number of questions: 2' in create_user_prompt('x'*2500)
    with pytest.raises(ValueError):create_user_prompt('short')


def test_validator_rejects_bad_ranges_duplicates_and_count():
    output=QuestionsResponse(questions=[question()])
    assert validate_questions(output,'source line',1)==output
    with pytest.raises(ValueError,match='outside'):
        validate_questions(QuestionsResponse(questions=[question(end=2)]),'source line',1)
    with pytest.raises(ValueError,match='Duplicate'):
        validate_questions(QuestionsResponse(questions=[question(),question()]),'source line',2)
    with pytest.raises(ValueError,match='exactly'):
        validate_questions(output,'source line',2)


def test_flatten_saves_exact_support_host_metadata_and_unreviewed_status():
    report={'report_id':'r','content':'source line\nsecond line','source_url':'https://example.com/report'}
    group=GeneratedQuestions(questions=[question()],filename='r.txt',source_url=report['source_url'],source_hash=digest(report['content']))
    row=flatten_questions([group],[report])[0]
    assert row['supporting_passage']=='source line'
    assert row['analyst_reviewed'] is False
    assert row['filename']=='r.txt'
    prompt=format_judge_prompt({'input':{'question':row['question']},'rag_response':{'answer':'candidate'},'synthetic_reference':row,'label':'bad','comments':'SECRET'})
    assert 'Used a stolen account' in prompt
    assert 'SECRET' not in prompt
    report['content']='changed'
    with pytest.raises(ValueError,match='changed'):
        flatten_questions([group],[report])


@pytest.mark.asyncio
async def test_reference_is_withheld_from_agent_and_added_for_judge(tmp_path,monkeypatch):
    import pandas as pd
    import evals.batch
    import evals.evaluate_judge
    import evals.llm_judge
    from evals.synthetic import evaluate_synthetic
    report={'report_id':'r','content':'source evidence','source_url':'https://example.com'}
    group=GeneratedQuestions(questions=[question()],filename='r.txt',source_url=report['source_url'],source_hash=digest(report['content']))
    rows=flatten_questions([group],[report])
    async def batch(frame,destination,**kw):
        assert list(frame.columns)==['question','group','type']
        assert kw['setup_by_question']=={}
        return [{'input':{'question':rows[0]['question']},'status':'completed',
                 'rag_response':{'answer':'candidate'},'messages':[],'tools':[]}]
    async def judge(outputs,agent,on_result):
        assert outputs[0]['synthetic_reference']['reference_answer']=='Used a stolen account'
        assert outputs[0]['synthetic_reference']['supporting_passage']=='source evidence'
        return pd.DataFrame([{'status':'completed','llm_label':'good'}])
    monkeypatch.setattr(evals.batch,'run_batch',batch)
    monkeypatch.setattr(evals.evaluate_judge,'evaluate_rows',judge)
    monkeypatch.setattr(evals.llm_judge,'create_log_judge_agent',lambda _:object())
    _,_,summary=await evaluate_synthetic(rows,[report],tmp_path/'evaluation')
    assert summary['judge_good_pct_all_attempts']==100
    assert summary['analyst_reviewed_candidates']==0
    rows[0]['supporting_passage']='invented'
    with pytest.raises(ValueError,match='differs'):
        await evaluate_synthetic(rows,[report],tmp_path/'invalid')
    assert not (tmp_path/'invalid').exists()
