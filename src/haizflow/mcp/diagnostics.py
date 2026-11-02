"""Read-only stdio handshake and desktop round trip, run outside the GUI thread."""

from __future__ import annotations

import asyncio
import json
import threading


async def _roundtrip(endpoint: str) -> dict:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    from .protocol import launch_configuration

    entry = json.loads(launch_configuration(endpoint))["mcpServers"]["haizflow"]
    params = StdioServerParameters(command=entry["command"], args=entry["args"])
    async with Client(params, raise_exceptions=False) as session:
        tools = (await session.list_tools()).tools
        if "haizflow_status" not in {tool.name for tool in tools}:
            return {"ok": False, "reason": "tools"}
        result = await session.call_tool("haizflow_status", {})
        if result.is_error:
            return {"ok": False, "reason": "desktop"}
        text = next(item.text for item in result.content if item.type == "text")
        status = json.loads(text)
        if not isinstance(status.get("permissions"), dict):
            return {"ok": False, "reason": "response"}
        return {"ok": True, "tools": len(tools)}


async def _check(endpoint: str, cancelled: threading.Event, timeout: float) -> dict:
    async def watch_cancel():
        while not cancelled.is_set():
            await asyncio.sleep(.1)

    task = asyncio.create_task(_roundtrip(endpoint))
    watcher = asyncio.create_task(watch_cancel())
    try:
        done, _ = await asyncio.wait((task, watcher), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            return {"ok": False, "reason": "cancelled"}
        if task not in done:
            return {"ok": False, "reason": "timeout"}
        return await task
    finally:
        for pending in (task, watcher):
            if not pending.done():
                pending.cancel()
        # Exiting the SDK stdio context closes its own child process. Never
        # kill an external agent or a user-owned HaizFlow process.
        await asyncio.gather(task, watcher, return_exceptions=True)


def check_connection(endpoint: str, cancelled: threading.Event, *, timeout: float = 15) -> dict:
    try:
        return asyncio.run(_check(endpoint, cancelled, timeout))
    except Exception:
        # Do not show raw SDK tracebacks, paths or environment details in UI.
        return {"ok": False, "reason": "transport"}
