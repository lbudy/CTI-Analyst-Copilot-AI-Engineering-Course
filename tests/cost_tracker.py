"""Course per-model usage accumulator; prices are dated text-token estimates."""
from collections import defaultdict
from contextvars import ContextVar
from pydantic_ai.usage import RunUsage
from cost_tracker import TokenPrices, calculate_cost as token_cost

# Standard text-token USD / 1M, verified 2026-11-12 from official model pages.
# https://developers.openai.com/api/docs/models/gpt-4o-mini
# https://developers.openai.com/api/docs/models/gpt-4o
PRICES_VERIFIED_ON = '2026-11-12'
MODEL_PRICES = {
    'openai:gpt-4o-mini': TokenPrices(.15, .60, .075),
    'openai:gpt-4o': TokenPrices(2.50, 10.00, 1.25),
}
MODEL_ALIASES = {
    'openai:gpt-4o-mini-2024-07-18': 'openai:gpt-4o-mini',
    'openai:gpt-4o-2024-08-06': 'openai:gpt-4o',
    'openai:gpt-4o-2024-11-20': 'openai:gpt-4o',
}
usages = defaultdict(RunUsage)
fixture_usages = defaultdict(RunUsage)
_usage_sink = ContextVar('cti_test_usage_sink', default=None)
_test_context = ContextVar('cti_test_context', default=None)
_seen_results = {}


def normalize_model(model):
    return model.strip().lower()


def prices_for_model(model):
    key = normalize_model(model)
    return MODEL_PRICES.get(MODEL_ALIASES.get(key, key))


def identify_model(agent, result):
    """Use the executed response, not the configured name under model overrides."""
    response = result.response
    name = response.model_name
    provider = response.provider_name
    if name and name.lower().startswith('function:'):
        return normalize_model(name)
    if provider and name:
        return normalize_model(f'{provider}:{name}')
    configured = agent.model
    if not isinstance(configured, str) and getattr(configured, 'system', None) == 'function':
        return f'function:{name or configured.model_name}'
    if isinstance(configured, str) and ':' in configured:
        provider, configured_name = configured.split(':', 1)
        # Explicitly reconcile the SDK endpoint label with the pricing provider.
        if provider in {'openai-chat', 'openai-responses'}:
            provider = 'openai'
        return normalize_model(f'{provider}:{name or configured_name}')
    return normalize_model(f'{provider or "unknown"}:{name or "unknown"}')


def calculate_cost(model_name, input_tokens, output_tokens, cached_input_tokens=0):
    prices = prices_for_model(model_name)
    if prices is None:
        return None  # Unknown models must not appear free.
    return token_cost(RunUsage(input_tokens=input_tokens, output_tokens=output_tokens,
                               cache_read_tokens=cached_input_tokens), prices)


def capture_usage(model, result, *, usage_role="agent"):
    """Automatically called by run_agent_test; notify the ledger fixture once."""
    if id(result) in _seen_results:
        return
    _seen_results[id(result)] = result
    model = normalize_model(model)
    if model.startswith(('function:', 'test:')):
        fixture_usages[model] += result.usage
    else:
        usages[model] += result.usage
    sink = _usage_sink.get()
    if sink is not None:
        sink(model, result, usage_role=usage_role)


def reset_usage():
    usages.clear()
    fixture_usages.clear()
    _seen_results.clear()


def display_total_usage(write=print, *, cost_rows=None):
    """Display current-session totals; fixture and unknown-price costs stay separate."""
    if not usages and not fixture_usages:
        return
    write('API usage by model — current test session')
    for model, usage in sorted(usages.items()):
        if cost_rows is not None:
            model_rows = [r for r in cost_rows if r['usage_kind']=='live_provider' and r['model']==model]
            cost = (sum(r['estimated_usd'] for r in model_rows)
                    if model_rows and all(r['estimated_usd'] is not None for r in model_rows) else None)
        else:
            cost = calculate_cost(model, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens)
        write(f'{model}: {usage.input_tokens} input, {usage.output_tokens} output, '
              f'{usage.cache_read_tokens} cached input; '
              + (f'estimated ${cost:.6f}' if cost is not None else 'cost unknown'))
    for model, usage in sorted(fixture_usages.items()):
        write(f'{model}: {usage.input_tokens} input, {usage.output_tokens} output '
              '(offline fixture; excluded from API cost)')
    # Rows supplied by pytest honor per-run CLI overrides instead of repricing them.
    if cost_rows is not None:
        costs = [row['estimated_usd'] for row in cost_rows if row['usage_kind']=='live_provider']
    else:
        costs = [calculate_cost(model,u.input_tokens,u.output_tokens,u.cache_read_tokens)
                 for model,u in usages.items()]
    known = sum(cost for cost in costs if cost is not None)
    if any(cost is None for cost in costs):
        write(f'Total estimated cost: unknown (priced subtotal ${known:.6f})')
    else:
        write(f'Total estimated cost: ${known:.6f}')
