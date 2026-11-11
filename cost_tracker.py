"""Explicit price inputs prevent silently reporting unknown model costs as zero."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TokenPrices:
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None = None

    def __post_init__(self):
        for value in (self.input_per_million, self.output_per_million, self.cached_input_per_million):
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError('Prices must be finite and nonnegative')


def calculate_cost(usage, prices):
    cached = usage.cache_read_tokens or 0
    inputs, outputs = usage.input_tokens or 0, usage.output_tokens or 0
    if min(cached, inputs, outputs) < 0 or cached > inputs:
        raise ValueError('Invalid token counts')
    cached_rate = prices.cached_input_per_million
    # Missing cached discount uses the full input rate: conservative estimate.
    cached_rate = prices.input_per_million if cached_rate is None else cached_rate
    return ((inputs-cached)*prices.input_per_million + cached*cached_rate
            + outputs*prices.output_per_million)/1_000_000
