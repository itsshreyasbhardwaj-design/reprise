from __future__ import annotations

from reprise import Session
from reprise.store import TraceStore


def test_record_then_fork_diverges(tmp_path):
    base = tmp_path / "base.reprise"
    with Session.record(base, name="base") as s:
        s.llm({"model": "llama3", "messages": [{"role": "user", "content": "1"}]},
              lambda: {"choices": [{"message": {"content": "A"}}]})
        s.tool("search", {"q": "x"}, lambda: {"result": "B"})
        s.llm({"model": "llama3", "messages": [{"role": "user", "content": "3"}]},
              lambda: {"choices": [{"message": {"content": "C"}}]})

    fork = tmp_path / "fork.reprise"
    live = {"n": 0}
    with Session.fork(base, at=2, out_path=fork, name="fork") as s:
        s.llm({"model": "llama3", "messages": [{"role": "user", "content": "1"}]},
              lambda: {"choices": [{"message": {"content": "SHOULD-NOT-RUN"}}]})
        s.tool("search", {"q": "x"}, lambda: {"result": "SHOULD-NOT-RUN"})

        def live_third():
            live["n"] += 1
            return {"choices": [{"message": {"content": "C-PRIME"}}]}

        third = s.llm({"model": "llama3", "messages": [{"role": "user", "content": "3"}]}, live_third)
        assert third["choices"][0]["message"]["content"] == "C-PRIME"

    assert live["n"] == 1  # only the post-fork step ran live; the prefix was served

    store = TraceStore(fork)
    run = store.load_run(store.latest_run_id(), with_steps=True)
    assert run.parent_run_id is not None
    assert run.forked_from_index == 2
    assert len(run.steps) == 3
    assert run.steps[0].meta.get("replayed") is True
    assert run.steps[1].meta.get("replayed") is True
    assert run.steps[2].meta.get("replayed") is None  # live divergence, not replayed


def test_replay_mode_serves_without_live_calls(tmp_path):
    path = tmp_path / "r.reprise"
    with Session.record(path, name="r") as s:
        s.llm({"model": "llama3", "messages": [{"content": "q"}]}, lambda: {"out": "recorded"})

    with Session.replay(path) as s:
        got = s.llm({"model": "llama3", "messages": [{"content": "q"}]},
                    lambda: (_ for _ in ()).throw(AssertionError("live must not run in replay")))
    assert got == {"out": "recorded"}
