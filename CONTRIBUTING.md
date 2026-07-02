# Contributing to Reprise

Thanks for your interest! Reprise aims to be a small, sharp, well-tested tool. Contributions that
keep it that way are very welcome.

## Development setup

Reprise targets Python ≥ 3.10 and uses [uv](https://github.com/astral-sh/uv). No project install is
needed to run the tests — the suite runs against `src/` directly:

```bash
# run the full test suite (core + UI)
uv run --python 3.12 --with 'pydantic>=2.6' --with 'pytest>=8' \
  --with 'fastapi>=0.110' --with 'uvicorn>=0.29' --with 'httpx>=0.27' \
  --no-project python -m pytest

# lint
uvx ruff check .
```

## Guidelines

- **Keep the core dependency-light.** The only runtime dependency is `pydantic`. Anything heavier
  (a web server, an embedding model) belongs behind an optional extra and a lazy import.
- **Local-first, no forced spend.** Every feature must work against a local model (Ollama) or fully
  offline. Never require a paid API key to run or test a feature.
- **Test what you add.** New behaviour needs a test. Prefer deterministic tests with fakes over
  network calls — Reprise is, after all, a tool for making agent runs reproducible.
- **Small diffs.** Fix the thing asked; avoid drive-by refactors in a feature PR.

## Pull requests

1. Open an issue first for anything non-trivial so we can agree on the approach.
2. Keep PRs focused; update `CHANGELOG.md` under `[Unreleased]`.
3. Make sure `pytest` and `ruff check` are green.

By contributing, you agree that your contributions are licensed under the MIT License.
