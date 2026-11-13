"""Persistence and normalization for human evaluation; never generates labels."""
from copy import deepcopy
import json
from pathlib import Path
import os
import tempfile
from evals.quality import digest


def get_results_path(input_path):
    path=Path(input_path)
    return path.with_name(path.stem+'_results.json')


def normalize_records(raw):
    if isinstance(raw,dict) and raw and all(isinstance(v,dict) and 'all_messages' in v for v in raw.values()):
        from trace_replay import TraceData,trace_to_run_result
        converted=[]
        for trace_id,trace in raw.items():
            run=trace_to_run_result(TraceData(**trace))
            messages=json.loads(run.all_messages_json())
            from tests.utils import collect_tools
            from dataclasses import asdict
            from pydantic_ai.messages import UserPromptPart
            questions=[p.content for m in run.all_messages() for p in m.parts if isinstance(p,UserPromptPart)]
            output=run.output
            converted.append({'input':{'question':questions[-1] if questions else 'Question unavailable'},
                'rag_response':output if isinstance(output,dict) else {'answer':str(output)},
                'messages':messages,'tools':[asdict(t) for t in collect_tools(run.all_messages())],
                'trace_id':trace_id,'status':'completed','reconstructed':True,
                '_trace_source_hash':digest({'trace_id':trace_id,'trace':trace})})
        raw=converted
    if not isinstance(raw,list) or not raw:
        raise ValueError('Select a nonempty batch list or reconstructed Logfire trace archive')
    records=[]
    for original in raw:
        if not isinstance(original,dict):
            raise ValueError('Each run must be an object')
        record=deepcopy(original)
        if 'input' not in record and 'case' in record:
            record['input']={'question':record['case']['question']}
            record['rag_response']=record.get('output')
        if not isinstance(record.get('input'),dict) or not isinstance(record['input'].get('question'),str):
            raise ValueError('Each run needs input.question or case.question')
        if 'rag_response' not in record:
            raise ValueError('No response field in this file; select a batch results file')
        record.setdefault('status', 'completed' if record.get('rag_response') is not None else 'error')
        record['_source_hash']=record.pop('_trace_source_hash',None) or digest(original)
        record.update(label=None,comments='',reviewer='',failure_tags=[])
        records.append(record)
    return records


def load_records(input_path):
    records=normalize_records(json.loads(Path(input_path).read_text()))
    results_path=get_results_path(input_path)
    if results_path.exists():
        saved=json.loads(results_path.read_text())
        if not isinstance(saved,list) or len(saved)!=len(records) or any(
            a.get('_source_hash')!=b['_source_hash'] for a,b in zip(saved,records)):
            raise ValueError('Source data changed; saved labels belong to different responses. Select the original input or a new batch filename.')
        records=saved
    return records


def save_records(records,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    # Replace only after a complete write; a failed save leaves the old labels intact.
    handle,name=tempfile.mkstemp(dir=path.parent,prefix='.labels-',suffix='.tmp')
    try:
        with os.fdopen(handle,'w') as stream:
            json.dump(records,stream,indent=2,ensure_ascii=False)
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def find_next_unlabelled(data,start_index):
    for offset in range(1,len(data)+1):
        index=(start_index+offset)%len(data)
        if data[index].get('label') is None:
            return index
    return None


def export_gold_labels(records):
    """Use the exact same response hash as Section 30/31, not the UI source hash."""
    from evals.batch import batch_to_quality_records
    from evals.quality import load_cases,HumanLabel
    quality=batch_to_quality_records(records,load_cases())
    labels=[]
    for source,record in zip(records,quality):
        if source.get('label') is None or record['status']!='completed':
            continue
        record_hash = source['record_hash'] if 'case' in source and 'record_hash' in source else record['record_hash']
        labels.append(HumanLabel(case_id=record['case']['case_id'],record_hash=record_hash,
            reviewer=source['reviewer'],good=source['label']=='good',rationale=source['comments'],
            failure_tags=source.get('failure_tags',[])).model_dump())
    return labels
