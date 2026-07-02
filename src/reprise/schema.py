from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StepKind(str, Enum):
    """The kind of interaction a recorded step represents."""

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    MCP_TOOL_CALL = "mcp_tool_call"
    EVENT = "event"


class RunStatus(str, Enum):
    RECORDING = "recording"
    COMPLETED = "completed"
    FAILED = "failed"
    FORKED = "forked"


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: Optional[int] = None
    completion: Optional[int] = None
    total: Optional[int] = None


class StepError(BaseModel):
    type: str
    message: str
    traceback: Optional[str] = None


class Step(BaseModel):
    """A single recorded interaction within a run."""

    index: int
    kind: StepKind
    name: str
    # Content key used to match this request during deterministic replay. Equal to
    # request_ref today; kept distinct so a future normalized key can ignore volatile fields.
    request_hash: Optional[str] = None
    request_ref: Optional[str] = None
    response_ref: Optional[str] = None
    started_at: float = 0.0
    ended_at: Optional[float] = None
    duration_ms: Optional[float] = None
    tokens: Optional[TokenUsage] = None
    cost: Optional[float] = None
    error: Optional[StepError] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Run(BaseModel):
    """A recorded agent run: an ordered sequence of steps in one .reprise file."""

    run_id: str
    name: str = "run"
    created_at: float = 0.0
    ended_at: Optional[float] = None
    status: RunStatus = RunStatus.RECORDING
    # Set when this run was produced by forking another run at a given step index.
    parent_run_id: Optional[str] = None
    forked_from_index: Optional[int] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
