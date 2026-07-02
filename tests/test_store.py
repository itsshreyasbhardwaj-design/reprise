from __future__ import annotations

import time

from reprise.schema import Run, RunStatus, Step, StepKind
from reprise.store import TraceStore


def test_blob_dedup_is_content_addressed(tmp_path):
    store = TraceStore(tmp_path / "t.reprise")
    ref1 = store.put_blob({"a": 1, "b": 2})
    ref2 = store.put_blob({"b": 2, "a": 1})  # same content, different key order
    assert ref1 == ref2
    count = store._conn.execute("SELECT COUNT(*) AS c FROM blobs").fetchone()["c"]
    assert count == 1
    assert store.get_blob(ref1) == {"a": 1, "b": 2}


def test_run_and_steps_roundtrip(tmp_path):
    store = TraceStore(tmp_path / "t.reprise")
    store.upsert_run(Run(run_id="r1", name="demo", created_at=time.time(),
                         status=RunStatus.RECORDING))
    store.put_step("r1", Step(index=0, kind=StepKind.LLM_CALL, name="llama3",
                              request_ref="sha256:x", response_ref="sha256:y"))
    store.put_step("r1", Step(index=1, kind=StepKind.MCP_TOOL_CALL, name="fs:read"))

    loaded = store.load_run("r1", with_steps=True)
    assert loaded is not None
    assert loaded.name == "demo"
    assert [s.index for s in loaded.steps] == [0, 1]
    assert loaded.steps[1].kind is StepKind.MCP_TOOL_CALL
    assert store.latest_run_id() == "r1"
