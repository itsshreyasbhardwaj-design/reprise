from __future__ import annotations

import json

from reprise import Session
from reprise.cli import main
from reprise.store import TraceStore


def _make(path, second="A2"):
    with Session.record(path, name="demo") as s:
        s.llm({"model": "gpt-4o-mini", "messages": [{"content": "1"}]},
              lambda: {"choices": [{"message": {"content": "A1"}}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 2}})
        s.tool("search", {"q": "x"}, lambda: {"r": "ok"})
        s.llm({"model": "gpt-4o-mini", "messages": [{"content": "2"}]},
              lambda: {"choices": [{"message": {"content": second}}],
                       "usage": {"prompt_tokens": 8, "completion_tokens": 3}})


def test_ls_and_show(tmp_path, capsys):
    p = tmp_path / "a.reprise"
    _make(p)
    assert main(["ls", str(p)]) == 0
    assert "demo" in capsys.readouterr().out
    assert main(["show", str(p)]) == 0
    out = capsys.readouterr().out
    assert "llm_call" in out and "search" in out


def test_show_step_dumps_payload(tmp_path, capsys):
    p = tmp_path / "a.reprise"
    _make(p)
    assert main(["show", str(p), "--step", "0"]) == 0
    out = capsys.readouterr().out
    assert "request" in out and "response" in out and "A1" in out


def test_stat_and_cost(tmp_path, capsys):
    p = tmp_path / "a.reprise"
    _make(p)
    assert main(["stat", str(p)]) == 0
    assert "est. cost" in capsys.readouterr().out
    assert main(["cost", str(p)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total_tokens"] == 23


def test_replay_check_ok(tmp_path, capsys):
    p = tmp_path / "a.reprise"
    _make(p)
    assert main(["replay", str(p)]) == 0
    assert "replayable: yes" in capsys.readouterr().out


def test_fork_creates_new_run(tmp_path, capsys):
    p = tmp_path / "a.reprise"
    _make(p)
    out_file = tmp_path / "f.reprise"
    assert main(["fork", str(p), "--at", "2", "--out", str(out_file)]) == 0
    store = TraceStore(out_file)
    run = store.load_run(store.latest_run_id(), with_steps=True)
    assert run.forked_from_index == 2 and len(run.steps) == 2


def test_diff_gate_fails_on_divergence(tmp_path, capsys):
    a, b = tmp_path / "a.reprise", tmp_path / "b.reprise"
    _make(a, second="A2")
    _make(b, second="a completely different final answer")
    rc = main(["diff", str(a), str(b), "--gate", "--threshold", "0.99"])
    out = capsys.readouterr().out
    assert "diverged at step 2" in out
    assert rc == 1
