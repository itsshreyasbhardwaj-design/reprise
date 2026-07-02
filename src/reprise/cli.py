from __future__ import annotations

import argparse
import datetime
import json
import sys
from typing import Optional

from . import __version__
from .cost import run_cost
from .diff import diff_runs
from .store import TraceStore

__all__ = ["main", "build_parser"]


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _die(msg: str, code: int = 2) -> None:
    print(f"reprise: error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _resolve_run(store: TraceStore, run_id: Optional[str]):
    rid = run_id or store.latest_run_id()
    if rid is None:
        _die("no runs found in file")
    run = store.load_run(rid, with_steps=True)  # type: ignore[arg-type]
    if run is None:
        _die(f"run not found: {rid}")
    return run


def cmd_ls(args) -> int:
    store = TraceStore(args.file)
    runs = store.list_runs()
    if not runs:
        print("(no runs)")
        return 0
    print(f"{'RUN ID':<34}  {'NAME':<20}  {'STATUS':<10}  {'STEPS':>5}  CREATED")
    for r in runs:
        steps = sum(1 for _ in store.iter_steps(r.run_id))
        print(f"{r.run_id:<34}  {r.name[:20]:<20}  {r.status.value:<10}  {steps:>5}  {_fmt_ts(r.created_at)}")
    return 0


def cmd_show(args) -> int:
    store = TraceStore(args.file)
    run = _resolve_run(store, args.run)
    if args.step is not None:
        return _show_step(store, run, args.step, args.verbose)
    print(f"run     {run.run_id}")
    print(f"name    {run.name}")
    print(f"status  {run.status.value}")
    if run.parent_run_id:
        print(f"forked  from {run.parent_run_id} at step {run.forked_from_index}")
    print(f"steps   {len(run.steps)}\n")
    print(f"{'#':>3}  {'KIND':<14}  {'NAME':<28}  {'ms':>7}  TOKENS")
    for s in run.steps:
        tok = f"{s.tokens.prompt or 0}->{s.tokens.completion or 0}" if s.tokens else ""
        ms = f"{s.duration_ms:.0f}" if s.duration_ms is not None else ""
        flag = "  !err" if s.error else ""
        print(f"{s.index:>3}  {s.kind.value:<14}  {s.name[:28]:<28}  {ms:>7}  {tok}{flag}")
    return 0


def _show_step(store: TraceStore, run, idx: int, verbose: bool) -> int:
    if idx < 0 or idx >= len(run.steps):
        _die(f"step {idx} out of range (0..{len(run.steps) - 1})")
    s = run.steps[idx]
    print(f"step {s.index}  {s.kind.value}  {s.name}")
    if s.duration_ms is not None:
        print(f"duration {s.duration_ms:.1f} ms")
    if s.tokens:
        print(f"tokens   prompt={s.tokens.prompt} completion={s.tokens.completion} total={s.tokens.total}")
    if s.cost:
        print(f"cost     ${s.cost:.6f}")
    if s.error:
        print(f"error    {s.error.type}: {s.error.message}")
    print("--- request ---")
    print(_dump(store.get_blob(s.request_ref)) if s.request_ref else "(none)")
    print("--- response ---")
    text = _dump(store.get_blob(s.response_ref)) if s.response_ref else "(none)"
    if not verbose and len(text) > 2000:
        text = text[:2000] + f"\n... [{len(text) - 2000} more chars; pass -v for full]"
    print(text)
    return 0


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def cmd_replay(args) -> int:
    store = TraceStore(args.file)
    run = _resolve_run(store, args.run)
    missing = 0
    seen: dict[str, int] = {}
    dupes = 0
    for s in run.steps:
        if s.request_ref:
            seen[s.request_ref] = seen.get(s.request_ref, 0) + 1
            if seen[s.request_ref] > 1:
                dupes += 1
        for ref in (s.request_ref, s.response_ref):
            if ref and store.get_blob(ref) is None:
                missing += 1
    ok = missing == 0
    print(f"run {run.run_id}: {len(run.steps)} steps, {dupes} repeated requests, {missing} dangling blobs")
    print("replayable: " + ("yes" if ok else "NO"))
    return 0 if ok else 1


def cmd_stat(args) -> int:
    store = TraceStore(args.file)
    run = _resolve_run(store, args.run)
    by_kind: dict[str, int] = {}
    total_ms = 0.0
    for s in run.steps:
        by_kind[s.kind.value] = by_kind.get(s.kind.value, 0) + 1
        if s.duration_ms:
            total_ms += s.duration_ms
    rc = run_cost(run)
    print(f"run {run.run_id}  ({run.name})")
    print(f"steps        {len(run.steps)}")
    for k, v in sorted(by_kind.items()):
        print(f"  {k:<14} {v}")
    print(f"tokens       {rc.prompt_tokens} prompt + {rc.completion_tokens} completion = {rc.total_tokens}")
    print(f"est. cost    ${rc.usd:.6f}")
    print(f"wall (rec.)  {total_ms:.0f} ms")
    return 0


def cmd_cost(args) -> int:
    store = TraceStore(args.file)
    run = _resolve_run(store, args.run)
    print(_dump(run_cost(run).model_dump()))
    return 0


def cmd_fork(args) -> int:
    store = TraceStore(args.file)
    src = _resolve_run(store, args.run)
    dst = TraceStore(args.out) if args.out else None
    new_id = store.copy_run_prefix(src.run_id, args.at, dst, new_name=args.name)
    print(f"forked {src.run_id} at step {args.at} -> {new_id}")
    print(f"in {args.out or args.file}  ({args.at} steps copied); resume recording from step {args.at}.")
    return 0


def cmd_diff(args) -> int:
    sa = TraceStore(args.file_a)
    sb = TraceStore(args.file_b)
    ra = _resolve_run(sa, args.run_a)
    rb = _resolve_run(sb, args.run_b)
    d = diff_runs(ra, rb, sa.get_blob, sb.get_blob)
    print(f"A {ra.run_id[:12]} ({len(ra.steps)} steps)  vs  B {rb.run_id[:12]} ({len(rb.steps)} steps)")
    marks = {"same": "  ", "changed": " ~", "added": " +", "removed": " -"}
    for s in d.steps:
        sim = f"  sim={s.similarity:.3f}" if s.similarity is not None else ""
        print(f"{marks[s.change.value]} #{s.index:<3} {s.change.value:<8} {(s.name_a or s.name_b or ''):<28}{sim}")
    tail = f"   diverged at step {d.diverged_at}" if d.diverged_at is not None else "   (identical)"
    print(f"overall similarity: {d.overall_similarity:.3f}{tail}")
    if args.gate:
        ok = d.overall_similarity >= args.threshold
        print(f"gate: {'PASS' if ok else 'FAIL'} (threshold {args.threshold})")
        return 0 if ok else 1
    return 0


def cmd_ui(args) -> int:
    try:
        from .server import serve
    except Exception as exc:  # pragma: no cover - depends on optional extra
        _die(f"UI requires optional deps: pip install 'reprise[ui]'  ({exc})")
    serve(args.file, host=args.host, port=args.port)  # pragma: no cover
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reprise",
        description="Record/replay & time-travel debugging for AI agents.",
    )
    p.add_argument("--version", action="version", version=f"reprise {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("ls", help="list runs in a .reprise file")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_ls)

    sp = sub.add_parser("show", help="show a run's steps, or one step's payloads")
    sp.add_argument("file")
    sp.add_argument("--run", help="run id (defaults to the latest)")
    sp.add_argument("--step", type=int, help="dump this step's request/response")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("replay", help="check a recording replays self-consistently")
    sp.add_argument("file")
    sp.add_argument("--run")
    sp.set_defaults(func=cmd_replay)

    sp = sub.add_parser("stat", help="aggregate steps/tokens/cost for a run")
    sp.add_argument("file")
    sp.add_argument("--run")
    sp.set_defaults(func=cmd_stat)

    sp = sub.add_parser("cost", help="print token/USD cost for a run as JSON")
    sp.add_argument("file")
    sp.add_argument("--run")
    sp.set_defaults(func=cmd_cost)

    sp = sub.add_parser("fork", help="seed a new run from steps [0, N) of an existing run")
    sp.add_argument("file")
    sp.add_argument("--at", type=int, required=True, help="fork point (step index)")
    sp.add_argument("--out", help="write the fork to this file (default: same file)")
    sp.add_argument("--run")
    sp.add_argument("--name")
    sp.set_defaults(func=cmd_fork)

    sp = sub.add_parser("diff", help="diff two runs step-by-step (optionally gate CI)")
    sp.add_argument("file_a")
    sp.add_argument("file_b")
    sp.add_argument("--run-a", dest="run_a")
    sp.add_argument("--run-b", dest="run_b")
    sp.add_argument("--gate", action="store_true", help="exit non-zero if similarity < threshold")
    sp.add_argument("--threshold", type=float, default=0.9)
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("ui", help="launch the local web UI for a .reprise file")
    sp.add_argument("file")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=7842)
    sp.set_defaults(func=cmd_ui)

    sp = sub.add_parser("version", help="print version")
    sp.set_defaults(func=lambda args: (print(f"reprise {__version__}"), 0)[1])
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
