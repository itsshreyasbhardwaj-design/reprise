"""Reprise — deterministic record/replay and time-travel debugging for AI agents.

Local-first, MCP-native. Capture every LLM and tool call in an agent run, replay it
byte-for-byte offline, fork from any step to debug what actually happened, and diff runs.
"""
from __future__ import annotations

from .blobs import blob_hash
from .capture import Recorder
from .cost import Budget, BudgetExceeded, RunCost, run_cost, step_cost, token_cost
from .diff import StepChange, StepDiff, TrajectoryDiff, diff_runs
from .mcp import RecordingMCPSession, wrap_mcp_session
from .replay import ReplayMiss, Replayer
from .schema import Run, RunStatus, Step, StepError, StepKind, TokenUsage
from .session import Mode, Session
from .store import TraceStore

__version__ = "0.1.0"

__all__ = [
    # runtime
    "Recorder",
    "Replayer",
    "ReplayMiss",
    "Session",
    "Mode",
    "TraceStore",
    # mcp
    "RecordingMCPSession",
    "wrap_mcp_session",
    # cost / budget
    "Budget",
    "BudgetExceeded",
    "RunCost",
    "run_cost",
    "step_cost",
    "token_cost",
    # diff
    "diff_runs",
    "TrajectoryDiff",
    "StepDiff",
    "StepChange",
    # schema
    "Run",
    "RunStatus",
    "Step",
    "StepKind",
    "StepError",
    "TokenUsage",
    "blob_hash",
    "__version__",
]
