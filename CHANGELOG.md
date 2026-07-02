# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-07-02

Initial release. Local-first, MCP-native record/replay and time-travel debugging for AI agents.

### Added
- **Trace store** — content-addressed, de-duplicated payloads in a single portable SQLite
  `.reprise` file.
- **Capture SDK** (`Recorder`) — record LLM, tool, and MCP calls; sync and async variants; an
  `openai_chat` helper for OpenAI-compatible / Ollama endpoints.
- **Deterministic replay** (`Replayer`) — serve recorded responses back, occurrence-aware, so a
  run re-executes byte-for-byte.
- **MCP-native capture** (`wrap_mcp_session`) — record every `call_tool` through an MCP client
  session as a first-class step.
- **Session runtime** — one call surface for three modes: `record`, `replay`, and
  `fork` (replay a deterministic prefix, then diverge live).
- **Trajectory diff** (`diff_runs`) — step-aligned comparison with a local, dependency-free
  similarity function; pluggable for embedding/judge-based scoring.
- **Cost & budget** — per-run token/USD attribution and a `Budget` kill-switch
  (`max_usd` / `max_tokens` / `max_steps`).
- **CLI** — `reprise ls | show | replay | stat | cost | fork | diff | ui`; `diff --gate` for CI
  regression gating.
- **Local web UI** — self-contained timeline scrubber and step inspector (`reprise ui`).

[Unreleased]: https://github.com/itsshreyasbhardwaj-design/reprise/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/itsshreyasbhardwaj-design/reprise/releases/tag/v0.1.0
