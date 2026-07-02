"""Record an OpenAI-compatible chat call into a .reprise file, then replay it deterministically.

Uses a local Ollama OpenAI-compatible endpoint if the ``openai`` package and a server are
available; otherwise falls back to a built-in fake client so the example runs offline with zero
setup.

    python examples/record_openai_compatible.py
"""
from __future__ import annotations

from types import SimpleNamespace

from reprise import Recorder, Replayer

PROMPT = [{"role": "user", "content": "Say hello in 3 words."}]


def _make_client():
    try:
        from openai import OpenAI  # type: ignore

        # Ollama exposes an OpenAI-compatible API; the api_key is ignored locally.
        return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), "llama3.2"
    except Exception:
        return _FakeClient(), "fake-model"


class _FakeCompletions:
    def create(self, **kwargs):
        content = kwargs["messages"][-1]["content"]
        return {
            "choices": [{"message": {"content": f"echo: {content}"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        }


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def _content(resp) -> str:
    if isinstance(resp, dict):
        return resp["choices"][0]["message"]["content"]
    return resp.choices[0].message.content


def main() -> None:
    client, model = _make_client()

    rec = Recorder("agent.reprise", name="example")
    with rec.run():
        resp = rec.openai_chat(client, model=model, messages=PROMPT)
    print("recorded:", _content(resp))

    # Deterministic replay — no client call, served from agent.reprise.
    rp = Replayer("agent.reprise")
    replayed = rp.respond(
        {"provider": "openai-compatible", "endpoint": "chat.completions",
         "model": model, "messages": PROMPT}
    )
    print("replayed:", _content(replayed))


if __name__ == "__main__":
    main()
