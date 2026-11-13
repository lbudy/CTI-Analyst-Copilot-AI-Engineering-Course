import pytest
from pydantic import ValidationError
from evals.quality import load_cases,digest,labeling_template,validate_labels,summarize


def record(case_id='case',good=True):
    value={'case':{'case_id':case_id,'partition':'scope','split':'holdout'},'status':'completed','output':{'answer':'fixture'}}
    value['record_hash']=digest(value)
    return value


def test_27_cases_cover_partitions_and_splits():
    cases=load_cases()
    assert len(cases)==27
    assert len({case.partition for case in cases})==9
    assert sum(case.split=='holdout' for case in cases)==9
    assert all(case.setup_questions for case in cases if case.partition=='multi-turn')


def test_template_is_not_fake_gold_and_requires_review():
    records=[record()]
    template=labeling_template(records)
    assert template[0]['good'] is None
    with pytest.raises(ValidationError):
        validate_labels(records,template)


def test_labels_are_bound_to_exact_saved_response():
    records=[record()]
    labels=[dict(case_id='case',record_hash=records[0]['record_hash'],reviewer='analyst',good=False,rationale='Unsupported claim')]
    assert len(validate_labels(records,labels))==1
    records[0]['output']['answer']='changed'
    with pytest.raises(ValueError,match='changed'):
        validate_labels(records,labels)


def test_confusion_metrics_and_missing_labels():
    records=[record('a'),record('b')]
    labels=[dict(case_id=r['case']['case_id'],record_hash=r['record_hash'],reviewer='analyst',good=i==0,rationale='Reviewed') for i,r in enumerate(records)]
    predictions=[{'case_id':r['case']['case_id'],'record_hash':r['record_hash'],'verdict':{'good':True,'rationale':'Judge result'}} for r in records]
    result=summarize(records,labels,predictions)
    assert result['judge_agreement']==.5
    assert result['false_accept_rate']==1
    assert result['human_good_rate_all_attempts']==.5
    with pytest.raises(ValueError,match='Complete human'):
        summarize(records,labels[:1],predictions)
