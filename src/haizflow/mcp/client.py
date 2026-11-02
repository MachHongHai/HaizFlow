"""Synchronous QLocalSocket client; called off the MCP event loop."""

from __future__ import annotations

import json
import time
import uuid

from PySide6.QtNetwork import QLocalSocket

from .protocol import MAX_REQUEST, MAX_RESPONSE, PROTOCOL_VERSION, encode_frame, validate_endpoint


class DesktopClientError(RuntimeError):
    """An actionable, public-safe error from the desktop boundary or transport."""


class DesktopClient:
    def __init__(self, endpoint: str, timeout_ms: int = 15000):
        self.endpoint = validate_endpoint(endpoint)
        self.timeout_ms = timeout_ms

    def call(self, method: str, params: dict | None = None) -> dict:
        request_id = str(uuid.uuid4())
        try:
            frame = encode_frame(
                {"version": PROTOCOL_VERSION, "id": request_id, "method": method, "params": params or {}}, MAX_REQUEST
            )
        except ValueError as exc:
            raise DesktopClientError(str(exc)) from None
        socket = QLocalSocket()
        deadline = time.monotonic() + self.timeout_ms / 1000

        def remaining() -> int:
            return max(0, int((deadline - time.monotonic()) * 1000))

        try:
            socket.connectToServer(self.endpoint)
            if not socket.waitForConnected(min(1500, remaining())):
                raise DesktopClientError("Open HaizFlow and enable MCP in Settings → MCP before connecting.")
            if socket.write(frame) != len(frame):
                raise DesktopClientError("Could not send the MCP request.")
            socket.flush()
            while socket.bytesToWrite() and remaining():
                if not socket.waitForBytesWritten(remaining()) and socket.bytesToWrite():
                    raise DesktopClientError("Could not send the MCP request.")
            response = bytearray()
            while remaining():
                response.extend(bytes(socket.readAll()))
                if len(response) > MAX_RESPONSE:
                    raise DesktopClientError("HaizFlow response exceeded the size limit.")
                if b"\n" in response:
                    value = json.loads(response.split(b"\n", 1)[0])
                    if value.get("id") != request_id or value.get("version") != PROTOCOL_VERSION:
                        raise DesktopClientError("Invalid HaizFlow response.")
                    if "error" in value:
                        raise DesktopClientError(value["error"])
                    return value["result"]
                if not socket.waitForReadyRead(remaining()):
                    break
            # Do not retry mutations: the desktop may already have accepted them.
            raise DesktopClientError("HaizFlow did not respond. Check app status before repeating this action.")
        finally:
            socket.abort()
