from __future__ import annotations

import pytest

from reprise import Recorder, Replayer, ReplayMiss, StepKind


class _FakeCompletions:
    def __init__(self, outbox):
        self.outbox = list(outbox)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.outbox.pop(0)


class _FakeOpenAI:
    """Minimal stand-in for an OpenAI-compatible client (e.g. Ollama's endpoint)."""

    def __init__(self, outbox):
        self.chat = type("_Chat", (), {"completions": _FakeCompletions(outbox)})()


def _resp(text, prompt, completion):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                  "total_tokens": prompt + completion},
    }


def test_llm_call_replay_is_deterministic(tmp_path):
    path = tmp_path / "run.reprise"
    calls = {"n": 0}

    def live():
        calls["n"] += 1
        return _resp(f"live-{calls['n']}", 1, 1)

    rec = Recorder(path, name="agent")
    with rec.run():
        rec.llm_call({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]}, live)
        rec.llm_call({"model": "llama3", "messages": [{"role": "user", "content": "bye"}]}, live)
    assert calls["n"] == 2

    rp = Replayer(path)
    a = rp.respond({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    b = rp.respond({"model": "llama3", "messages": [{"role": "user", "content": "bye"}]})
    assert a["choices"][0]["message"]["content"] == "live-1"
    assert b["choices"][0]["message"]["content"] == "live-2"
    assert calls["n"] == 2  # served from disk; no new live calls
    with pytest.raises(ReplayMiss):
        rp.respond({"model": "llama3", "messages": [{"role": "user", "content": "unseen"}]})


def test_openai_chat_records_usage_and_steps(tmp_path):
    path = tmp_path / "run.reprise"
    client = _FakeOpenAI([_resp("A", 3, 1), _resp("B", 5, 2)])
    rec = Recorder(path, name="agent")
    with rec.run():
        rec.openai_chat(client, model="llama3", messages=[{"role": "user", "content": "q1"}])
        rec.openai_chat(client, model="llama3", messages=[{"role": "user", "content": "q2"}])

    run = rec.store.load_run(rec.run_id, with_steps=True)
    assert len(run.steps) == 2
    assert all(s.kind is StepKind.LLM_CALL for s in run.steps)
    assert run.steps[0].tokens.total == 4
    assert run.steps[1].tokens.prompt == 5
    assert run.steps[0].name == "llama3"


def test_occurrence_aware_replay_for_identical_requests(tmp_path):
    path = tmp_path / "run.reprise"
    seq = iter([_resp("first", 1, 1), _resp("second", 1, 1)])
    req = {"model": "llama3", "messages": [{"role": "user", "content": "same"}]}

    rec = Recorder(path, name="agent")
    with rec.run():
        rec.llm_call(dict(req), lambda: next(seq))
        rec.llm_call(dict(req), lambda: next(seq))

    rp = Replayer(path)
    assert rp.respond(dict(req))["choices"][0]["message"]["content"] == "first"
    assert rp.respond(dict(req))["choices"][0]["message"]["content"] == "second"
    with pytest.raises(ReplayMiss):
        rp.respond(dict(req))  # only two occurrences were recorded
