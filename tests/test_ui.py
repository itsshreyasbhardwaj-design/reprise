from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from reprise import Session  # noqa: E402
from reprise.server import create_app  # noqa: E402


def _make(path):
    with Session.record(path, name="ui-run") as s:
        s.llm({"model": "llama3", "messages": [{"content": "hi"}]},
              lambda: {"choices": [{"message": {"content": "yo"}}],
                       "usage": {"prompt_tokens": 3, "completion_tokens": 1}})
        s.tool("search", {"q": "x"}, lambda: {"r": "ok"})


def test_ui_api_endpoints(tmp_path):
    path = tmp_path / "a.reprise"
    _make(path)
    client = TestClient(create_app(str(path)))

    assert client.get("/").status_code == 200
    assert "Reprise" in client.get("/").text

    runs = client.get("/api/runs").json()
    assert len(runs) == 1 and runs[0]["steps"] == 2
    run_id = runs[0]["run_id"]

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["name"] == "ui-run"
    assert detail["cost"]["total_tokens"] == 4

    step = client.get(f"/api/runs/{run_id}/steps/0").json()
    assert step["response"]["choices"][0]["message"]["content"] == "yo"
    assert client.get(f"/api/runs/{run_id}/steps/99").status_code == 404
