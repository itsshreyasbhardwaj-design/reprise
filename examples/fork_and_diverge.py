"""Record a 3-step agent, fork at step 2, diverge, and diff the two trajectories.

Runs fully offline with a deterministic fake model — no server, no API key.

    python examples/fork_and_diverge.py
"""
from __future__ import annotations

from reprise import Session, diff_runs
from reprise.store import TraceStore


def agent(session, *, answer: str) -> None:
    """A tiny 3-step 'agent': plan -> search -> answer. Deterministic given its inputs."""
    session.llm({"model": "llama3.2", "messages": [{"role": "user", "content": "plan"}]},
                lambda: {"choices": [{"message": {"content": "step 1: search"}}]})
    session.tool("search", {"q": "capital of France"},
                 lambda: {"results": ["Paris is the capital of France."]})
    session.llm({"model": "llama3.2", "messages": [{"role": "user", "content": "answer"}]},
                lambda: {"choices": [{"message": {"content": answer}}]})


def main() -> None:
    base, fork = "base.reprise", "fork.reprise"

    # 1) Record the original run.
    with Session.record(base, name="base") as s:
        agent(s, answer="The capital of France is Paris.")

    # 2) Fork at step 2: steps 0-1 are replayed deterministically to rebuild state, then step 2
    #    diverges and runs live (imagine you changed the prompt/model and want to see the effect).
    with Session.fork(base, at=2, out_path=fork, name="fork") as s:
        agent(s, answer="La capitale de la France est Paris.")  # different final answer

    # 3) Diff the two runs.
    sa, sb = TraceStore(base), TraceStore(fork)
    ra = sa.load_run(sa.latest_run_id(), with_steps=True)
    rb = sb.load_run(sb.latest_run_id(), with_steps=True)
    d = diff_runs(ra, rb, sa.get_blob, sb.get_blob)

    print(f"base run: {ra.run_id[:12]}  ({len(ra.steps)} steps)")
    print(f"fork run: {rb.run_id[:12]}  (forked at step {rb.forked_from_index})\n")
    print("step-by-step diff:")
    for st in d.steps:
        print(f"  #{st.index} {st.change.value:<8} similarity={st.similarity}")
    print(f"\ndiverged at step: {d.diverged_at}")
    print("steps 0-1 are identical (the fork replayed them); step 2 diverged live.")


if __name__ == "__main__":
    main()
