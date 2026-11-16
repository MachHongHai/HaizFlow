"""Route MCP startup without accidentally falling through to the desktop."""

from __future__ import annotations


def mcp_server_arguments(arguments: list[str]) -> list[str] | None:
    """Return MCP arguments, or reject a malformed MCP invocation before Qt loads.

    STDIO clients pass an argv array, not a shell command. A pasted command
    stored as one args entry must fail closed rather than open a GUI each time
    the client starts a connection. Do not shell-split values or execute them.
    Other internal worker modes and normal desktop startup are unchanged.
    """
    if arguments and arguments[0] == "--mcp-server":
        return arguments[1:]
    if any(
        argument.lstrip().casefold().startswith(("--mcp", "--endpoint", "--tool-profile"))
        for argument in arguments
    ):
        raise ValueError(
            'Invalid MCP startup arguments. Start with "--mcp-server" and put '
            'each flag and value in a separate args entry.'
        )
    return None
