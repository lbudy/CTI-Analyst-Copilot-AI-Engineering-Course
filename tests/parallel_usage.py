"""Per-worker journals and controller-side deduplication for pytest-xdist."""
import json
from pathlib import Path


def append_rows(path, rows):
    if not rows:
        return
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as stream:
        stream.write(''.join(json.dumps(row)+'\n' for row in rows))


def read_rows(path):
    path=Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def worker_journal(root,run_id,worker_id):
    return Path(root)/'outputs/test_usage_workers'/run_id/f'{worker_id}.jsonl'


def merge_rows(existing,incoming):
    combined=[]
    seen=set()
    for row in [*existing,*incoming]:
        identity=row.get('record_id') or json.dumps(row,sort_keys=True)
        if identity not in seen:
            combined.append(row)
            seen.add(identity)
    return combined
