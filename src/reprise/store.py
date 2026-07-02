from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional, Union

from .blobs import blob_hash, canonical_bytes
from .schema import Run, RunStatus, Step, StepError, TokenUsage

__all__ = ["TraceStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    created_at        REAL NOT NULL,
    ended_at          REAL,
    status            TEXT NOT NULL,
    parent_run_id     TEXT,
    forked_from_index INTEGER,
    meta_json         TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS steps (
    run_id       TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    request_hash TEXT,
    request_ref  TEXT,
    response_ref TEXT,
    started_at   REAL NOT NULL,
    ended_at     REAL,
    duration_ms  REAL,
    tokens_json  TEXT,
    cost         REAL,
    error_json   TEXT,
    meta_json    TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, idx),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
CREATE TABLE IF NOT EXISTS blobs (
    hash TEXT PRIMARY KEY,
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS steps_request_ref ON steps(run_id, request_ref);
"""


class TraceStore:
    """SQLite-backed storage for runs, steps, and content-addressed payload blobs.

    One ``.reprise`` file == one SQLite database == a fully portable recording.
    """

    def __init__(self, path: Union[str, Path]):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- blobs -----------------------------------------------------------
    def put_blob(self, payload: Any) -> str:
        """Store a payload content-addressed; identical payloads collapse to one row."""
        data = canonical_bytes(payload)
        ref = blob_hash(payload)
        self._conn.execute("INSERT OR IGNORE INTO blobs(hash, data) VALUES (?, ?)", (ref, data))
        return ref

    def get_blob(self, ref: Optional[str]) -> Any:
        if ref is None:
            return None
        row = self._conn.execute("SELECT data FROM blobs WHERE hash = ?", (ref,)).fetchone()
        if row is None:
            return None
        return json.loads(bytes(row["data"]).decode("utf-8"))

    # -- runs ------------------------------------------------------------
    def upsert_run(self, run: Run) -> None:
        self._conn.execute(
            """INSERT INTO runs(run_id, name, created_at, ended_at, status,
                                parent_run_id, forked_from_index, meta_json)
               VALUES (:run_id, :name, :created_at, :ended_at, :status,
                       :parent_run_id, :forked_from_index, :meta_json)
               ON CONFLICT(run_id) DO UPDATE SET
                   name=excluded.name, ended_at=excluded.ended_at, status=excluded.status,
                   parent_run_id=excluded.parent_run_id,
                   forked_from_index=excluded.forked_from_index, meta_json=excluded.meta_json""",
            {
                "run_id": run.run_id,
                "name": run.name,
                "created_at": run.created_at,
                "ended_at": run.ended_at,
                "status": run.status.value,
                "parent_run_id": run.parent_run_id,
                "forked_from_index": run.forked_from_index,
                "meta_json": json.dumps(run.meta),
            },
        )
        self._conn.commit()

    def put_step(self, run_id: str, step: Step) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO steps(run_id, idx, kind, name, request_hash, request_ref,
                                            response_ref, started_at, ended_at, duration_ms,
                                            tokens_json, cost, error_json, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                step.index,
                step.kind.value,
                step.name,
                step.request_hash,
                step.request_ref,
                step.response_ref,
                step.started_at,
                step.ended_at,
                step.duration_ms,
                json.dumps(step.tokens.model_dump()) if step.tokens else None,
                step.cost,
                json.dumps(step.error.model_dump()) if step.error else None,
                json.dumps(step.meta),
            ),
        )
        self._conn.commit()

    def load_run(self, run_id: str, with_steps: bool = False) -> Optional[Run]:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        run = Run(
            run_id=row["run_id"],
            name=row["name"],
            created_at=row["created_at"],
            ended_at=row["ended_at"],
            status=RunStatus(row["status"]),
            parent_run_id=row["parent_run_id"],
            forked_from_index=row["forked_from_index"],
            meta=json.loads(row["meta_json"]),
        )
        if with_steps:
            run.steps = list(self.iter_steps(run_id))
        return run

    def iter_steps(self, run_id: str) -> Iterator[Step]:
        cur = self._conn.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY idx ASC", (run_id,)
        )
        for row in cur:
            yield _row_to_step(row)

    def list_runs(self) -> list[Run]:
        rows = self._conn.execute("SELECT run_id FROM runs ORDER BY created_at ASC").fetchall()
        runs = [self.load_run(r["run_id"]) for r in rows]
        return [r for r in runs if r is not None]

    def latest_run_id(self) -> Optional[str]:
        row = self._conn.execute(
            "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return row["run_id"] if row else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TraceStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _row_to_step(row: sqlite3.Row) -> Step:
    tokens = json.loads(row["tokens_json"]) if row["tokens_json"] else None
    error = json.loads(row["error_json"]) if row["error_json"] else None
    return Step(
        index=row["idx"],
        kind=row["kind"],
        name=row["name"],
        request_hash=row["request_hash"],
        request_ref=row["request_ref"],
        response_ref=row["response_ref"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_ms=row["duration_ms"],
        tokens=TokenUsage(**tokens) if tokens else None,
        cost=row["cost"],
        error=StepError(**error) if error else None,
        meta=json.loads(row["meta_json"]),
    )
