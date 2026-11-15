"""Malformed pipe replies must fail clearly, without replaying a mutation."""

import json

import pytest

from haizflow.mcp.client import DesktopClient, DesktopClientError
from haizflow.mcp.protocol import PROTOCOL_VERSION

ENDPOINT = "HaizFlow-MCP-" + "a" * 32


def install_socket(monkeypatch, reply):
    class Socket:
        writes = []
        aborted = False

        def connectToServer(self, endpoint):
            pass

        def waitForConnected(self, timeout):
            return True

        def write(self, frame):
            self.writes.append(json.loads(frame))
            value = reply(self.writes[-1])
            self.response = value if isinstance(value, bytes) else json.dumps(value).encode() + b"\n"
            return len(frame)

        def flush(self):
            pass

        def bytesToWrite(self):
            return 0

        def readAll(self):
            value, self.response = self.response, b""
            return value

        def waitForReadyRead(self, timeout):
            return False

        def abort(self):
            type(self).aborted = True

    monkeypatch.setattr("haizflow.mcp.client.QLocalSocket", Socket)
    return Socket


@pytest.mark.parametrize("reply", [
    lambda r: b"invalid\n",
    lambda r: b'"\xff"\n',
    lambda r: None,
    lambda r: [],
    lambda r: 42,
    lambda r: {"version": PROTOCOL_VERSION, "id": "wrong", "result": {}},
    lambda r: {"version": True, "id": r["id"], "result": {}},
    lambda r: {"version": str(PROTOCOL_VERSION), "id": r["id"], "result": {}},
    lambda r: {"version": PROTOCOL_VERSION, "id": r["id"]},
    lambda r: {"version": PROTOCOL_VERSION, "id": r["id"], "result": {}, "error": "oops"},
    lambda r: {"version": PROTOCOL_VERSION, "id": r["id"], "result": []},
    lambda r: {"version": PROTOCOL_VERSION, "id": r["id"], "result": None},
    lambda r: {"version": PROTOCOL_VERSION, "id": r["id"], "error": {}},
])
def test_invalid_reply_is_actionable_and_never_retried(monkeypatch, reply):
    socket = install_socket(monkeypatch, reply)
    with pytest.raises(DesktopClientError, match="Invalid HaizFlow response"):
        DesktopClient(ENDPOINT).call("process", {"video_id": "example"})
    assert len(socket.writes) == 1 and socket.aborted


def test_valid_reply_and_app_error_preserved(monkeypatch):
    socket = install_socket(monkeypatch, lambda r: {"version": PROTOCOL_VERSION, "id": r["id"], "result": {"ok": True}})
    assert DesktopClient(ENDPOINT).call("status") == {"ok": True}
    assert socket.aborted and len(socket.writes) == 1
    socket = install_socket(monkeypatch, lambda r: {"version": PROTOCOL_VERSION, "id": r["id"], "error": "Permission denied."})
    with pytest.raises(DesktopClientError, match="Permission denied"):
        DesktopClient(ENDPOINT).call("process")
    assert socket.aborted and len(socket.writes) == 1
