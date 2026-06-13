"""Token-usage accumulator — turns LLM calls into a measured cost number.

Real adapters (DeepSeek/Claude) record usage from each API response here, so
the eval harness reports MEASURED cost-per-contract, not a guess. Offline the
counters stay zero. Prices are constants (clearly approximate, override-able)
so a stale price never silently corrupts a headline number.
"""

from __future__ import annotations

from dataclasses import dataclass

# Approximate USD per 1M tokens. Override before a run if prices have moved.
# (DeepSeek is cheap on long contracts — the reason it's the primary model.)
PRICE_PER_MTOK = {
    "deepseek-v4-flash": {"in": 0.27, "out": 1.10},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
}


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, prompt: int, completion: int) -> None:
        self.calls += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion

    def reset(self) -> None:
        self.calls = self.prompt_tokens = self.completion_tokens = 0

    def cost_usd(self, model: str) -> float:
        price = PRICE_PER_MTOK.get(model)
        if not price:
            return 0.0
        return (
            self.prompt_tokens * price["in"] + self.completion_tokens * price["out"]
        ) / 1_000_000


USAGE = Usage()
