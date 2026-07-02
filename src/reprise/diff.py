from __future__ import annotations

import difflib
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel

from .blobs import canonical_bytes
from .schema import Run

__all__ = ["StepChange", "StepDiff", "TrajectoryDiff", "diff_runs", "text_similarity"]

Resolver = Callable[[Optional[str]], Any]
Similarity = Callable[[Any, Any], float]


class StepChange(str, Enum):
    SAME = "same"
    CHANGED = "changed"
    ADDED = "added"
    REMOVED = "removed"


class StepDiff(BaseModel):
    index: int
    change: StepChange
    name_a: Optional[str] = None
    name_b: Optional[str] = None
    similarity: Optional[float] = None


class TrajectoryDiff(BaseModel):
    run_a: str
    run_b: str
    steps: list[StepDiff]
    overall_similarity: float
    diverged_at: Optional[int] = None

    @property
    def identical(self) -> bool:
        return self.diverged_at is None and all(s.change is StepChange.SAME for s in self.steps)


def text_similarity(a: Any, b: Any) -> float:
    """Deterministic, dependency-free similarity of two payloads (canonical-JSON ratio, 0..1)."""
    sa = canonical_bytes(a).decode("utf-8")
    sb = canonical_bytes(b).decode("utf-8")
    return difflib.SequenceMatcher(None, sa, sb).ratio()


def diff_runs(run_a: Run, run_b: Run, resolve_a: Resolver, resolve_b: Resolver,
              *, similarity: Optional[Similarity] = None) -> TrajectoryDiff:
    """Align two runs step-by-step and classify each step.

    ``resolve_a`` / ``resolve_b`` turn a blob ref into its payload (typically ``store.get_blob``).
    ``similarity`` compares two response payloads; defaults to a local text ratio so diffing works
    offline. Pass an embedding- or judge-based function for semantic comparison.
    """
    sim = similarity or text_similarity
    n = max(len(run_a.steps), len(run_b.steps))
    steps: list[StepDiff] = []
    scores: list[float] = []
    diverged: Optional[int] = None

    for i in range(n):
        sa = run_a.steps[i] if i < len(run_a.steps) else None
        sb = run_b.steps[i] if i < len(run_b.steps) else None
        if sa is not None and sb is None:
            steps.append(StepDiff(index=i, change=StepChange.REMOVED, name_a=sa.name))
            diverged = i if diverged is None else diverged
            continue
        if sb is not None and sa is None:
            steps.append(StepDiff(index=i, change=StepChange.ADDED, name_b=sb.name))
            diverged = i if diverged is None else diverged
            continue
        assert sa is not None and sb is not None
        score = sim(resolve_a(sa.response_ref), resolve_b(sb.response_ref)) \
            if (sa.response_ref or sb.response_ref) else 1.0
        scores.append(score)
        same = sa.name == sb.name and sa.request_ref == sb.request_ref and score >= 0.999
        steps.append(StepDiff(
            index=i,
            change=StepChange.SAME if same else StepChange.CHANGED,
            name_a=sa.name, name_b=sb.name, similarity=round(score, 4),
        ))
        if not same and diverged is None:
            diverged = i

    overall = sum(scores) / len(scores) if scores else 1.0
    return TrajectoryDiff(run_a=run_a.run_id, run_b=run_b.run_id, steps=steps,
                          overall_similarity=round(overall, 4), diverged_at=diverged)
