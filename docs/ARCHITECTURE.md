# Architecture

Reprise records an AI agent run into a portable file, replays it deterministically, forks it, and
diffs runs against each other. This document explains how the pieces fit together and why.

## Design goals

1. **Deterministic** — a recorded run must re-execute byte-for-byte, serving *both* recorded LLM
   responses and recorded tool/MCP responses.
2. **Local-first** — no cloud account, no API key. Works against Ollama and any OpenAI-compatible
   endpoint. The only runtime dependency is `pydantic`.
3. **MCP-native** — MCP tool calls are first-class recorded steps, not opaque HTTP.
4. **Portable** — one run is one file you can copy, commit as a fixture, or attach to a bug report.

## The pipeline

```
        ┌─────────────┐      ┌──────────────────────┐      ┌────────────────┐
agent → │  Capture    │ ---> │  Trace store         │ ---> │  Replay engine │ → deterministic
code    │  (Recorder) │      │  (SQLite .reprise)   │      │  (Replayer)    │   re-execution
        └─────────────┘      └──────────────────────┘      └────────────────┘
              │                        │                            │
       Session unifies          content-addressed             Session(fork) replays a
       record / replay / fork   + de-duplicated blobs          prefix, then diverges live
                                        │
                         diff_runs ─────┴──── cost / Budget ──── CLI ──── web UI
```

## Modules

| Module | Responsibility |
|--------|----------------|
| `schema.py` | Pydantic models: `Run`, `Step`, `StepKind`, `TokenUsage`, `StepError`. The data contract. |
| `blobs.py` | Content addressing: canonical JSON encoding → `sha256:` hash. `to_jsonable` never raises on exotic SDK objects. |
| `store.py` | `TraceStore` — SQLite persistence for runs, steps, and blobs; `copy_run_prefix` seeds forks. |
| `capture.py` | `Recorder` — wraps live LLM/tool/MCP calls (sync + async), fills token/cost, enforces budgets. |
| `replay.py` | `Replayer` — serves recorded responses by request hash, occurrence-aware. |
| `mcp.py` | `wrap_mcp_session` — records every `call_tool` through an MCP client session. |
| `session.py` | `Session` — one call surface (`llm`/`tool`/`mcp`) for `record` / `replay` / `fork` modes. |
| `cost.py` | Pricing, `run_cost`, and the `Budget` kill-switch. |
| `diff.py` | `diff_runs` — step-aligned `TrajectoryDiff` with a pluggable similarity function. |
| `cli.py` | `reprise` command surface. |
| `server.py` + `_web.py` | Optional local web UI (FastAPI + a single self-contained HTML page). |

## Data model

A **Run** is an ordered list of **Steps** plus provenance (`parent_run_id`, `forked_from_index`). A
**Step** captures one interaction: its `kind` (`llm_call` / `tool_call` / `mcp_tool_call` /
`event`), name, timing, token usage, cost, error, and references to its request and response
payloads.

Payloads are stored **content-addressed**: each request/response is canonicalised (sorted-key,
whitespace-free JSON) and keyed by `sha256`. Identical payloads collapse to one row, and the hash of
a request is exactly what the replayer matches on.

## Replay semantics

Replay is **occurrence-aware**. During recording, each step stores `request_hash` (the content hash
of its request). During replay, the Nth request with a given hash is served the Nth recorded
response for that hash. This handles agents that issue the same request multiple times (e.g. retry
loops) without collapsing them.

Strict mode raises `ReplayMiss` when a request has no further recorded response — surfacing
divergence instead of silently going live.

## Fork semantics

Forking uses the **replay-prefix-then-diverge** model (as in `rr` and LangGraph's checkpointer, but
framework-agnostic):

- `Session.fork(src, at=N, out=…)` opens a `Replayer` over the parent run and a `Recorder` over a
  new run tagged with `parent_run_id` / `forked_from_index`.
- For call index `< N`, the recorded response is **served** (rebuilding the agent's in-memory state
  deterministically) and copied into the new run, marked `meta.replayed = true`. The live function
  is **not** executed.
- For call index `≥ N`, the call runs **live** and is recorded — this is where the fork diverges.

This is why forking needs to re-run the agent rather than just copy steps: only re-execution rebuilds
the agent's state at the fork point.

## Extension points

- **Similarity / judge** — `diff_runs(..., similarity=fn)` accepts any `(a, b) -> float`. The default
  is a local, dependency-free text ratio; drop in an embedding cosine or an LLM-judge (runnable on
  Ollama) for semantic comparison.
- **Pricing** — any `{model_substring: (prompt_$per_1M, completion_$per_1M)}` map can replace the
  defaults; local models resolve to `$0`.
- **Providers** — `Recorder.llm_call(request, fn)` is provider-agnostic; `openai_chat` and
  `wrap_mcp_session` are thin adapters. New adapters only need to produce a JSON-able request/response.

## Performance & security notes

- **Storage** — SQLite with content-addressed de-duplication keeps repeated prompts/system messages
  cheap. Large payloads could be gzip-compressed in the blob table without changing the API.
- **Determinism boundary** — Reprise records the *inputs and outputs* it sees at the call boundary.
  Nondeterminism inside a tool that Reprise doesn't wrap is out of scope; wrap it with `tool_call`.
- **Sensitive data** — a `.reprise` file contains full request/response payloads (prompts, tool
  results). Treat recordings like logs: they may contain secrets, so scrub before sharing. Recordings
  are ignored by `.gitignore` unless added intentionally as fixtures.
