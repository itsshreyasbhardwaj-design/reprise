from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any

__all__ = ["to_jsonable", "canonical_bytes", "blob_hash"]


def to_jsonable(obj: Any) -> Any:
    """Best-effort conversion of an arbitrary object into a JSON-serialisable structure.

    Handles primitives, dict/list/tuple, pydantic models, dataclasses, and objects exposing
    ``model_dump`` / ``dict`` / ``to_dict``. Falls back to ``{"__repr__": repr(obj)}`` so capture
    never raises on an exotic response type (e.g. a provider SDK's response object).
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    for attr in ("model_dump", "dict", "to_dict"):
        method = getattr(obj, attr, None)
        if callable(method):
            try:
                return to_jsonable(method())
            except Exception:
                pass
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(asdict(obj))
    if hasattr(obj, "__dict__"):
        try:
            return to_jsonable(vars(obj))
        except Exception:
            pass
    return {"__repr__": repr(obj)}


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON encoding: sorted keys, no incidental whitespace."""
    return json.dumps(
        to_jsonable(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def blob_hash(obj: Any) -> str:
    """Content address of a payload: ``sha256:<hex>`` over its canonical encoding."""
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()
