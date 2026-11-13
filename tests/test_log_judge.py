from types import SimpleNamespace
import pandas as pd
import pytest
from pydantic_ai.usage import RunUsage
from evals.llm_judge import JudgeEvaluation,format_judge_prompt,create_log_judge_agent
from evals.evaluate_judge import calculate_metrics,evaluate_rows,disagreement_rows


def test_prompt_excludes_human_labels_comments_and_unrelated_fields():
    row={'input':{'question':'Question'},'rag_response':{'answer':'Answer'},'tools':[],
         'messages':[{'evidence':'Retrieved text'}], 'label':'bad','comments':'SECRET_HUMAN_COMMENT',
         'reviewer':'SECRET_REVIEWER'}
    prompt=format_judge_prompt(row)
    assert 'SECRET_' not in prompt
    assert 'Retrieved text' in prompt
    assert list(JudgeEvaluation.model_fields)==['reasoning','label']
    judge=create_log_judge_agent()
    assert not judge._function_toolset.tools


def test_course_bad_positive_confusion_and_undefined_metrics():
    frame=pd.DataFrame({'human_label':['bad','bad','good','good','good'],
                        'llm_label':['good','bad','bad','good','good'],'status':['completed']*5})
    metrics=calculate_metrics(frame)
    assert metrics['accuracy']==.6
    assert metrics['precision_bad']==.5
    assert metrics['recall_bad']==.5
    assert len(disagreement_rows(frame))==2
    frame=pd.DataFrame({'human_label':['good'],'llm_label':['good'],'status':['completed']})
    assert calculate_metrics(frame)['recall_bad'] is None
    assert calculate_metrics(frame)['precision_bad'] is None


@pytest.mark.asyncio
async def test_judge_failure_is_not_a_bad_prediction_and_other_rows_continue():
    calls=[];checkpoints=[]
    class Judge:
        model='function:fixture'
        async def run(self,prompt,usage_limits):
            calls.append(prompt)
            if len(calls)==1:
                raise RuntimeError('provider unavailable')
            return SimpleNamespace(output=JudgeEvaluation(reasoning='Supported refusal',label='good'),
                usage=RunUsage(input_tokens=10,output_tokens=4),
                response=SimpleNamespace(model_name='function:fixture',provider_name='function'))
    rows=[{'input':{'question':'Q'},'rag_response':{'answer':'A'},'label':'bad','comments':'human'}]*2
    frame=await evaluate_rows(rows,Judge(),progress=False,on_result=lambda rows:checkpoints.append(len(rows)))
    assert pd.isna(frame.iloc[0].llm_label)
    assert frame.iloc[0].status=='judge_error'
    assert frame.iloc[1].llm_label=='good'
    assert checkpoints==[1,2]
    metrics=calculate_metrics(frame)
    assert metrics['compared']==1
    assert metrics['judge_errors']==1
    assert metrics['accuracy']==0
    assert metrics['fn']==1
