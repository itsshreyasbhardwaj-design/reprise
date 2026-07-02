from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Optional

from .capture import Recorder
from .replay import Replayer
from .schema import RunStatus, StepKind

__all__ = ["Session", "Mode"]


class Mode(str, Enum):
    RECORD = "record"
    REPLAY = "replay"
    FORK = "fork"


def _model(request: Any) -> str:
    if isinstance(request, dict) and request.get("model"):
        return request["model"]
    return "llm"


class Session:
    """Drives an agent under one of three modes with a single call surface.

    * ``record`` — every call runs live and is recorded.
    * ``replay`` — every call is served from a recording; no live calls happen.
    * ``fork``  — calls before the fork index are served from a recording (a deterministic
      prefix that rebuilds agent state), then calls diverge and run live, recorded into a new run.

    Use it as a context manager so the run's start/finish and status are handled for you::

        with Session.record("agent.reprise") as s:
            out = s.llm(request, lambda: client.chat.completions.create(**request))
    """

    def __init__(self, mode: Mode, *, recorder: Optional[Recorder] = None,
                 replayer: Optional[Replayer] = None, fork_at: Optional[int] = None):
        self.mode = mode
        self._rec = recorder
        self._replay = replayer
        self._fork_at = fork_at
        self._parent_run_id: Optional[str] = None
        self._idx = 0

    # -- constructors ----------------------------------------------------
    @classmethod
    def record(cls, path, name: str = "run", meta: Optional[dict] = None,
               *, budget=None, prices=None) -> "Session":
        return cls(Mode.RECORD,
                   recorder=Recorder(path, name=name, meta=meta, budget=budget, prices=prices))

    @classmethod
    def replay(cls, path, run_id: Optional[str] = None, *, strict: bool = True) -> "Session":
        return cls(Mode.REPLAY, replayer=Replayer(path, run_id=run_id, strict=strict))

    @classmethod
    def fork(cls, src_path, at: int, out_path, *, run_id: Optional[str] = None,
             name: Optional[str] = None, meta: Optional[dict] = None,
             budget=None, prices=None) -> "Session":
        replayer = Replayer(src_path, run_id=run_id, strict=True)
        session = cls(
            Mode.FORK,
            recorder=Recorder(out_path, name=name or "fork", meta=meta, budget=budget, prices=prices),
            replayer=replayer,
            fork_at=at,
        )
        session._parent_run_id = replayer.run_id
        return session

    # -- lifecycle -------------------------------------------------------
    def __enter__(self) -> "Session":
        if self._rec is not None:
            self._rec.begin()
            if self.mode is Mode.FORK and self._rec.run_id is not None:
                run = self._rec.store.load_run(self._rec.run_id)
                if run is not None:
                    run.parent_run_id = self._parent_run_id
                    run.forked_from_index = self._fork_at
                    self._rec.store.upsert_run(run)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._rec is not None:
            self._rec.finish(RunStatus.FAILED if exc_type else RunStatus.COMPLETED)
        if self._replay is not None:
            self._replay.close()
        return False

    @property
    def run_id(self) -> Optional[str]:
        if self._rec is not None:
            return self._rec.run_id
        return self._replay.run_id if self._replay is not None else None

    # -- unified call surface -------------------------------------------
    def llm(self, request, live_fn, *, name: Optional[str] = None,
            extract_usage=None, cost: Optional[float] = None):
        return self._dispatch(
            StepKind.LLM_CALL, name or _model(request), request,
            live=lambda: self._rec.llm_call(request, live_fn, name=name,
                                            extract_usage=extract_usage, cost=cost),
        )

    def tool(self, name: str, request, live_fn):
        return self._dispatch(
            StepKind.TOOL_CALL, name, request,
            live=lambda: self._rec.tool_call(name, request, live_fn),
        )

    def mcp(self, server: str, tool: str, request, live_fn):
        label = f"{server}:{tool}"
        return self._dispatch(
            StepKind.MCP_TOOL_CALL, label, request,
            live=lambda: self._rec.tool_call(label, request, live_fn, kind=StepKind.MCP_TOOL_CALL),
        )

    def _dispatch(self, kind: StepKind, name: str, request, *, live: Callable[[], Any]):
        i = self._idx
        self._idx += 1
        if self.mode is Mode.REPLAY:
            return self._replay.respond(request)
        if self.mode is Mode.FORK and i < (self._fork_at or 0):
            served = self._replay.respond(request)
            self._rec._record(kind, name, request, served, meta={"replayed": True})
            return served
        return live()
