import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from contextlib import nullcontext
import pandas as pd
import pytest
from evals.parallel import async_map_progress,threaded_map_progress
from evals.batch import run_batch


@pytest.mark.asyncio
async def test_async_limits_concurrency_and_yields_completion_order():
    active=peak=0
    first_pair=asyncio.Event()
    release=asyncio.Event()
    finished=[]
    async def task(item):
        nonlocal active,peak
        active+=1;peak=max(peak,active)
        if active==2:
            first_pair.set()
        await release.wait()
        if item==0:
            await asyncio.sleep(.01)
        active-=1
        return item
    running=asyncio.create_task(async_map_progress(range(5),task,2,progress=False,on_result=finished.append))
    await asyncio.wait_for(first_pair.wait(),1)
    assert peak==2
    release.set()
    result=await running
    assert peak==2
    assert sorted(result)==list(range(5))
    assert result[0]==1
    assert finished==result


@pytest.mark.asyncio
async def test_async_failure_cancels_outstanding_tasks():
    stopped=asyncio.Event()
    entered=asyncio.Event()
    async def task(item):
        if item==0:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        await entered.wait()
        raise RuntimeError('fixture error')
    with pytest.raises(RuntimeError,match='fixture'):
        await async_map_progress([0,1],task,2,progress=False)
    assert stopped.is_set()


def test_thread_helper_order_reuse_and_exception():
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert threaded_map_progress(pool,[3,1,2],lambda value:value*2,progress=False)==[6,2,4]
        assert threaded_map_progress(pool,[4],str,progress=False)==['4']
        with pytest.raises(ZeroDivisionError):
            threaded_map_progress(pool,[1,0],lambda value:1/value,progress=False)


@pytest.mark.asyncio
async def test_parallel_batch_checkpoints_completions_and_preserves_input_order(tmp_path,monkeypatch):
    import monitoring
    monkeypatch.setattr(monitoring,'configure_monitoring',lambda:None)
    monkeypatch.setattr(monitoring,'new_session',lambda:{'context':{}})
    monkeypatch.setattr(monitoring,'session_scope',lambda _:nullcontext())
    two_started=asyncio.Event()
    completed=[]
    async def run(row,agent,setup_questions):
        if row['question']=='slow':
            await two_started.wait()
            await asyncio.sleep(.01)
        else:
            two_started.set()
        completed.append(row['question'])
        return {'input':row,'status':'completed','cost':.1,'known_cost':.1,'cost_complete':True}
    frame=pd.DataFrame([{'question':q,'group':'g','type':'t'} for q in ['slow','fast']])
    destination=tmp_path/'batch.json'
    outputs=await run_batch(frame,destination,agent=object(),round_runner=run,progress=False,max_concurrency=2)
    assert completed==['fast','slow']
    assert [row['input']['question'] for row in outputs]==['slow','fast']
    assert json.loads(destination.read_text())==outputs
    assert [row['row_index'] for row in outputs]==[0,1]


@pytest.mark.asyncio
@pytest.mark.parametrize('limit',[0,-1,True])
async def test_invalid_concurrency(limit):
    with pytest.raises(ValueError,match='positive integer'):
        await async_map_progress([],None,limit,progress=False)
