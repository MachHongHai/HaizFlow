"""MCP clients must never open a desktop window because of malformed args."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from unittest.mock import patch

import pytest

from haizflow.core.startup_arguments import mcp_server_arguments
from haizflow.mcp.protocol import launch_configuration


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "HaizFlow-MCP-" + "a" * 32


@pytest.mark.parametrize("arguments", [
    [],
    ["--native-file-dialog", "C:/a folder/request.json"],
    ["--runtime-probe", "gpu"],
    ["--engine-worker", "--rpc"],
    ["--vieneu-worker", "C:/a folder/request.json"],
    ["--ui-smoke-test"],
])
def test_non_mcp_modes_are_unchanged(arguments):
    assert mcp_server_arguments(arguments) is None


@pytest.mark.parametrize("arguments", [
    [f"--mcp-server --endpoint {ENDPOINT} --tool-profile compact"],
    [" --mcp-server"],
    ["--MCP-SERVER"],
    ["--mcp_server"],
    [f"--mcp-server={ENDPOINT}"],
    ["--endpoint", ENDPOINT],
    [f"--endpoint={ENDPOINT}"],
    ["--tool-profile", "compact"],
    ["unexpected", "--mcp-server", "--endpoint", ENDPOINT],
])
def test_malformed_mcp_invocation_fails_closed(arguments):
    with pytest.raises(ValueError, match="separate args entry"):
        mcp_server_arguments(arguments)


def test_mcp_flag_with_no_arguments_still_routes_to_mcp_parser():
    assert mcp_server_arguments(["--mcp-server"]) == []


@pytest.mark.parametrize("client", ["codex", "claude", "antigravity", "generic"])
def test_frozen_configuration_keeps_every_argument_separate(client):
    with patch.object(sys, "frozen", True, create=True):
        text = launch_configuration(ENDPOINT, client)
    config = (tomllib.loads(text)["mcp_servers"]["haizflow"] if client == "codex"
              else json.loads(text)["mcpServers"]["haizflow"])
    assert config["args"] == ["--mcp-server", "--endpoint", ENDPOINT, "--tool-profile", "compact"]
    assert mcp_server_arguments(config["args"]) == config["args"][1:]


def test_bad_combined_argument_exits_before_importing_runtime_or_desktop():
    # A failing config module proves invalid MCP startup is stopped before it
    # can initialize user data, import Qt, or show a splash/desktop window.
    source = (
        "import runpy, sys\n"
        "class BlockRuntime:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname in ('haizflow.config', 'haizflow.desktop.main', 'PySide6'):\n"
        "            raise AssertionError('MCP reached GUI/runtime: ' + fullname)\n"
        "sys.meta_path.insert(0, BlockRuntime())\n"
        f"sys.argv = [{str(ROOT / 'haizflow_desktop.py')!r}, "
        f"'--mcp-server --endpoint {ENDPOINT} --tool-profile compact']\n"
        f"runpy.run_path({str(ROOT / 'haizflow_desktop.py')!r}, run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, env=os.environ.copy(),
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 2, result.stderr
    assert "Invalid MCP startup arguments" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("arguments,code,message", [
    (["--mcp-server"], 2, "--endpoint"),
    (["--mcp-server", "--endpoint"], 2, "expected one argument"),
    (["--mcp-server", "--endpoint", ENDPOINT, "--tool-profile", "wrong"], 2, "invalid choice"),
    (["--mcp-server", "--endpoint", ENDPOINT, "--unknown"], 2, "unrecognized arguments"),
    (["--mcp-server", f"--endpoint {ENDPOINT}"], 2, "--endpoint"),
    (["--mcp-server", "--help"], 0, "HaizFlow local MCP stdio server"),
])
def test_real_mcp_parser_errors_and_help_never_import_gui(arguments, code, message):
    source = (
        "import runpy, sys, types\n"
        "sys.modules['haizflow.config'] = types.ModuleType('haizflow.config')\n"
        "class BlockGUI:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname in ('haizflow.desktop.main', 'PySide6', 'haizflow.startup_splash'):\n"
        "            raise AssertionError('MCP reached GUI: ' + fullname)\n"
        "sys.meta_path.insert(0, BlockGUI())\n"
        f"sys.argv = {[str(ROOT / 'haizflow_desktop.py'), *arguments]!r}\n"
        f"runpy.run_path({str(ROOT / 'haizflow_desktop.py')!r}, run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, env=os.environ.copy(),
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == code, result.stderr
    assert message in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
