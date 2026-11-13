"""Download the last day's CTI spans; requires a separate Logfire read token."""
import json
import argparse
import sys
from dataclasses import asdict
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from logfire.query_client import LogfireQueryClient


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    parser = argparse.ArgumentParser()
    parser.add_argument('--reconstruct', action='store_true', help='Fetch complete agent histories and build evaluation runs')
    parser.add_argument('--days', type=int, default=1)
    args = parser.parse_args()
    if args.days < 1:
        parser.error('--days must be positive')
    load_dotenv(root / '.env')
    token = os.getenv('LOGFIRE_READ_TOKEN')
    if not token:
        raise SystemExit('Set LOGFIRE_READ_TOKEN to a project read token first.')
    options = {'read_token': token}
    if os.getenv('LOGFIRE_BASE_URL'):
        options['base_url'] = os.environ['LOGFIRE_BASE_URL']
    since = datetime.now(UTC) - timedelta(days=args.days)
    with LogfireQueryClient(**options) as client:
        if args.reconstruct:
            from trace_replay import recent_trace_ids, fetch_traces, trace_to_run_result
            ids = recent_trace_ids(client, min_timestamp=since)
            traces = fetch_traces(ids, client, min_timestamp=since)
            runs = [trace_to_run_result(trace) for trace in traces.values()]
            destination = root / 'outputs/logfire_agent_traces.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({tid: asdict(trace) for tid, trace in traces.items()}, indent=2))
            print(f'Saved {len(runs)} reconstructed conversation(s) to {destination}')
            return
        rows = client.query_json_rows(
            "SELECT * FROM records WHERE service_name = 'cti-analyst-copilot' ORDER BY start_timestamp",
            min_timestamp=since, limit=10000)
    destination = root / 'outputs/logfire_traces.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(rows, default=str, indent=2))
    print(f'Saved trace data to {destination}')


if __name__ == '__main__':
    main()
