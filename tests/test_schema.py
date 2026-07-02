from __future__ import annotations

from reprise.schema import Step, StepKind, TokenUsage


def test_step_roundtrips_through_json():
    step = Step(
        index=0,
        kind=StepKind.LLM_CALL,
        name="llama3",
        request_ref="sha256:abc",
        response_ref="sha256:def",
        tokens=TokenUsage(prompt=10, completion=5, total=15),
    )
    dumped = step.model_dump(mode="json")
    assert dumped["kind"] == "llm_call"
    restored = Step.model_validate(dumped)
    assert restored == step
    assert restored.tokens.total == 15


def test_kind_accepts_raw_value():
    step = Step(index=1, kind="tool_call", name="search")
    assert step.kind is StepKind.TOOL_CALL
