from __future__ import annotations

import pytest

from reprise import Budget, BudgetExceeded, Session
from reprise.cost import run_cost, token_cost
from reprise.schema import TokenUsage
from reprise.store import TraceStore


def test_token_cost_and_local_is_free():
    assert token_cost("gpt-4o-mini", TokenUsage(prompt=1_000_000, completion=0)) == pytest.approx(0.15)
    assert token_cost("gpt-4o", TokenUsage(prompt=0, completion=1_000_000)) == pytest.approx(10.0)
    assert token_cost("llama3.2", TokenUsage(prompt=1_000_000, completion=1_000_000)) == 0.0


def test_run_cost_aggregates(tmp_path):
    path = tmp_path / "r.reprise"
    with Session.record(path, name="r") as s:
        s.llm({"model": "gpt-4o-mini", "messages": []},
              lambda: {"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}})

    store = TraceStore(path)
    run = store.load_run(store.latest_run_id(), with_steps=True)
    rc = run_cost(run)
    assert rc.total_tokens == 1_000_000
    assert rc.usd == pytest.approx(0.15, abs=1e-6)


def test_budget_kill_switch(tmp_path):
    hits = {"n": 0}
    with pytest.raises(BudgetExceeded):
        with Session.record(tmp_path / "r.reprise", name="r", budget=Budget(max_steps=2)) as s:
            for i in range(5):
                hits["n"] += 1
                s.tool(f"t{i}", {"i": i}, lambda i=i: {"ok": i})
    assert hits["n"] == 3  # the 3rd step trips the ceiling (> 2)
