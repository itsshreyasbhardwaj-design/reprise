from __future__ import annotations

from typing import Any

from ._web import INDEX_HTML
from .cost import run_cost
from .store import TraceStore

__all__ = ["create_app", "serve"]


def create_app(path: str) -> Any:
    """Build the FastAPI app serving a single .reprise file (read-only)."""
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="Reprise", docs_url=None, redoc_url=None)
    store_path = str(path)

    def _store() -> TraceStore:
        return TraceStore(store_path)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    @app.get("/api/runs")
    def api_runs() -> list[dict]:
        store = _store()
        out = []
        for r in store.list_runs():
            steps = sum(1 for _ in store.iter_steps(r.run_id))
            out.append({
                "run_id": r.run_id, "name": r.name, "status": r.status.value,
                "created_at": r.created_at, "steps": steps,
                "parent_run_id": r.parent_run_id, "forked_from_index": r.forked_from_index,
            })
        return out

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: str) -> dict:
        store = _store()
        run = store.load_run(run_id, with_steps=True)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"run": run.model_dump(mode="json"), "cost": run_cost(run).model_dump()}

    @app.get("/api/runs/{run_id}/steps/{idx}")
    def api_step(run_id: str, idx: int) -> dict:
        store = _store()
        run = store.load_run(run_id, with_steps=True)
        if run is None or idx < 0 or idx >= len(run.steps):
            raise HTTPException(status_code=404, detail="step not found")
        step = run.steps[idx]
        return {
            "step": step.model_dump(mode="json"),
            "request": store.get_blob(step.request_ref),
            "response": store.get_blob(step.response_ref),
        }

    return app


def serve(path: str, host: str = "127.0.0.1", port: int = 7842) -> None:  # pragma: no cover
    import uvicorn

    print(f"reprise ui → http://{host}:{port}   ({path})")
    uvicorn.run(create_app(path), host=host, port=port, log_level="warning")
