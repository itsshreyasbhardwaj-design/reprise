from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .schema import Run, TokenUsage

__all__ = [
    "Budget",
    "BudgetExceeded",
    "RunCost",
    "DEFAULT_PRICES",
    "token_cost",
    "step_cost",
    "run_cost",
]


class BudgetExceeded(Exception):
    """Raised by a recording when a configured budget ceiling is crossed (the kill switch)."""


class Budget(BaseModel):
    """Ceilings enforced during recording. ``None`` means no limit for that dimension."""

    max_usd: Optional[float] = None
    max_tokens: Optional[int] = None
    max_steps: Optional[int] = None


# USD per 1,000,000 tokens as (prompt, completion). Local models are free. Substring-matched
# against the step's model name; override by passing your own dict where a price map is accepted.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "o3": (2.00, 8.00),
    "claude-opus": (15.00, 75.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (0.80, 4.00),
    "llama": (0.0, 0.0),
    "qwen": (0.0, 0.0),
    "mistral": (0.0, 0.0),
    "gemma": (0.0, 0.0),
    "*local*": (0.0, 0.0),
}


def _price_for(model: Optional[str], prices: dict) -> tuple[float, float]:
    if model in prices:
        return prices[model]
    name = model or ""
    for key, val in prices.items():
        if key != "*local*" and key in name:
            return val
    return prices.get("*local*", (0.0, 0.0))


def token_cost(model: Optional[str], tokens: Optional[TokenUsage],
               prices: dict = DEFAULT_PRICES) -> float:
    """USD cost of one call given its model and token usage."""
    if tokens is None:
        return 0.0
    prompt_price, completion_price = _price_for(model, prices)
    return (tokens.prompt or 0) / 1e6 * prompt_price + (tokens.completion or 0) / 1e6 * completion_price


def step_cost(step, prices: dict = DEFAULT_PRICES) -> float:
    if step.cost is not None:
        return step.cost
    return token_cost(step.name, step.tokens, prices)


class RunCost(BaseModel):
    run_id: str
    steps: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    usd: float


def run_cost(run: Run, prices: dict = DEFAULT_PRICES) -> RunCost:
    """Aggregate token usage and USD cost across a run's steps."""
    prompt = completion = 0
    usd = 0.0
    for step in run.steps:
        if step.tokens:
            prompt += step.tokens.prompt or 0
            completion += step.tokens.completion or 0
        usd += step_cost(step, prices)
    return RunCost(
        run_id=run.run_id,
        steps=len(run.steps),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        usd=round(usd, 6),
    )
