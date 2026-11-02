"""Bounded private-pipe protocol shared by the desktop and stdio adapter."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

PROTOCOL_VERSION = 1
MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 2 * 1024 * 1024
ENDPOINT_PATTERN = re.compile(r"HaizFlow-MCP-[a-f0-9]{32}\Z")


def default_endpoint() -> str:
    from haizflow.config import RUNTIME_DATA_DIR

    scope = f"{Path.home().resolve()}|{Path(RUNTIME_DATA_DIR).resolve()}".casefold()
    return "HaizFlow-MCP-" + hashlib.sha256(scope.encode()).hexdigest()[:32]


def validate_endpoint(value: str) -> str:
    if not ENDPOINT_PATTERN.fullmatch(value):
        raise ValueError("Invalid HaizFlow local endpoint.")
    return value


def encode_frame(value: dict, limit: int) -> bytes:
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode() + b"\n"
    if len(data) > limit:
        raise ValueError("Response/request too large; use pagination or a smaller selection.")
    return data


def launch_configuration(endpoint: str, client: str = "generic") -> str:
    validate_endpoint(endpoint)
    if getattr(sys, "frozen", False):
        command, args = sys.executable, ["--mcp-server", "--endpoint", endpoint]
    else:
        command, args = sys.executable, ["-m", "haizflow.mcp", "--endpoint", endpoint]
    args.extend(["--tool-profile", "compact"])
    if client == "codex":
        return "[mcp_servers.haizflow]\ncommand = " + json.dumps(command) + "\nargs = " + json.dumps(args) + "\n"
    return json.dumps({"mcpServers": {"haizflow": {"command": command, "args": args}}}, indent=2)
