"""The client can disconnect during a response without crashing the stdio child."""

import errno
import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from haizflow.mcp.__main__ import _run_stdio

ROOT = Path(__file__).resolve().parents[1]
WINDOWED_BOOTLOADER = (
    "import runpy, sys, types\n"
    "import mcp.server.stdio\n"  # Load venv DLLs before imitating PyInstaller's stream state.
    "sys.modules['haizflow.config'] = types.ModuleType('haizflow.config')\n"
    "sys.frozen = True\n"
    "sys.stdin = sys.stdout = sys.stderr = None\n"
    "sys.argv.insert(1, '--mcp-server')\n"
    "runpy.run_path('haizflow_desktop.py', run_name='__main__')\n"
)


@pytest.mark.parametrize("launch", [
    pytest.param(("-m", "haizflow.mcp"), id="module"),
    pytest.param(("haizflow_desktop.py", "--mcp-server"), id="desktop-entry"),
    pytest.param(("-c", WINDOWED_BOOTLOADER), id="windowed-stream-restore",
                 marks=pytest.mark.skipif(sys.platform != "win32", reason="Windows bootloader")),
])
def test_stdio_exit_when_client_stops_reading(launch, tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "HAIZFLOW_SMOKE_TEST": "1",
           "HAIZFLOW_HOME": str(tmp_path), "RUNTIME_DATA_DIR": str(tmp_path / "data"),
           "HAIZFLOW_RESOURCE_ROOT": str(tmp_path / "resources")}
    endpoint = "HaizFlow-MCP-" + uuid.uuid4().hex
    error_log = tmp_path / "stderr.log"
    with error_log.open("wb") as errors, subprocess.Popen(
        [sys.executable, *launch, "--endpoint", endpoint, "--tool-profile", "compact"],
        cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
    ) as child:
        def send(method, request_id=None, params=None):
            message = {"jsonrpc": "2.0", "method": method}
            if request_id is not None:
                message["id"] = request_id
            if params is not None:
                message["params"] = params
            child.stdin.write(json.dumps(message).encode() + b"\n")
            child.stdin.flush()

        responses = queue.Queue()

        def read_two_responses():
            for _ in range(2):
                responses.put(child.stdout.readline())

        reader = threading.Thread(target=read_two_responses, daemon=True)
        reader.start()
        try:
            send("initialize", 1, {"protocolVersion": "2025-11-25", "capabilities": {},
                                  "clientInfo": {"name": "shutdown-test", "version": "1"}})
            hello = responses.get(timeout=15)
            assert hello, error_log.read_text("utf-8", errors="replace")
            assert json.loads(hello)["result"]["serverInfo"]["name"] == "HaizFlow"
            send("notifications/initialized")
            send("ping", 2)
            assert json.loads(responses.get(timeout=5))["result"] == {}
            reader.join(timeout=3)
            assert not reader.is_alive()
            child.stdout.close()
            send("ping", 3)  # The response now has no receiving end.
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            child.stdin.close()
            assert child.wait(timeout=10) == 0, error_log.read_text("utf-8", errors="replace")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            reader.join(timeout=3)
    assert "Traceback" not in error_log.read_text("utf-8", errors="replace")


@pytest.mark.parametrize("error", [
    OSError(errno.EINVAL, "invalid startup"), BrokenPipeError(errno.EPIPE, "internal pipe"),
])
def test_stdio_unrelated_os_errors_are_not_treated_as_disconnect(error):
    def run():
        raise ExceptionGroup("failed", [error])

    with pytest.raises(ExceptionGroup) as raised:
        _run_stdio(SimpleNamespace(run=run))
    assert raised.value.exceptions == (error,)


def test_stdio_only_discards_transport_error_from_mixed_group():
    stdio = {"__name__": "mcp.server.stdio", "errno": errno}
    exec("def stdout_writer():\n    raise BrokenPipeError(errno.EPIPE, 'peer closed')", stdio)

    def run():
        try:
            stdio["stdout_writer"]()
        except OSError as disconnected:
            raise ExceptionGroup("failed", [ExceptionGroup("transport", [disconnected]), ValueError("real error")])

    with pytest.raises(ExceptionGroup) as raised:
        _run_stdio(SimpleNamespace(run=run))
    assert len(raised.value.exceptions) == 1
    assert str(raised.value.exceptions[0]) == "real error"
