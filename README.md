# Reprise

**Deterministic record / replay and time-travel debugging for AI agents.** Local-first, MCP-native.

[![CI](https://github.com/OWNER/reprise/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/reprise/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-informational.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

Reprise records every LLM call, tool call, and MCP interaction in an agent run into a single portable
file, then replays it **byte-for-byte** with no network and no API key — so you can debug what your
agent *actually* did, **fork from any step** to explore a different path, and **diff two runs** to
catch regressions. It treats an agent run the way [`rr`](https://github.com/rr-debugger/rr) treats a
program: capture the nondeterminism once, then replay and inspect it.

> **Status:** v0.1.0. Everything below works today and is covered by tests. It runs entirely offline.

## Why

Agent observability today is built for single LLM calls and is almost entirely cloud SaaS. When an
agent fails at tool call #14 because of something at call #2, you get logs — not a reproducible,
re-runnable recording. Reprise is the missing piece: **deterministic serving of both LLM and tool
responses**, **local-first**, and **MCP-native** — a combination no existing tool ships.

## Install

```bash
# core (record + replay + diff + cost + CLI)
pip install reprise            # once published; until then, clone and use uv (see Development)

# with the local web UI
pip install 'reprise[ui]'
```

## Quickstart

```python
from reprise import Session

# RECORD — every call runs live and is captured.
with Session.record("agent.reprise", name="my-agent") as s:
    plan = s.llm({"model": "llama3.2", "messages": [{"role": "user", "content": "plan"}]},
                 lambda: client.chat.completions.create(model="llama3.2", messages=[...]))
    hits = s.tool("search", {"q": "..."}, lambda: search("..."))

# REPLAY — same code, zero live calls; responses served from the recording.
with Session.replay("agent.reprise") as s:
    plan = s.llm({"model": "llama3.2", "messages": [{"role": "user", "content": "plan"}]},
                 lambda: never_called())
```

Every recording is one SQLite file (`*.reprise`) — copy it, commit it as a test fixture, or attach it
to a bug report. Payloads are content-addressed and de-duplicated.

## Fork from a step, then diff

```python
from reprise import Session, diff_runs

# Replay steps 0..N deterministically, then diverge live from step N.
with Session.fork("agent.reprise", at=2, out_path="fork.reprise") as s:
    ...  # re-run the agent; steps before 2 are served, step 2+ runs live with your change
```

```bash
reprise diff agent.reprise fork.reprise
#   #0  same     llama3.2
#   #1  same     search
# ~ #2  changed  llama3.2      sim=0.41
# overall similarity: 0.80   diverged at step 2
```

See [`examples/fork_and_diverge.py`](examples/fork_and_diverge.py) for a runnable, offline version.

## CLI

```
reprise ls      FILE                  list runs in a .reprise file
reprise show    FILE [--step N] [-v]  run summary, or one step's request/response
reprise replay  FILE                  check a recording replays self-consistently
reprise stat    FILE                  steps / tokens / cost / duration
reprise cost    FILE                  token & USD cost as JSON
reprise fork    FILE --at N [--out F] seed a new run from steps [0, N)
reprise diff    A B [--gate --threshold T]   step-by-step diff; --gate exits non-zero for CI
reprise ui      FILE [--port P]       launch the local web timeline/inspector
```

`reprise diff --gate` turns any recorded run into a **CI regression test**: record a golden trace,
then fail the build when a change makes the agent diverge beyond a threshold.

## MCP-native capture

```python
from reprise import Recorder, wrap_mcp_session

rec = Recorder("mcp.reprise")
session = wrap_mcp_session(mcp_client_session, rec, server="filesystem")
with rec.run():
    result = await session.call_tool("read_file", {"path": "a.txt"})  # recorded as a first-class step
```

Works with the official `mcp` Python SDK by duck typing; see [`examples/mcp_capture.py`](examples/mcp_capture.py).

## Cost attribution & budget kill-switch

```python
from reprise import Session, Budget

with Session.record("agent.reprise", budget=Budget(max_usd=0.50, max_steps=200)) as s:
    ...  # BudgetExceeded is raised the moment a ceiling is crossed (the offending step is still recorded)
```

## Local web UI

```bash
reprise ui agent.reprise      # → http://127.0.0.1:7842
```

A self-contained timeline scrubber (arrow keys / slider) with a per-step request/response inspector,
token/cost/latency facts, and fork provenance. No CDN, no build step.

## How it works

```
capture SDK        content-addressed          deterministic
(wraps LLM /   →   trace store (SQLite,   →    replayer          →  diff · cost · CLI · web UI
 tool / MCP)       one portable .reprise)      + fork/diverge
```

Replay matching is by request **content hash** and **occurrence-aware**: the Nth identical request in
a replay receives the Nth recorded response. Full design in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

Requires Python ≥ 3.10 and [uv](https://github.com/astral-sh/uv). The suite runs against `src/`
directly — no install needed:

```bash
uv run --python 3.12 --with 'pydantic>=2.6' --with 'pytest>=8' \
  --with 'fastapi>=0.110' --with 'uvicorn>=0.29' --with 'httpx>=0.27' \
  --no-project python -m pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- [x] Content-addressed trace store + capture SDK (OpenAI-compatible / Ollama)
- [x] Deterministic, occurrence-aware replay
- [x] MCP-native tool-call capture
- [x] `Session` runtime: record / replay / fork-and-diverge
- [x] CLI (`ls · show · replay · stat · cost · fork · diff · ui`)
- [x] Local web UI (timeline scrubber + step inspector)
- [x] Trajectory diff + CI regression gate
- [x] Per-run cost / token attribution + budget ceilings
- [ ] Embedding- / judge-based semantic diff (Ollama), beyond the local text ratio
- [ ] First-class adapters + integration tests against the real `openai` and `mcp` SDKs
- [ ] PyPI release; package the UI assets into the wheel

## Related work & prior art

Reprise builds on ideas from Mozilla's `rr`, the VCR cassette pattern (`vcrpy`), and LangGraph's
checkpointer. Its contribution is combining, in one tool: deterministic serving of **both** LLM and
tool responses, framework-agnostic **local-first** capture, and **MCP-native** tool calls — an
integration no existing tool ships today.

## License

MIT © 2026 Shreyas Bhardwaj

Companion project: **mcplens** — an MCP server inspector & linter. Together they form a small
MCP-reliability toolchain: lint your server, then record/replay the agents that use it.
