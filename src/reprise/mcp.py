from __future__ import annotations

from typing import Any, Optional

from .capture import Recorder

__all__ = ["RecordingMCPSession", "wrap_mcp_session"]


class RecordingMCPSession:
    """Wraps an MCP ``ClientSession``-like object so every ``call_tool`` is recorded.

    Duck-typed: the wrapped session need only expose an async ``call_tool(name, arguments)``.
    Works with the official ``mcp`` Python SDK. All other attributes/methods pass through
    unchanged, so this is a drop-in replacement:

        session = wrap_mcp_session(session, recorder, server="filesystem")
        result = await session.call_tool("read_file", {"path": "a.txt"})  # recorded
    """

    def __init__(self, session: Any, recorder: Recorder, server: str = "mcp"):
        self.__dict__["_session"] = session
        self.__dict__["_rec"] = recorder
        self.__dict__["_server"] = server

    async def call_tool(self, name: str, arguments: Optional[dict] = None, **kwargs: Any) -> Any:
        request: dict[str, Any] = {"server": self._server, "tool": name, "arguments": arguments or {}}
        if kwargs:
            request["kwargs"] = kwargs
        return await self._rec.a_mcp_tool_call(
            self._server, name, request,
            lambda: self._session.call_tool(name, arguments, **kwargs),
        )

    def __getattr__(self, item: str) -> Any:
        return getattr(self.__dict__["_session"], item)


def wrap_mcp_session(session: Any, recorder: Recorder, server: str = "mcp") -> RecordingMCPSession:
    """Convenience wrapper: record every tool call made through an MCP client session."""
    return RecordingMCPSession(session, recorder, server)
