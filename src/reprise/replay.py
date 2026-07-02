from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from .blobs import blob_hash
from .store import TraceStore

__all__ = ["Replayer", "ReplayMiss"]


class ReplayMiss(Exception):
    """Raised when a replayed request has no (further) recorded response."""


class Replayer:
    """Serves recorded responses back for a run, enabling deterministic re-execution.

    Matching is by request content hash and occurrence-aware: the Nth identical request during
    replay receives the Nth recorded response for that request. This is the minimal engine that
    proves a recording can be replayed byte-for-byte; interactive fork-from-step builds on it.
    """

    def __init__(self, path: Union[str, Path], run_id: Optional[str] = None, *, strict: bool = True):
        self.store = TraceStore(path)
        self.run_id = run_id or self.store.latest_run_id()
        if self.run_id is None:
            raise ValueError("no runs found in trace file")
        self.strict = strict
        self._responses: dict[str, list[str]] = {}
        for step in self.store.iter_steps(self.run_id):
            if step.request_ref and step.response_ref:
                self._responses.setdefault(step.request_ref, []).append(step.response_ref)
        self._counters: dict[str, int] = {}

    def respond(self, request: Any) -> Any:
        """Return the next recorded response for ``request``; raise ``ReplayMiss`` if none (strict)."""
        key = blob_hash(request)
        refs = self._responses.get(key, [])
        i = self._counters.get(key, 0)
        if i >= len(refs):
            if self.strict:
                raise ReplayMiss(f"no recorded response for request {key} (occurrence {i})")
            return None
        self._counters[key] = i + 1
        return self.store.get_blob(refs[i])

    def reset(self) -> None:
        """Rewind occurrence counters so the run can be replayed again from the start."""
        self._counters.clear()

    def close(self) -> None:
        self.store.close()
