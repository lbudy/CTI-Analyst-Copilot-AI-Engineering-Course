"""Course fixtures: opt-in live tests, shared application factory, and usage ledger."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import pytest
from pydantic_ai import models
from cost_tracker import TokenPrices, calculate_cost
from doc_agent import DocumentationAgentConfig, create_agent, DEFAULT_INSTRUCTIONS
from tools import ROOT, create_documentation_tools_cached
from tests import cost_tracker as test_costs
from tests.parallel_usage import append_rows, read_rows, worker_journal, merge_rows
from pydantic_ai.usage import RunUsage


def pytest_addoption(parser):
    parser.addoption('--agent-model', default='openai:gpt-4o-mini', help='Model for live course agent scenarios')
    parser.addoption('--judge-model', default='openai:gpt-4o-mini', help='Tool-free judge model')
    parser.addoption('--run-live', action='store_true', help='Enable paid provider-backed tests')
    parser.addoption('--input-price', type=float, default=None, help='Verified USD per million input tokens')
    parser.addoption('--output-price', type=float, default=None, help='Verified USD per million output tokens')
    parser.addoption('--cached-input-price', type=float, default=None)


def pytest_configure(config):
    worker = getattr(config, 'workerinput', {})
    config._cti_run_id = worker.get('cti_run_id', uuid.uuid4().hex)
    config._cti_worker_id = worker.get('workerid', 'master')
    if config.getoption('--run-live'):
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env')
    config._cti_usage_rows = []
    test_costs.reset_usage()
    values = [config.getoption('--input-price'), config.getoption('--output-price')]
    if (values[0] is None) != (values[1] is None):
        raise pytest.UsageError('Supply both --input-price and --output-price, or neither.')
    if config.getoption('--cached-input-price') is not None and values[0] is None:
        raise pytest.UsageError('Cached-input override requires input and output prices.')
    if values[0] is not None:
        try:
            TokenPrices(*values, config.getoption('--cached-input-price'))
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from exc


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--run-live'):
        for item in items:
            if item.get_closest_marker('live'):
                item.add_marker(pytest.mark.skip(reason='Paid test: enable explicitly with --run-live'))


@pytest.fixture(autouse=True)
def block_unrequested_provider_calls(request):
    enabled = request.node.get_closest_marker('live') and request.config.getoption('--run-live')
    with patch.object(models, 'ALLOW_MODEL_REQUESTS', bool(enabled)):
        yield


@pytest.fixture(scope='session')
def documentation_tools():
    return create_documentation_tools_cached()


@pytest.fixture(scope='module')
def agent(request):
    """One production-configured agent per test module; calls still get fresh history."""
    started = perf_counter()
    tools = create_documentation_tools_cached()
    instance = create_agent(DocumentationAgentConfig(model=request.config.getoption('--agent-model'),
                                                   instructions=DEFAULT_INSTRUCTIONS), tools)
    print(f"loading agent took {perf_counter()-started:.4f}s (module scope)")
    return instance


@pytest.fixture
def create_test_agent(documentation_tools):
    """Build the same application agent; tests can inject an offline model."""
    def factory(model='openai:gpt-4o-mini'):
        config = DocumentationAgentConfig(model=model, instructions=DEFAULT_INSTRUCTIONS)
        return create_agent(config, documentation_tools)
    return factory


@pytest.fixture(autouse=True)
def capture_usage(request):
    entries = []
    seen = {}
    def capture(model, result, *, usage_role="agent"):
        if id(result) in seen:
            return
        seen[id(result)] = result
        model = test_costs.normalize_model(model)
        usage = result.usage
        live = not model.startswith(('function:', 'test:')) and bool(request.node.get_closest_marker('live'))
        input_price = request.config.getoption('--input-price')
        prices = (TokenPrices(input_price, request.config.getoption('--output-price'),
                              request.config.getoption('--cached-input-price'))
                  if input_price is not None else test_costs.prices_for_model(model))
        entries.append({'record_id':uuid.uuid4().hex, 'run_id':request.config._cti_run_id,
            'worker_id':request.config._cti_worker_id, 'test':request.node.nodeid,
            'timestamp_utc':datetime.now(timezone.utc).isoformat(), 'model':model,
            'usage_kind':'live_provider' if live else 'offline_fixture', 'usage_role':usage_role,
            'completion_status':getattr(result,'completion_status','completed'),
            'input_tokens':usage.input_tokens, 'output_tokens':usage.output_tokens,
            'cache_read_tokens':usage.cache_read_tokens, 'requests':usage.requests,
            'tool_calls':usage.tool_calls,
            'estimated_usd':calculate_cost(usage, prices) if live and prices else None,
            'prices':vars(prices) if live and prices else None,
            'pricing_verified_on':test_costs.PRICES_VERIFIED_ON if live and prices and input_price is None else None})
    context_token = test_costs._test_context.set({'run_id':request.config._cti_run_id,
        'test':request.node.nodeid,'worker_id':request.config._cti_worker_id})
    token = test_costs._usage_sink.set(capture)
    yield capture
    test_costs._usage_sink.reset(token)
    test_costs._test_context.reset(context_token)
    request.config._cti_usage_rows.extend(entries)
    path = (worker_journal(ROOT,request.config._cti_run_id,request.config._cti_worker_id)
            if hasattr(request.config,'workerinput') else ROOT/'outputs/test_usage.jsonl')
    append_rows(path,entries)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if hasattr(config,'workerinput'):
        return
    path = ROOT/'outputs/test_usage.jsonl'
    if not path.exists():
        return
    entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    current = [e for e in entries if e['run_id']==config._cti_run_id]
    if not current:
        return
    terminalreporter.write_sep('-', 'CTI test usage (outputs/test_usage.jsonl)')
    for label, selected in [('This run',current),('Across recorded runs',entries)]:
        live = [e for e in selected if e['usage_kind']=='live_provider']
        fixtures = sum(e['usage_kind']=='offline_fixture' for e in selected)
        known = [e for e in live if e['estimated_usd'] is not None]
        terminalreporter.write_line(
            f"{label}: {len(live)} live results, {sum(e['input_tokens'] for e in live)} input / "
            f"{sum(e['output_tokens'] for e in live)} output tokens; {fixtures} offline fixtures.")
        if known:
            terminalreporter.write_line(f"Priced live estimates: ${sum(e['estimated_usd'] for e in known):.6f}")
        if len(known)<len(live):
            terminalreporter.write_line('Some live usage is unpriced; supply verified prices to estimate cost.')


def pytest_sessionfinish(session, exitstatus):
    config=session.config
    if hasattr(config,'workerinput'):
        config.workeroutput['cti_usage_rows']=config._cti_usage_rows
        return
    if getattr(config.option,'numprocesses',0):
        # The controller did not run test helpers; reconstruct per-model totals.
        test_costs.reset_usage()
        for row in config._cti_usage_rows:
            usage=RunUsage(input_tokens=row['input_tokens'],output_tokens=row['output_tokens'],
                           cache_read_tokens=row['cache_read_tokens'],requests=row['requests'],
                           tool_calls=row['tool_calls'])
            target=test_costs.usages if row['usage_kind']=='live_provider' else test_costs.fixture_usages
            target[row['model']] += usage
    reporter = config.pluginmanager.getplugin('terminalreporter')
    write = reporter.write_line if reporter is not None else print
    test_costs.display_total_usage(write, cost_rows=config._cti_usage_rows)


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node):
    node.workerinput['cti_run_id']=node.config._cti_run_id


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node,error):
    config=node.config
    rows=getattr(node,'workeroutput',{}).get('cti_usage_rows')
    if rows is None:
        # Recover completed test records if a worker ended before reporting them.
        rows=read_rows(worker_journal(ROOT,config._cti_run_id,node.gateway.id))
    previous=config._cti_usage_rows
    combined=merge_rows(previous,rows)
    old_ids={row['record_id'] for row in previous}
    append_rows(ROOT/'outputs/test_usage.jsonl',[row for row in combined if row['record_id'] not in old_ids])
    config._cti_usage_rows=combined


@pytest.fixture(scope='module')
def judge_agent(request):
    from tests.judge import create_judge_agent
    return create_judge_agent(request.config.getoption('--judge-model'))
