# Reprise

**Deterministic record / replay and time-travel debugging for AI agents.** Local-first, MCP-native.

Reprise records every LLM call, tool call, and MCP interaction in an agent run into a single
portable file, then replays it **byte-for-byte** with no network and no API key — so you can debug
what your agent *actually* did instead of re-running a stochastic black box and hoping it
misbehaves the same way twice.

> **Status:** early (v0.0.1). Capture + deterministic replay work today. MCP-native capture, a CLI,
> fork-from-step, a time-travel UI, trajectory diffing, and cost attribution are on the roadmap.

## Why

Agent observability today is built for single LLM calls and is almost entirely cloud SaaS. When an
agent fails at tool call #14 because of something that happened at call #2, you get logs — not a
reproducible, re-runnable recording. Reprise treats an agent run the way [`rr`](https://github.com/rr-debugger/rr)
treats a program: capture the nondeterminism once, then replay it deterministically and inspect it.

## Quickstart

```python
from reprise import Recorder, Replayer

rec = Recorder("agent.reprise", name="my-agent")
with rec.run():
    # Works with the openai SDK or Ollama's OpenAI-compatible endpoint.
    resp = rec.openai_chat(client, model="llama3.2",
                           messages=[{"role": "user", "content": "hello"}])

# Later, offline, with zero API calls — served from the recording:
rp = Replayer("agent.reprise")
same = rp.respond({"provider": "openai-compatible", "endpoint": "chat.completions",
                   "model": "llama3.2", "messages": [{"role": "user", "content": "hello"}]})
```

Every recording is one SQLite file (`*.reprise`) — copy it, commit it as a test fixture, or attach
it to a bug report. Payloads are content-addressed and de-duplicated.

Run the offline example (no server needed):

```bash
python examples/record_openai_compatible.py
```

## How it works

```
 capture SDK              content-addressed             deterministic
 (wraps LLM / tool /  ->  trace store (SQLite,     ->   replayer
  MCP calls)               one portable .reprise)       (serves recorded responses)
```

Replay matching is by request **content hash** and is **occurrence-aware**: the Nth identical
request during a replay receives the Nth recorded response.

## Development

Requires Python ≥ 3.10. With [uv](https://github.com/astral-sh/uv):

```bash
uv run --python 3.12 --with pydantic --with pytest --no-project python -m pytest
```

## Roadmap

- [x] Capture SDK (OpenAI-compatible / Ollama) + content-addressed trace store
- [x] Deterministic, occurrence-aware replay
- [ ] MCP-native tool-call capture (first-class)
- [ ] CLI: `reprise run | ls | show | replay`
- [ ] Fork-from-step (re-run live from any point)
- [ ] Local web UI: timeline scrubber + step inspector
- [ ] Semantic trajectory diff + regression gate (local judge)
- [ ] Per-run cost / token attribution + budget ceilings

## Related work & prior art

Reprise builds on ideas from Mozilla's `rr`, the VCR cassette pattern (`vcrpy`), and LangGraph's
checkpointer. Its contribution is combining, in one tool: deterministic serving of **both** LLM and
tool responses, framework-agnostic **local-first** capture, and **MCP-native** tool calls — an
integration no existing tool ships today.

## License

MIT © 2026 Shreyas Bhardwaj

Companion project: **mcplens** — an MCP server inspector & linter. Together they form a small
MCP-reliability toolchain (lint your server, then record/replay the agents that use it).
