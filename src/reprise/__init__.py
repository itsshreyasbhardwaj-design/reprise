"""Reprise — deterministic record/replay and time-travel debugging for AI agents.

Local-first, MCP-native. Capture every LLM and tool call in an agent run, replay it
byte-for-byte offline, and (on the roadmap) fork from any step to debug what actually happened.
"""
from __future__ import annotations

from .blobs import blob_hash
from .capture import Recorder
from .replay import ReplayMiss, Replayer
from .schema import Run, RunStatus, Step, StepError, StepKind, TokenUsage
from .store import TraceStore

__version__ = "0.0.1"

__all__ = [
    "Recorder",
    "Replayer",
    "ReplayMiss",
    "TraceStore",
    "Run",
    "RunStatus",
    "Step",
    "StepKind",
    "StepError",
    "TokenUsage",
    "blob_hash",
    "__version__",
]
