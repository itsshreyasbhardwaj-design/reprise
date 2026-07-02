from __future__ import annotations

import time
import traceback as _tb
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

from .cost import DEFAULT_PRICES, Budget, BudgetExceeded, token_cost
from .schema import Run, RunStatus, Step, StepError, StepKind, TokenUsage
from .store import TraceStore

__all__ = ["Recorder"]


class Recorder:
    """Records an agent run into a ``.reprise`` file.

    Example::

        rec = Recorder("run.reprise", name="my-agent")
        with rec.run():
            resp = rec.llm_call(request, lambda: client.create(**request))
            out = rec.tool_call("search", {"q": "x"}, lambda: do_search("x"))

    Pass ``budget=Budget(max_usd=..., max_tokens=..., max_steps=...)`` to enforce a hard ceiling:
    the offending step is still recorded, then :class:`~reprise.cost.BudgetExceeded` is raised.
    """

    def __init__(self, path: Union[str, Path], name: str = "run", meta: Optional[dict] = None,
                 *, budget: Optional[Budget] = None, prices: Optional[dict] = None):
        self.store = TraceStore(path)
        self._name = name
        self._meta = dict(meta or {})
        self._run_id: Optional[str] = None
        self._index = 0
        self._budget = budget
        self._prices = prices if prices is not None else DEFAULT_PRICES
        self._spent_steps = 0
        self._spent_tokens = 0
        self._spent_usd = 0.0

    # -- lifecycle -------------------------------------------------------
    @contextmanager
    def run(self, name: Optional[str] = None, meta: Optional[dict] = None) -> Iterator["Recorder"]:
        self.begin(name=name, meta=meta)
        try:
            yield self
        except BaseException:
            self.finish(RunStatus.FAILED)
            raise
        else:
            self.finish(RunStatus.COMPLETED)

    def begin(self, name: Optional[str] = None, meta: Optional[dict] = None) -> str:
        self._run_id = uuid.uuid4().hex
        self._index = 0
        run = Run(
            run_id=self._run_id,
            name=name or self._name,
            created_at=time.time(),
            status=RunStatus.RECORDING,
            meta={**self._meta, **(meta or {})},
        )
        self.store.upsert_run(run)
        return self._run_id

    def finish(self, status: RunStatus = RunStatus.COMPLETED) -> None:
        if self._run_id is None:
            return
        run = self.store.load_run(self._run_id)
        if run is not None:
            run.status = status
            run.ended_at = time.time()
            self.store.upsert_run(run)

    @property
    def run_id(self) -> Optional[str]:
        return self._run_id

    # -- recording primitives (sync) ------------------------------------
    def llm_call(self, request: dict[str, Any], fn: Callable[[], Any], *,
                 name: Optional[str] = None,
                 extract_usage: Optional[Callable[[Any], Optional[TokenUsage]]] = None,
                 cost: Optional[float] = None) -> Any:
        """Record one LLM call. ``fn`` performs the real call; its return value is captured."""
        label = name or (request.get("model") if isinstance(request, dict) else None) or "llm"
        started = time.time()
        try:
            result = fn()
        except Exception as exc:
            self._record(StepKind.LLM_CALL, label, request, None,
                         error=_error(exc), started=started, ended=time.time())
            raise
        usage = extract_usage(result) if extract_usage else _default_usage(result)
        self._record(StepKind.LLM_CALL, label, request, result,
                     tokens=usage, cost=cost, started=started, ended=time.time())
        return result

    def tool_call(self, name: str, request: Any, fn: Callable[[], Any], *,
                  kind: StepKind = StepKind.TOOL_CALL) -> Any:
        """Record one tool call. ``fn`` performs the real call; its return value is captured."""
        started = time.time()
        try:
            result = fn()
        except Exception as exc:
            self._record(kind, name, request, None, error=_error(exc),
                         started=started, ended=time.time())
            raise
        self._record(kind, name, request, result, started=started, ended=time.time())
        return result

    def mcp_tool_call(self, server: str, tool: str, request: Any, fn: Callable[[], Any]) -> Any:
        """Record an MCP tool call as a first-class step, named ``server:tool``."""
        return self.tool_call(f"{server}:{tool}", request, fn, kind=StepKind.MCP_TOOL_CALL)

    def event(self, name: str, payload: Any = None) -> None:
        """Record a zero-duration marker (e.g. a decision point or state snapshot)."""
        now = time.time()
        self._record(StepKind.EVENT, name, None, payload, started=now, ended=now)

    def openai_chat(self, client: Any, **kwargs: Any) -> Any:
        """Record a call to an OpenAI-compatible ``client.chat.completions.create(**kwargs)``.

        Works with the ``openai`` SDK and Ollama's OpenAI-compatible endpoint alike.
        """
        request = {"provider": "openai-compatible", "endpoint": "chat.completions", **kwargs}
        return self.llm_call(request, lambda: client.chat.completions.create(**kwargs),
                             name=kwargs.get("model"))

    # -- recording primitives (async, for async agents / MCP) -----------
    async def a_llm_call(self, request: dict[str, Any], fn: Callable[[], Any], *,
                         name: Optional[str] = None,
                         extract_usage: Optional[Callable[[Any], Optional[TokenUsage]]] = None,
                         cost: Optional[float] = None) -> Any:
        label = name or (request.get("model") if isinstance(request, dict) else None) or "llm"
        started = time.time()
        try:
            result = await fn()
        except Exception as exc:
            self._record(StepKind.LLM_CALL, label, request, None,
                         error=_error(exc), started=started, ended=time.time())
            raise
        usage = extract_usage(result) if extract_usage else _default_usage(result)
        self._record(StepKind.LLM_CALL, label, request, result,
                     tokens=usage, cost=cost, started=started, ended=time.time())
        return result

    async def a_tool_call(self, name: str, request: Any, fn: Callable[[], Any], *,
                          kind: StepKind = StepKind.TOOL_CALL) -> Any:
        started = time.time()
        try:
            result = await fn()
        except Exception as exc:
            self._record(kind, name, request, None, error=_error(exc),
                         started=started, ended=time.time())
            raise
        self._record(kind, name, request, result, started=started, ended=time.time())
        return result

    async def a_mcp_tool_call(self, server: str, tool: str, request: Any,
                              fn: Callable[[], Any]) -> Any:
        return await self.a_tool_call(f"{server}:{tool}", request, fn, kind=StepKind.MCP_TOOL_CALL)

    # -- internals -------------------------------------------------------
    def _record(self, kind: StepKind, name: str, request: Any, response: Any, *,
                error: Optional[StepError] = None, tokens: Optional[TokenUsage] = None,
                cost: Optional[float] = None, started: float = 0.0,
                ended: Optional[float] = None, meta: Optional[dict] = None) -> Step:
        if self._run_id is None:
            raise RuntimeError("Recorder.begin()/run() must be called before recording steps")
        req_ref = self.store.put_blob(request) if request is not None else None
        resp_ref = self.store.put_blob(response) if response is not None else None
        duration = (ended - started) * 1000.0 if (ended is not None and started) else None
        if cost is None and tokens is not None:
            cost = token_cost(name, tokens, self._prices)
        step = Step(
            index=self._next_index(),
            kind=kind,
            name=name,
            request_hash=req_ref,
            request_ref=req_ref,
            response_ref=resp_ref,
            started_at=started,
            ended_at=ended,
            duration_ms=duration,
            tokens=tokens,
            cost=cost,
            error=error,
            meta=meta or {},
        )
        self.store.put_step(self._run_id, step)
        self._enforce_budget(step)
        return step

    def _enforce_budget(self, step: Step) -> None:
        budget = self._budget
        if budget is None:
            return
        self._spent_steps += 1
        if step.tokens is not None:
            self._spent_tokens += step.tokens.total or ((step.tokens.prompt or 0)
                                                         + (step.tokens.completion or 0))
        if step.cost:
            self._spent_usd += step.cost
        if budget.max_steps is not None and self._spent_steps > budget.max_steps:
            raise BudgetExceeded(f"step budget exceeded ({self._spent_steps} > {budget.max_steps})")
        if budget.max_tokens is not None and self._spent_tokens > budget.max_tokens:
            raise BudgetExceeded(f"token budget exceeded ({self._spent_tokens} > {budget.max_tokens})")
        if budget.max_usd is not None and self._spent_usd > budget.max_usd:
            raise BudgetExceeded(f"cost budget exceeded (${self._spent_usd:.4f} > ${budget.max_usd})")

    def _next_index(self) -> int:
        i = self._index
        self._index += 1
        return i

    def close(self) -> None:
        self.store.close()


def _error(exc: Exception) -> StepError:
    return StepError(
        type=type(exc).__name__,
        message=str(exc),
        traceback="".join(_tb.format_exception(type(exc), exc, exc.__traceback__)),
    )


def _default_usage(result: Any) -> Optional[TokenUsage]:
    """Extract token usage from an OpenAI-style response (dict or object), if present."""
    usage = result.get("usage") if isinstance(result, dict) else getattr(result, "usage", None)
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else (lambda k, d=None: getattr(usage, k, d))
    prompt = get("prompt_tokens", get("prompt"))
    completion = get("completion_tokens", get("completion"))
    total = get("total_tokens", get("total"))
    if prompt is None and completion is None and total is None:
        return None
    return TokenUsage(prompt=prompt, completion=completion, total=total)
