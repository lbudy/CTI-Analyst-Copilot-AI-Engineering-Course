"""Cost arithmetic, actual model identity, deduplication and offline/live separation."""
from collections import defaultdict
from types import SimpleNamespace
import pytest
from pydantic_ai.usage import RunUsage
from tests import cost_tracker as tracker


@pytest.fixture
def isolated_tracker(monkeypatch):
    monkeypatch.setattr(tracker,'usages',defaultdict(RunUsage))
    monkeypatch.setattr(tracker,'fixture_usages',defaultdict(RunUsage))
    monkeypatch.setattr(tracker,'_seen_results',{})
    token=tracker._usage_sink.set(None)
    yield tracker
    tracker._usage_sink.reset(token)


@pytest.mark.parametrize('model,expected',[('openai:gpt-4o-mini',.00024),('openai:gpt-4o',.004)])
def test_cached_input_is_counted_once_at_model_specific_price(model,expected):
    assert tracker.calculate_cost(model,1000,200,400)==pytest.approx(expected)


def test_unknown_models_are_unpriced_and_aliases_are_explicit():
    assert tracker.calculate_cost('other:unknown',1000,100) is None
    assert tracker.calculate_cost('openai:gpt-4o-mini-2024-07-18',1000,200,400)==pytest.approx(.00024)
    assert tracker.calculate_cost('openai:gpt-4o-mini-unverified',1000,100) is None


def test_capture_accumulates_models_without_counting_a_result_twice(isolated_tracker):
    first=SimpleNamespace(usage=RunUsage(input_tokens=1000,output_tokens=200))
    second=SimpleNamespace(usage=RunUsage(input_tokens=500,output_tokens=100))
    isolated_tracker.capture_usage('openai:gpt-4o-mini',first)
    isolated_tracker.capture_usage('openai:gpt-4o-mini',first)
    isolated_tracker.capture_usage('openai:gpt-4o',second)
    assert isolated_tracker.usages['openai:gpt-4o-mini'].input_tokens==1000
    assert isolated_tracker.usages['openai:gpt-4o'].input_tokens==500


def test_fixture_usage_is_never_priced_as_api_usage(isolated_tracker):
    isolated_tracker.capture_usage('function:scripted',SimpleNamespace(usage=RunUsage(input_tokens=5000,output_tokens=500)))
    printed=[]
    isolated_tracker.display_total_usage(printed.append)
    assert not isolated_tracker.usages
    assert 'Total estimated cost: $0.000000' in printed
    assert any('offline fixture; excluded' in line for line in printed)


def test_actual_override_identity_wins_over_configured_real_model():
    result=SimpleNamespace(response=SimpleNamespace(model_name='function::stream:',provider_name=None))
    agent=SimpleNamespace(model='openai:gpt-4o-mini')
    assert tracker.identify_model(agent,result).startswith('function:')
    live=SimpleNamespace(response=SimpleNamespace(model_name='gpt-4o-mini-2024-07-18',provider_name='openai'))
    assert tracker.identify_model(agent,live)=='openai:gpt-4o-mini-2024-07-18'


def test_session_report_honors_recorded_price_override(isolated_tracker):
    model='openai:gpt-4o-mini'
    isolated_tracker.capture_usage(model,SimpleNamespace(usage=RunUsage(input_tokens=1000,output_tokens=0)))
    rows=[{'usage_kind':'live_provider','model':model,'estimated_usd':.123}]
    printed=[]
    isolated_tracker.display_total_usage(printed.append,cost_rows=rows)
    assert any('estimated $0.123000' in line for line in printed)
    assert 'Total estimated cost: $0.123000' in printed


def test_unpriced_model_does_not_make_total_look_complete(isolated_tracker):
    isolated_tracker.capture_usage('unknown:model',SimpleNamespace(usage=RunUsage(input_tokens=1000)))
    printed=[]
    isolated_tracker.display_total_usage(printed.append)
    assert any('Total estimated cost: unknown' in line for line in printed)
