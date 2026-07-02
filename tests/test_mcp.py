from __future__ import annotations

import asyncio

from reprise import Recorder, Replayer, StepKind, wrap_mcp_session


class _FakeMCPSession:
    """Async stand-in for an mcp ClientSession."""

    def __init__(self, results):
        self._results = results
        self.calls = []

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        return self._results[name]

    async def list_tools(self):
        return list(self._results)


def test_mcp_tool_calls_are_recorded_and_replayable(tmp_path):
    path = tmp_path / "run.reprise"

    async def scenario():
        rec = Recorder(path, name="mcp-agent")
        session = wrap_mcp_session(_FakeMCPSession({
            "read_file": {"content": "hello"},
            "list_dir": {"entries": ["a", "b"]},
        }), rec, server="filesystem")
        with rec.run():
            r1 = await session.call_tool("read_file", {"path": "a.txt"})
            r2 = await session.call_tool("list_dir", {"path": "."})
        # passthrough of non-recorded methods still works
        tools = await session.list_tools()
        return rec.run_id, r1, r2, tools

    run_id, r1, r2, tools = asyncio.run(scenario())
    assert r1 == {"content": "hello"}
    assert set(tools) == {"read_file", "list_dir"}

    store_run = Recorder(path).store.load_run(run_id, with_steps=True)
    assert [s.kind for s in store_run.steps] == [StepKind.MCP_TOOL_CALL, StepKind.MCP_TOOL_CALL]
    assert store_run.steps[0].name == "filesystem:read_file"

    rp = Replayer(path, run_id=run_id)
    served = rp.respond({"server": "filesystem", "tool": "read_file", "arguments": {"path": "a.txt"}})
    assert served == {"content": "hello"}
