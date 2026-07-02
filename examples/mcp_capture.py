"""Record MCP tool calls made through a client session, then replay them offline.

Uses a fake async MCP session so it runs with zero setup; swap in a real ``mcp`` ClientSession
and the same ``wrap_mcp_session`` records it unchanged.

    python examples/mcp_capture.py
"""
from __future__ import annotations

import asyncio

from reprise import Recorder, Replayer, wrap_mcp_session


class FakeMCPSession:
    """Stand-in for an mcp ClientSession (async call_tool)."""

    async def call_tool(self, name, arguments=None):
        table = {
            "read_file": {"content": "# hello from a.md"},
            "list_dir": {"entries": ["a.md", "b.md"]},
        }
        return table[name]


async def main() -> None:
    rec = Recorder("mcp.reprise", name="mcp-agent")
    session = wrap_mcp_session(FakeMCPSession(), rec, server="filesystem")
    with rec.run():
        listing = await session.call_tool("list_dir", {"path": "."})
        content = await session.call_tool("read_file", {"path": "a.md"})
    print("recorded MCP calls:", listing, content)

    # Replay a recorded MCP tool call, offline, by its request.
    rp = Replayer("mcp.reprise")
    served = rp.respond({"server": "filesystem", "tool": "read_file", "arguments": {"path": "a.md"}})
    print("replayed read_file:", served)


if __name__ == "__main__":
    asyncio.run(main())
