from __future__ import annotations

from reprise import Session, diff_runs
from reprise.store import TraceStore


def _record_two_step(path, second_out):
    with Session.record(path, name="r") as s:
        s.llm({"model": "llama3", "messages": [{"content": "1"}]}, lambda: {"out": "A"})
        s.llm({"model": "llama3", "messages": [{"content": "2"}]}, lambda: {"out": second_out})


def _load(path):
    store = TraceStore(path)
    return store, store.load_run(store.latest_run_id(), with_steps=True)


def test_identical_runs_have_no_divergence(tmp_path):
    a, b = tmp_path / "a.reprise", tmp_path / "b.reprise"
    _record_two_step(a, "same")
    _record_two_step(b, "same")
    sa, ra = _load(a)
    sb, rb = _load(b)
    d = diff_runs(ra, rb, sa.get_blob, sb.get_blob)
    assert d.identical
    assert d.diverged_at is None
    assert d.overall_similarity == 1.0


def test_diff_pinpoints_divergence(tmp_path):
    a, c = tmp_path / "a.reprise", tmp_path / "c.reprise"
    _record_two_step(a, "same")
    _record_two_step(c, "totally different output text")
    sa, ra = _load(a)
    sc, rc = _load(c)
    d = diff_runs(ra, rc, sa.get_blob, sc.get_blob)
    assert d.diverged_at == 1
    assert d.overall_similarity < 1.0
    assert d.steps[0].change.value == "same"
    assert d.steps[1].change.value == "changed"
