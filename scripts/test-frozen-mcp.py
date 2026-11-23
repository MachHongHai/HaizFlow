"""Exercise real MCP stdio in a windowed Core EXE without touching the desktop."""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path


def smoke(artifact: Path) -> None:
    executable = artifact.resolve(strict=True) / "HaizFlowCore.exe"
    if not executable.is_file():
        raise ValueError("A frozen Core artifact is required.")
    info = json.loads((artifact / "BUILD-INFO.json").read_text("utf-8"))
    for profile in ("compact", "full"):
        with tempfile.TemporaryDirectory(prefix="haizflow-frozen-mcp-") as directory:
            root = Path(directory)
            environment = os.environ.copy()
            for name in ("PYTHONPATH", "HAIZFLOW_INSTALL_ROOT", "APP_DATA_DIR", "MODELS_DIR"):
                environment.pop(name, None)
            environment.update(HAIZFLOW_SMOKE_TEST="1", HAIZFLOW_HOME=str(root),
                               RUNTIME_DATA_DIR=str(root / "data"),
                               HAIZFLOW_RESOURCE_ROOT=str(root / "resources"),
                               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            with (root / "stderr.log").open("wb") as errors:
                process = subprocess.Popen(
                    [str(executable), "--mcp-server", "--endpoint", "HaizFlow-MCP-" + uuid.uuid4().hex,
                     "--tool-profile", profile],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, cwd=root,
                    env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                messages: queue.Queue = queue.Queue()
                stop_after_response = threading.Event()

                def read_messages(stream=process.stdout):
                    try:
                        for line in stream:
                            messages.put(json.loads(line.decode("utf-8")))
                            if stop_after_response.is_set():
                                break
                    except Exception as exc:
                        messages.put(exc)
                    finally:
                        messages.put(None)

                reader = threading.Thread(target=read_messages, daemon=True)
                reader.start()
                sequence = 0

                def send(method, params=None, *, notification=False, abandon_response=False):
                    nonlocal sequence
                    sequence += 1
                    outgoing = {"jsonrpc": "2.0", "method": method}
                    if not notification:
                        outgoing["id"] = sequence
                    if params is not None:
                        outgoing["params"] = params
                    process.stdin.write(json.dumps(outgoing).encode() + b"\n")
                    process.stdin.flush()
                    if notification or abandon_response:
                        return None
                    response = messages.get(timeout=40)
                    if not isinstance(response, dict):
                        raise RuntimeError("Frozen MCP closed or emitted invalid stdio; inspect stderr.")
                    if response.get("id") != sequence or "error" in response or "result" not in response:
                        raise RuntimeError(f"Unexpected frozen MCP response to {method}: {response}")
                    return response["result"]

                try:
                    initialized = send("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                        "clientInfo": {"name": "HaizFlow release acceptance", "version": "1"}})
                    assert initialized["serverInfo"]["name"] == "HaizFlow"
                    assert initialized["serverInfo"]["version"] == info["version"]
                    send("notifications/initialized", notification=True)
                    tools = send("tools/list")["tools"]
                    names = {tool["name"] for tool in tools}
                    assert "haizflow_capabilities" in names and "haizflow_execute" in names
                    assert (len(tools) == 9) if profile == "compact" else (len(tools) > 9)
                    assert send("ping") == {}
                    # A missing isolated desktop must produce a bounded tool
                    # error, not crash, leak a traceback, or connect to user data.
                    if profile == "compact":
                        stop_after_response.set()
                    failure = send("tools/call", {"name": "haizflow_capabilities", "arguments": {}})
                    assert failure.get("isError") is True
                    contents = json.dumps(failure, ensure_ascii=False)
                    assert "enable MCP" in contents and "Traceback" not in contents
                    if profile == "compact":
                        reader.join(timeout=3)
                        assert not reader.is_alive()
                        process.stdout.close()
                        send("ping", abandon_response=True)
                        # Hosts can leave stdin open briefly after discarding stdout.
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    process.stdin.close()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=10)
                    reader.join(timeout=3)
                    process.stdout.close()
                assert process.returncode == 0, (root / "stderr.log").read_text("utf-8", errors="replace")[-6000:]
                print(f"Frozen MCP {profile}: handshake, tools, transport error and shutdown passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    smoke(parser.parse_args().artifact)
