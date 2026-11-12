"""MCP tests use private runtime roots; never touch real user projects/accounts."""

import asyncio
import json
import sys
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.mcp_bridge import McpBridge
from haizflow.desktop.mcp_commands import COMMANDS, McpCommands
from haizflow.mcp.client import DesktopClient, DesktopClientError
from haizflow.mcp.protocol import MAX_REQUEST, MAX_RESPONSE, encode_frame, launch_configuration
from haizflow.mcp.server import create_server
from haizflow.schemas.video import VideoConfig, VideoInfo


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def bridge(app):
    host = QObject()
    instance = McpBridge(
        host,
        endpoint="HaizFlow-MCP-" + uuid.uuid4().hex,
        dispatcher=lambda method, params: {"method": method, "params": params},
    )
    assert instance.setEnabled(True)
    instance.setPermission("write", False)  # Most fixtures deliberately exercise read-only mode.
    yield instance
    instance.close()
    app.processEvents()


def in_worker(app, function, timeout=20):
    result, errors = [], []

    def work():
        try:
            result.append(function())
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout
    while worker.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        worker.join(0.005)
    assert not worker.is_alive(), "MCP test worker did not finish"
    if errors:
        raise errors[0]
    return result[0]


def test_private_pipe_roundtrip_unicode(app, bridge):
    import subprocess

    # The production adapter is a separate process. Qt's Windows blocking pipe
    # waits can hold the GIL; a second Python thread is not a valid stand-in.
    code = (
        "from PySide6.QtCore import QCoreApplication; import json,sys; "
        "from haizflow.mcp.client import DesktopClient; app=QCoreApplication([]); "
        "print(json.dumps(DesktopClient(sys.argv[1]).call('status', {'text':'Phụ đề 日本語 한국어'})))"
    )
    completed = in_worker(
        app,
        lambda: subprocess.run(
            [sys.executable, "-c", code, bridge.endpoint], capture_output=True, encoding="utf-8", timeout=20
        ),
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["params"]["text"] == "Phụ đề 日本語 한국어"


def test_offline_client_has_actionable_error(app):
    with pytest.raises(RuntimeError, match="enable MCP"):
        DesktopClient("HaizFlow-MCP-" + uuid.uuid4().hex, timeout_ms=200).call("status")


def test_permissions_reset_without_a_ui_confirmation_workflow(bridge):
    bridge.setPermission("publish", True)
    assert bridge.permissions["write"] and bridge.permissions["publish"]
    bridge.setPermission("online", True)
    assert bridge.approval == {}
    assert not hasattr(bridge, "prepare_approval")
    bridge.setPermission("write", False)
    assert not any(bridge.permissions.values())
    bridge.setPermission("delete", True)
    bridge.setEnabled(False)
    assert not any(bridge.permissions.values())
    assert bridge.setEnabled(True)
    assert all(bridge.permissions.values())


def test_enable_grants_all_permissions_but_individual_revocation_stays_effective(bridge):
    bridge.setEnabled(False)
    assert not any(bridge.permissions.values())
    assert bridge.setEnabled(True)
    assert all(bridge.permissions.values())
    bridge.setPermission("online", False)
    bridge.setPermission("publish", False)
    assert bridge.permissions == {"write": True, "online": False, "delete": True, "publish": False}
    assert bridge.setEnabled(True)  # A no-op must not grant permissions again.
    assert not bridge.permissions["online"] and not bridge.permissions["publish"]
    bridge.setPermission("write", False)
    assert not any(bridge.permissions.values())
    assert not bridge.approval


def test_failed_enable_does_not_grant_permissions(app, bridge):
    host = QObject()
    other = McpBridge(host, endpoint=bridge.endpoint, dispatcher=lambda *_args: {})
    try:
        assert not other.setEnabled(True)
        assert other.error
        assert not other.enabled
        assert not any(other.permissions.values())
    finally:
        other.close()


def test_legacy_listener_blocks_enable_and_releases_lock_for_next_attempt(app):
    from PySide6.QtNetwork import QLocalServer

    endpoint = "HaizFlow-MCP-" + uuid.uuid4().hex
    legacy = QLocalServer()
    legacy.setSocketOptions(QLocalServer.UserAccessOption)
    assert legacy.listen(endpoint)
    host = QObject()
    instance = McpBridge(host, endpoint=endpoint, dispatcher=lambda *_args: {})
    try:
        assert not instance.setEnabled(True)
        assert not any(instance.permissions.values())
        assert instance._endpoint_lock is None
        legacy.close()
        assert instance.setEnabled(True)
        assert all(instance.permissions.values())
    finally:
        legacy.close()
        instance.close()


def test_lock_permission_failure_reports_storage_error_without_granting_access(bridge):
    from PySide6.QtCore import QLockFile

    bridge.setEnabled(False)
    failure = Mock(tryLock=Mock(return_value=False), error=Mock(return_value=QLockFile.LockError.PermissionError))
    factory = Mock(return_value=failure)
    factory.LockError = QLockFile.LockError
    with patch("haizflow.desktop.mcp_bridge.QLockFile", factory):
        assert not bridge.setEnabled(True)
    assert "quyền ghi" in bridge.error
    assert not any(bridge.permissions.values())


def test_connection_check_is_async_readonly_and_disabled_when_mcp_is_off(app, bridge):
    bridge.setEnabled(False)
    assert not bridge.testConnection()
    assert bridge.connectionState == "error"
    assert bridge.setEnabled(True)
    with patch("haizflow.mcp.diagnostics.check_connection", return_value={"ok": True, "tools": 22}) as check:
        assert bridge.testConnection()
        assert bridge.connectionState == "checking"
        assert not bridge.testConnection()
        deadline = time.monotonic() + 5
        while bridge.connectionState == "checking" and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert bridge.connectionState == "success"
        assert "22" in bridge.connectionMessage and "nội bộ" in bridge.connectionMessage
        check.assert_called_once()


def test_disable_cancels_check_and_late_result_cannot_report_success(bridge):
    stopped = threading.Event()

    def cancelled(_endpoint, event):
        event.wait(3)
        assert event.is_set()
        stopped.set()
        return {"ok": True, "tools": 22}

    with patch("haizflow.mcp.diagnostics.check_connection", side_effect=cancelled):
        assert bridge.testConnection()
        bridge.setEnabled(False)
        assert bridge.connectionState == "idle"
        assert stopped.wait(4)
        assert bridge.connectionState == "idle"


def test_connection_timeout_and_cancellation_do_not_leave_pending_tasks():
    from haizflow.mcp import diagnostics

    async def pending(_endpoint):
        await asyncio.sleep(100)

    with patch.object(diagnostics, "_roundtrip", pending):
        assert diagnostics.check_connection("unused", threading.Event(), timeout=.02)["reason"] == "timeout"
        cancelled = threading.Event()
        cancelled.set()
        assert diagnostics.check_connection("unused", cancelled)["reason"] == "cancelled"


def test_frozen_core_includes_client_for_in_app_connection_check():
    from pathlib import Path

    script = (Path(__file__).parents[1] / "scripts/build-exe.ps1").read_text("utf-8")
    assert '"--collect-submodules", "mcp.client"' in script


def test_request_and_response_bounds():
    with pytest.raises(ValueError, match="too large"):
        encode_frame({"data": "x" * MAX_REQUEST}, MAX_REQUEST)
    assert len(encode_frame({"data": "abc"}, MAX_RESPONSE)) < MAX_RESPONSE


def test_client_configs_parse_and_use_current_interpreter(bridge):
    import tomllib

    config = tomllib.loads(launch_configuration(bridge.endpoint, "codex"))["mcp_servers"]["haizflow"]
    assert config["command"] == sys.executable
    assert config["args"][:2] == ["-m", "haizflow.mcp"]
    assert config["args"][-2:] == ["--tool-profile", "compact"]
    for name in ("claude", "antigravity", "generic"):
        assert json.loads(launch_configuration(bridge.endpoint, name))["mcpServers"]["haizflow"] == config


def test_sdk_tool_and_resource_discovery_do_not_execute_mutations():
    from mcp import Client

    client = Mock()
    client.call.return_value = {"permissions": {"write": False}}
    server = create_server(client)

    async def run():
        async with Client(server, raise_exceptions=True) as session:
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {
                "haizflow_prepare_delete",
                "haizflow_delete_project",
                "haizflow_prepare_publish",
                "haizflow_publish",
                "haizflow_execute",
                "haizflow_capabilities",
            } <= names
            for tool in tools.tools:
                if tool.name in {"haizflow_delete_project", "haizflow_publish"}:
                    assert "confirmation_token" not in tool.input_schema.get("required", [])
            assert not client.call.called
            await session.call_tool("haizflow_status", {})
            client.call.assert_called_once_with("status")
            await session.read_resource("haizflow://status")

    asyncio.run(run())


@pytest.mark.parametrize("message", [
    "offset must be >= 0; limit must be between 1 and 200.",
    "Open HaizFlow and enable MCP in Settings → MCP before connecting.",
    "Enable MCP 'write' permission in HaizFlow Settings for this session.",
    "HaizFlow did not respond. Check app status before repeating this action.",
])
def test_expected_tool_errors_preserve_the_actionable_message(message):
    from mcp import Client

    client = Mock()
    client.call.side_effect = DesktopClientError(message)

    async def run():
        async with Client(create_server(client), raise_exceptions=False) as session:
            result = await session.call_tool("haizflow_execute", {"command": "projects", "arguments": {"limit": -1}})
            assert result.is_error
            assert message in " ".join(item.text for item in result.content if item.type == "text")
        client.call.assert_called_once()  # No automatic retry of possibly accepted mutations.

    asyncio.run(run())


def test_unexpected_server_crash_keeps_details_private():
    from mcp import Client

    client = Mock()
    client.call.side_effect = RuntimeError("fake-secret-that-must-not-reach-agent")

    async def run():
        async with Client(create_server(client), raise_exceptions=False) as session:
            result = await session.call_tool("haizflow_status", {})
            assert result.is_error
            assert "fake-secret" not in str(result.content)

    asyncio.run(run())


def test_expected_resource_error_preserves_the_actionable_message():
    from mcp import Client

    message = "Open HaizFlow and enable MCP in Settings → MCP before connecting."
    client = Mock()
    client.call.side_effect = DesktopClientError(message)

    async def run():
        async with Client(create_server(client), raise_exceptions=False) as session:
            with pytest.raises(Exception, match="Open HaizFlow and enable MCP"):
                await session.read_resource("haizflow://status")

    asyncio.run(run())


@pytest.mark.parametrize("desktop_entry", [False, True])
def test_real_stdio_host_handshake_and_call(app, bridge, desktop_entry):
    from pathlib import Path

    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    async def run():
        args = (
            [str(Path(__file__).parents[1] / "haizflow_desktop.py"), "--mcp-server"]
            if desktop_entry
            else ["-m", "haizflow.mcp"]
        )
        parameters = StdioServerParameters(command=sys.executable, args=[*args, "--endpoint", bridge.endpoint])
        async with Client(parameters, raise_exceptions=True) as session:
            tools = await session.list_tools()
            assert any(tool.name == "haizflow_publish" for tool in tools.tools)
            response = await session.call_tool("haizflow_status", {})
            assert not response.is_error

    in_worker(app, lambda: asyncio.run(run()))


def test_real_stdio_expected_error_survives_the_private_pipe(app, bridge):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    def reject(method, arguments):
        raise ValueError("offset must be >= 0; limit must be between 1 and 200.")

    bridge._dispatcher = reject

    async def run():
        params = StdioServerParameters(command=sys.executable,
                                      args=["-m", "haizflow.mcp", "--endpoint", bridge.endpoint])
        async with Client(params, raise_exceptions=False) as session:
            result = await session.call_tool("haizflow_list_projects", {"limit": -1})
            assert result.is_error
            assert "limit must be between 1 and 200" in str(result.content)

    in_worker(app, lambda: asyncio.run(run()))


@pytest.fixture
def commands(bridge, monkeypatch):
    config = VideoConfig(project_type="manual", project_key="project:test")
    video = VideoInfo(
        **config.model_dump(),
        video_id="test-video",
        original_filename="test.mp4",
        status="manual_ready",
        created_at="today",
        updated_at="today",
    )
    host = SimpleNamespace(
        _shutdown_started=False,
        _selected_project_key="project:test",
        _selected_video_id="test-video",
        _catalog_videos={video.video_id: video},
        _project_summaries_by_key={
            "project:test": {"key": "project:test", "project_name": "Test", "project_type": "manual"}
        },
        _project_commands=Mock(is_deleting=Mock(return_value=False)),
        _project_import=Mock(has_project_work=Mock(return_value=False)),
        _media_downloader=Mock(has_project_work=Mock(return_value=False)),
        _tiktok_publisher=Mock(has_project_work=Mock(return_value=False)),
        _processing_queue=Mock(
            contains=Mock(return_value=False), active_video_id=None, pending_ids=Mock(return_value=[])
        ),
        _manual_subtitles=SimpleNamespace(_states={}, segments=[], video_id=video.video_id, revision=0),
        _manual_settings_drafts={},
        _manual_editing_segment_id="",
        _resource_packs=SimpleNamespace(storageMoving=False),
        _video_exports=SimpleNamespace(busy=False, jobs=[]),
        _media_import_busy=False,
        _url_importer=SimpleNamespace(state="idle", progress=0),
        _video_project_key=lambda v: v.project_key,
        _build_config=lambda: config,
        runManualTool=Mock(return_value=True),
        _apply_config_to_video=Mock(),
        _select_video=Mock(),
    )
    monkeypatch.setattr("haizflow.services.video_store.get_video", lambda video_id: video)
    return McpCommands(host, bridge)


def test_capabilities_cover_all_allowlisted_commands(commands):
    capabilities = commands.dispatch("capabilities", {"include_schemas": True})
    assert set(capabilities["commands"]) == COMMANDS
    assert {"batch_start", "channel_scan", "publish", "delete", "edit_subtitle"} <= COMMANDS
    export_schema = capabilities["commands"]["export"]["input_schema"]
    for option in ("overwrite", "process"):
        assert export_schema["properties"][option]["default"] is False
        assert option not in export_schema["required"]


def test_compact_discovery_is_smaller_and_named_schemas_remain_complete(commands):
    from haizflow.mcp.efficiency import encoded_size

    full = commands.dispatch("capabilities", {"include_schemas": True})
    small = commands.dispatch("capabilities", {})
    assert set(full["commands"]) == set(small["commands"])
    assert encoded_size(small) < encoded_size(full) * .4
    scoped = commands.dispatch("capabilities", {"command_names": ["translation_patch", "export"]})
    assert set(scoped["commands"]) == {"translation_patch", "export"}
    assert scoped["commands"]["translation_patch"]["input_schema"]["additionalProperties"] is False
    assert all(item["area"] == "subtitles" for item in commands.dispatch(
        "capabilities", {"area": "subtitles", "include_schemas": False})["commands"].values())


@pytest.mark.parametrize("arguments", [{"area": "wrong"}, {"command_names": []},
                                        {"command_names": ["shell"]}, {"include_schemas": "true"}])
def test_bad_discovery_filters_are_rejected(commands, arguments):
    with pytest.raises(ValueError):
        commands.dispatch("capabilities", arguments)


def test_projects_search_and_compact_paginated_video_list(commands):
    host = commands.host
    host._project_summaries_by_key["project:other"] = {
        "key": "project:other", "project_name": "Tiếng Việt", "project_type": "single"}
    result = commands.dispatch("projects", {"query": "TIẾNG", "kind": "single"})
    assert [row["key"] for row in result["items"]] == ["project:other"]
    original = host._catalog_videos["test-video"]
    host._catalog_videos.update({f"video-{i}": original.model_copy(update={"video_id": f"video-{i}"})
                                for i in range(100)})
    result = commands.dispatch("project", {"project_id": "project:test", "offset": 98, "limit": 2,
                                           "compact": True})
    assert result["total"] == 101 and len(result["videos"]) == 2
    assert "subtitle_style" not in result["videos"][0]
    with pytest.raises(ValueError):
        commands.dispatch("project", {"project_id": "project:test", "limit": 0})


@pytest.mark.parametrize("forbidden", ["delete", "run", "publish", "read_many", "visual_context"])
def test_read_many_rejects_entire_mixed_request_before_any_read_or_write(commands, monkeypatch, forbidden):
    lookup = Mock()
    monkeypatch.setattr(commands, "_known_video", lookup)
    with pytest.raises(ValueError):
        commands.dispatch("read_many", {"requests": [{"command": "video", "arguments": {"video_id": "test-video"}},
                                                    {"command": forbidden, "arguments": {}}]})
    lookup.assert_not_called()


def test_read_many_validates_every_schema_before_reading_and_bounds_results(commands, monkeypatch):
    lookup = Mock()
    with monkeypatch.context() as scoped:
        scoped.setattr(commands, "_known_video", lookup)
        with pytest.raises(ValueError):
            commands.dispatch("read_many", {"requests": [{"command": "video", "arguments": {"video_id": "test-video"}},
                                                        {"command": "projects", "arguments": {"typo": 1}}]})
        lookup.assert_not_called()
    result = commands.dispatch("read_many", {"requests": [{"command": "projects", "arguments": {}},
                                                         {"command": "video", "arguments": {"video_id": "unknown"}}]})
    assert "result" in result["results"][0] and "error" in result["results"][1]
    commands.host._project_summaries_by_key["project:test"]["project_name"] = "X" * 13000
    result = commands.dispatch("read_many", {"requests": [{"command": "projects", "arguments": {}}]})
    assert "12 KB" in result["results"][0]["error"]
    for requests in ([], [{}] * 9):
        with pytest.raises(ValueError):
            commands.dispatch("read_many", {"requests": requests})


def test_observe_live_cursor_changes_on_progress_errors_and_permission_revocation(commands, bridge):
    from haizflow.mcp.efficiency import encoded_size

    video = commands.host._catalog_videos["test-video"]
    first = commands.dispatch("observe", {"video_ids": [video.video_id]})
    assert not first["busy"]
    same = commands.dispatch("observe", {"video_ids": [video.video_id], "since": first["cursor"]})
    assert same == {"cursor": first["cursor"], "changed": False}
    assert encoded_size(same) < encoded_size(first) / 2
    video.progress, video.status = 42, "processing"
    running = commands.dispatch("observe", {"video_ids": [video.video_id], "since": first["cursor"]})
    assert running["changed"] and running["busy"] and running["videos"][0]["progress"] == 42
    video.status, video.error = "failed", "Authorization: Bearer secret-token"
    failed = commands.dispatch("observe", {"video_ids": [video.video_id], "since": running["cursor"]})
    assert failed["changed"] and not failed["busy"]
    assert "secret-token" not in json.dumps(failed)
    bridge.setPermission("write", True)
    granted = commands.dispatch("observe", {"video_ids": [video.video_id]})
    bridge.setPermission("write", False)
    assert commands.dispatch("observe", {"video_ids": [video.video_id], "since": granted["cursor"]})["changed"]


def test_targeted_observe_ignores_other_video_progress_but_waits_for_own_export(commands):
    host = commands.host
    host._processing_queue.active_video_id = "other-video"
    host._processing_queue.pending_ids.return_value = ["other-video"]
    job = {"videoId": "other-video", "status": "exporting", "progress": 50}
    host._video_exports.jobs = [job]
    first = commands.dispatch("observe", {"video_ids": ["test-video"]})
    assert not first["busy"] and first["exports"] == []
    job["progress"] = 60
    assert not commands.dispatch("observe", {"video_ids": ["test-video"], "since": first["cursor"]})["changed"]
    host._video_exports.jobs.append({"videoId": "test-video", "status": "exporting", "progress": 99})
    assert commands.dispatch("observe", {"video_ids": ["test-video"]})["busy"]
    host._video_exports.jobs[-1]["status"] = "done"
    assert not commands.dispatch("observe", {"video_ids": ["test-video"]})["busy"]


def test_observe_unqueued_pending_video_is_idle_and_import_inspection_is_busy(commands):
    commands.host._catalog_videos["test-video"].status = "pending"
    assert not commands.dispatch("observe", {"video_ids": ["test-video"]})["busy"]
    commands.host._url_importer.state = "inspecting"
    assert commands.dispatch("observe", {})["busy"]


@pytest.mark.parametrize("arguments", [{"video_ids": ["unknown"]}, {"since": "x" * 65},
                                        {"workflow": "shell"}, {"workflow": "social"},
                                        {"project_id": "project:test"}])
def test_observe_rejects_invalid_targets(commands, arguments):
    with pytest.raises(ValueError):
        commands.dispatch("observe", arguments)


def test_translation_context_filters_keep_original_cue_ids_and_revision(commands, monkeypatch):
    state = {"revision": "all-cues", "source": [], "segments": [
        {"segment_id": f"s-{i}", "start": i, "end": i + 1, "text": f"Chào bạn {i}", "speaker": f"p{i % 2}"}
        for i in range(10)]}
    monkeypatch.setattr(commands, "_translation_snapshot", lambda _id: (
        commands.host._catalog_videos["test-video"], state))
    result = commands.dispatch("translation_context", {"video_id": "test-video", "query": "BẠN 5", "speaker": "p1"})
    assert result["revision"] == "all-cues" and result["total"] == 1 and result["total_cues"] == 10
    assert result["items"][0]["cue_id"] == "cue-6"
    exact = commands.dispatch("translation_context", {"video_id": "test-video", "cue_ids": ["cue-10", "cue-2"]})
    assert [row["cue_id"] for row in exact["items"]] == ["cue-2", "cue-10"]
    with pytest.raises(ValueError):
        commands.dispatch("translation_context", {"video_id": "test-video", "cue_ids": ["cue-999"]})


def test_social_compact_pagination_and_observe_never_publish(social_commands):
    commands, item = social_commands
    social = commands.host._tiktok_publisher
    social.busy = True
    social._accounts = []
    social._model_item.return_value = {}
    social._queue_items.return_value = [dict(item, id=f"item-{i}", caption="long caption" * 100) for i in range(80)]
    result = commands.dispatch("social_status", {"project_id": "project:test", "offset": 70,
                                               "limit": 2, "compact": True})
    assert result["total"] == 80 and len(result["items"]) == 2
    assert "caption" not in result["items"][0] and "accounts" not in result
    exact = commands.dispatch("social_status", {"project_id": "project:test", "item_ids": ["item-79"]})
    assert len(exact["items"]) == 1
    snapshot = commands.dispatch("observe", {"workflow": "social", "project_id": "project:test"})
    assert snapshot["busy"] and len(snapshot["items"]) == 50
    assert not commands.dispatch("observe", {"workflow": "social", "project_id": "project:test",
                                            "since": snapshot["cursor"]})["changed"]
    social.busy = False
    social._queue_items.return_value[-1].update(status="publishing", upload_progress=100)
    pending = commands.dispatch("observe", {"workflow": "social", "project_id": "project:test"})
    assert pending["busy"] and pending["active_items"][0]["id"] == "item-79"
    social._queue_items.return_value[-1]["status"] = "published"
    finished = commands.dispatch("observe", {"workflow": "social", "project_id": "project:test",
                                             "since": pending["cursor"]})
    assert finished["changed"] and not finished["busy"]
    assert finished["status_counts"]["published"] == 1
    social.publish_token.assert_not_called()


def test_download_observe_includes_inspection_and_channel_work_without_starting_work(commands):
    host = commands.host
    host._project_summaries_by_key["project:test"]["project_type"] = "download"
    download = host._media_downloader
    download.state, download.status, download.progress = "idle", "", 0
    download.queueCount, download.channelState, download.channelStatus = 0, "idle", ""
    download.channelProgress, download.channelCandidateCount, download.channelSelectedCount = 0, 0, 0
    download.videoPreviewReady = download.audioPreviewReady = False
    download.hasWork = download.videoPreviewBusy = download.audioPreviewBusy = False
    snapshot = commands.dispatch("observe", {"workflow": "download", "project_id": "project:test"})
    assert not snapshot["busy"]
    download.videoPreviewBusy = True
    assert commands.dispatch("observe", {"workflow": "download", "project_id": "project:test"})["busy"]
    download.videoPreviewBusy, download.hasWork = False, True
    assert commands.dispatch("observe", {"workflow": "download", "project_id": "project:test"})["busy"]
    download.downloadVideo.assert_not_called()
    download.inspectChannel.assert_not_called()


def test_wait_and_compact_discovery_work_through_real_mcp_sdk():
    from mcp import Client

    client = Mock()
    server = create_server(client)

    async def run():
        async with Client(server, raise_exceptions=True) as session:
            tools = {item.name: item for item in (await session.list_tools()).tools}
            for name in ("haizflow_observe", "haizflow_wait", "haizflow_read_many"):
                assert tools[name].annotations.read_only_hint
            client.call.return_value = {"commands": {}}
            await session.call_tool("haizflow_capabilities", {})
            assert client.call.call_args.args == ("capabilities", {"command_names": None, "area": "",
                                                                 "include_schemas": False})
            await session.call_tool("haizflow_capabilities", {"command_names": ["export"]})
            assert client.call.call_args.args[1]["include_schemas"]
            client.call.side_effect = [{"cursor": "old", "changed": True, "busy": True},
                                       {"cursor": "new", "changed": True, "busy": False}]
            result = await session.call_tool("haizflow_wait", {"video_ids": ["v1"], "since": "old", "until": "idle",
                                                              "timeout_seconds": 3})
            assert not result.is_error and json.loads(result.content[0].text)["timed_out"] is False
            assert len(result.content) == 1 and result.structured_content is None
            assert "\n" not in result.content[0].text
            assert client.call.call_args.args == ("observe", {"video_ids": ["v1"], "workflow": "processing",
                                                             "project_id": ""})
    asyncio.run(run())


def test_wait_timeout_is_small_unchanged_not_failure_and_does_not_retry_mutations():
    from mcp import Client

    client = Mock()
    client.call.return_value = {"cursor": "same", "changed": True, "busy": True}

    async def run():
        async with Client(create_server(client), raise_exceptions=True) as session:
            result = await session.call_tool("haizflow_wait", {"since": "same", "timeout_seconds": 1})
            assert json.loads(result.content[0].text) == {"cursor": "same", "changed": False, "timed_out": True}
            assert not result.is_error
            assert all(c.args[0] == "observe" for c in client.call.call_args_list)
    asyncio.run(run())


def test_wait_real_stdio_pipe_keeps_dispatch_on_gui_thread(app, bridge):
    from mcp import Client, StdioServerParameters

    gui_thread, calls = threading.get_ident(), []

    def dispatch(method, params):
        assert method == "observe" and params["video_ids"] == ["private-test-video"]
        calls.append(threading.get_ident())
        return {"cursor": str(len(calls)), "busy": len(calls) == 1, "changed": True,
                "videos": [{"status": "processing" if len(calls) == 1 else "done"}]}

    bridge._dispatcher = dispatch

    async def run():
        params = StdioServerParameters(command=sys.executable,
                                      args=["-m", "haizflow.mcp", "--endpoint", bridge.endpoint])
        async with Client(params, raise_exceptions=True) as session:
            result = await session.call_tool("haizflow_wait", {"video_ids": ["private-test-video"],
                                                              "until": "idle", "timeout_seconds": 3})
            value = json.loads(result.content[0].text)
            assert not value["busy"] and not value["timed_out"] and value["videos"][0]["status"] == "done"
    in_worker(app, lambda: asyncio.run(run()))
    assert calls == [gui_thread, gui_thread]


def test_wait_transport_failure_does_not_repeat_any_request():
    from mcp import Client

    client = Mock()
    client.call.side_effect = DesktopClientError("MCP disabled; reconnect first.")

    async def run():
        async with Client(create_server(client), raise_exceptions=False) as session:
            result = await session.call_tool("haizflow_wait", {"timeout_seconds": 1})
            assert result.is_error and "MCP disabled" in str(result.content)
    asyncio.run(run())
    assert client.call.call_count == 1


def test_compact_profile_reduces_tool_schemas_without_losing_execute_access():
    from mcp import Client

    client = Mock()
    client.call.return_value = {"accepted": True}

    async def run():
        async with Client(create_server(client), raise_exceptions=True) as session:
            full = (await session.list_tools()).tools
        async with Client(create_server(client, tool_profile="compact"), raise_exceptions=True) as session:
            compact = (await session.list_tools()).tools
            assert len(full) == 27 and len(compact) == 9
            names = {item.name for item in compact}
            assert {"haizflow_execute", "haizflow_capabilities", "haizflow_status", "haizflow_list_projects",
                    "haizflow_preview_frames", "haizflow_subtitle_layout", "haizflow_wait"} <= names
            assert len(json.dumps([item.model_dump() for item in compact])) < len(
                json.dumps([item.model_dump() for item in full])) * .6
            # Detailed/destructive commands still pass through the same guarded
            # desktop dispatcher, never through hidden shell/file workarounds.
            await session.call_tool("haizflow_execute", {"command": "delete", "arguments": {"project_id": "p"}})
            client.call.assert_called_once_with("delete", {"project_id": "p"})
    asyncio.run(run())


def test_generated_compact_launch_configuration_works_over_real_stdio(app, bridge):
    from mcp import Client, StdioServerParameters

    async def run():
        config = json.loads(launch_configuration(bridge.endpoint))["mcpServers"]["haizflow"]
        async with Client(StdioServerParameters(**config), raise_exceptions=True) as session:
            assert len((await session.list_tools()).tools) == 9
            result = await session.call_tool("haizflow_status", {})
            assert not result.is_error
    in_worker(app, lambda: asyncio.run(run()))


def test_export_requires_explicit_overwrite_and_keeps_the_exact_path(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    target = tmp_path / "10.mp4"
    target.write_bytes(b"previous video")
    commands.host.exportVideoTo = Mock(return_value=True)
    arguments = {"video_id": "test-video", "destination": str(target)}
    with pytest.raises(ValueError, match="overwrite=true"):
        commands.dispatch("export", arguments)
    commands.host.exportVideoTo.assert_not_called()
    assert target.read_bytes() == b"previous video"
    assert commands.dispatch("export", {**arguments, "overwrite": True})["accepted"]
    commands.host.exportVideoTo.assert_called_once_with("test-video", "source", str(target), True)
    # The command delegates publication to the app; it never pre-deletes/renames a file.
    assert target.read_bytes() == b"previous video"


def test_export_defaults_remain_non_overwriting(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    target = tmp_path / "new.mp4"
    commands.host.exportVideoTo = Mock(return_value=True)
    assert commands.dispatch("export", {"video_id": "test-video", "destination": str(target)})["accepted"]
    commands.host.exportVideoTo.assert_called_once_with("test-video", "source", str(target), False)


def test_process_export_uses_one_app_job_and_checks_online_permission(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    video.project_type = "single"
    video.translation_model = "gemini-3.5-flash-lite"
    commands.host._build_config = lambda: VideoConfig(translation_model=video.translation_model)
    commands.host.processVideoTo = Mock(return_value=True)
    commands.host.exportVideoTo = Mock()
    arguments = {"video_id": video.video_id, "destination": str(tmp_path / "10.mp4"),
                 "overwrite": True, "process": True}
    bridge.setPermission("online", False)
    with pytest.raises(ValueError, match="online"):
        commands.dispatch("export", arguments)
    commands.host.processVideoTo.assert_not_called()
    bridge.setPermission("online", True)
    assert commands.dispatch("export", arguments)["accepted"]
    commands.host.processVideoTo.assert_called_once_with(video.video_id, "source", arguments["destination"], True)
    commands.host.exportVideoTo.assert_not_called()
    commands.host._project_commands.restart_selected_video.assert_not_called()


def test_manual_export_cannot_accidentally_start_auto_rerun(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    commands.host.processVideoTo = Mock()
    with pytest.raises(ValueError, match="Auto or Batch"):
        commands.dispatch("export", {"video_id": "test-video", "destination": str(tmp_path / "10.mp4"),
                                     "process": True})
    commands.host.processVideoTo.assert_not_called()


def test_export_status_reports_actual_ui_destination(commands):
    commands.host._video_exports.jobs = [{"videoId": "test-video", "status": "done", "progress": 100,
                                         "path": "E:/hongnguyenky/10.mp4"}]
    assert commands.dispatch("status", {})["exports"][0]["output"] == "E:/hongnguyenky/10.mp4"


def test_manual_force_rerun_is_explicit_and_still_checks_ownership(commands, bridge):
    bridge.setPermission("write", True)
    assert commands.dispatch("run", {"video_id": "test-video", "tool": "image", "force_rerun": True})["accepted"]
    commands.host.runManualTool.assert_called_once_with("image", True, confirm_existing_voice=False)
    commands.host._processing_queue.contains.return_value = True
    with pytest.raises(ValueError, match="busy"):
        commands.dispatch("run", {"video_id": "test-video", "tool": "image", "force_rerun": True})
    assert commands.host.runManualTool.call_count == 1


def test_partial_subtitle_style_preserves_unrelated_fields(commands, bridge):
    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    video.subtitle_style.font_size = 64
    video.subtitle_style.text_color = "#ABCDEF"
    commands.dispatch("configure", {"video_id": "test-video", "settings": {
        "subtitle_style": {"position_y_percent": 72},
    }})
    config = commands.host._apply_config_to_video.call_args.args[1]
    assert config.subtitle_style.position_y_percent == 72
    assert config.subtitle_style.font_size == 64
    assert config.subtitle_style.text_color == "#ABCDEF"


def test_local_source_replacement_delegates_to_normal_transaction(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    source = tmp_path / "new.mp4"
    source.write_bytes(b"new input")
    commands.host._project_import.replace_video.return_value = True
    assert commands.dispatch("replace_source", {"video_id": "test-video", "path": str(source)})["accepted"]
    commands.host._project_import.replace_video.assert_called_once_with("test-video", str(source.resolve()))
    commands.host._selected_video_id = "unrelated"
    with pytest.raises(ValueError, match="exact video"):
        commands.dispatch("replace_source", {"video_id": "test-video", "path": str(source)})
    assert commands.host._project_import.replace_video.call_count == 1


@pytest.fixture
def replacement_commands(commands, bridge):
    bridge.setPermission("write", True)
    bridge.setPermission("online", True)
    importer = SimpleNamespace(busy=False, _generation=0, url="", state="idle")

    def begin(_mode):
        importer._generation += 1
        importer.state = "idle"

    def inspect(url):
        importer._generation += 1
        importer.url = url
        importer.state = "inspecting"

    importer.begin, importer.inspect = Mock(side_effect=begin), Mock(side_effect=inspect)
    commands.host._url_importer = importer
    commands.host._video_source_key = Mock(return_value="original-source")
    commands.host.downloadInspectedVideo = Mock(side_effect=lambda: setattr(importer, "busy", True))
    return commands


@pytest.mark.parametrize("changed", ["source", "inspection", "url", "selection"])
def test_replacement_url_rejects_stale_or_wrong_target(replacement_commands, changed):
    commands = replacement_commands
    commands.dispatch("replace_url_inspect", {"video_id": "test-video", "url": "https://www.tiktok.com/video/1"})
    commands.host._url_importer.state = "ready"
    if changed == "source":
        commands.host._video_source_key.return_value = "different-source"
    elif changed == "inspection":
        commands.host._url_importer._generation += 1
    elif changed == "url":
        commands.host._url_importer.url = "https://www.tiktok.com/video/2"
    else:
        commands.host._selected_video_id = "other-video"
    with pytest.raises(ValueError):
        commands.dispatch("replace_url_start", {"video_id": "test-video"})
    commands.host.downloadInspectedVideo.assert_not_called()


def test_replacement_url_requires_ready_then_starts_only_once(replacement_commands):
    commands = replacement_commands
    arguments = {"video_id": "test-video"}
    commands.dispatch("replace_url_inspect", {**arguments, "url": "https://www.tiktok.com/video/1"})
    with pytest.raises(ValueError, match="ready"):
        commands.dispatch("replace_url_start", arguments)
    commands.host._url_importer.state = "ready"
    assert commands.dispatch("replace_url_start", arguments)["accepted"]
    with pytest.raises(ValueError, match="Inspect"):
        commands.dispatch("replace_url_start", arguments)
    commands.host.downloadInspectedVideo.assert_called_once()


def test_existing_source_still_cannot_be_replaced_by_ordinary_import(commands, bridge):
    bridge.setPermission("write", True)
    bridge.setPermission("online", True)
    with pytest.raises(ValueError, match="replace"):
        commands.dispatch("import_url_start", {"project_id": "project:test"})


def test_export_in_flight_blocks_source_and_subtitle_mutations(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    commands.host._video_exports.jobs = [{"videoId": "test-video", "status": "exporting"}]
    source = tmp_path / "source.mp4"
    source.touch()
    for command, arguments in [
        ("replace_source", {"video_id": "test-video", "path": str(source)}),
        ("remove_srt", {"video_id": "test-video"}),
        ("configure", {"video_id": "test-video", "settings": {"watermark_text": "changed"}}),
    ]:
        with pytest.raises(ValueError, match="busy"):
            commands.dispatch(command, arguments)
    commands.host._project_import.replace_video.assert_not_called()
    commands.host._project_commands.remove_selected_srt.assert_not_called()


def test_srt_replace_is_opt_in_and_remove_has_no_mcp_modal(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    source = tmp_path / "translated.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n", encoding="utf-8")
    commands.host._manual_subtitles.segments = [{"segment_id": "old"}]
    commands.host.importSelectedSrt = Mock(return_value=True)
    arguments = {"video_id": "test-video", "path": str(source), "language": "vi"}
    with pytest.raises(ValueError, match="replace=true"):
        commands.dispatch("import_srt", arguments)
    assert commands.dispatch("import_srt", {**arguments, "replace": True})["accepted"]
    commands.host.importSelectedSrt.assert_called_once_with(str(source.resolve()), "vi", "test-video")
    commands.host._project_commands.remove_selected_srt.return_value = True
    assert commands.dispatch("remove_srt", {"video_id": "test-video"})["accepted"]
    commands.host._project_commands.remove_selected_srt.assert_called_once_with("test-video", confirm=False)


def test_segment_export_routes_to_app_and_does_not_export_whole_video(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    commands.host.exportVideoSegmentTo = Mock(return_value=True)
    commands.host.exportVideoTo = Mock()
    destination = str(tmp_path / "range.mp4")
    assert commands.dispatch("export", {"video_id": "test-video", "destination": destination,
                                        "segment_id": "result-2"})["accepted"]
    commands.host.exportVideoSegmentTo.assert_called_once_with("test-video", "source", destination, False, "result-2")
    commands.host.exportVideoTo.assert_not_called()


def test_logs_are_bounded_redacted_and_do_not_follow_symlinks(commands, monkeypatch, tmp_path):
    monkeypatch.setattr("haizflow.services.video_store.get_video_dir", lambda _id: str(tmp_path))
    (tmp_path / "logs.txt").write_text("old\napi_key=PRIVATE cookie=SECRET https://example.com/?token=bad\n", "utf-8")
    result = commands.dispatch("logs", {"video_id": "test-video", "lines": 1})
    assert len(result["lines"]) == 1
    assert "PRIVATE" not in str(result) and "SECRET" not in str(result) and "example.com" not in str(result)
    with pytest.raises(ValueError):
        commands.dispatch("logs", {"video_id": "test-video", "lines": 501})


def test_mcp_error_redaction_masks_entire_bearer_and_cookie_headers(commands):
    result = commands._safe_detail("Authorization: Bearer PRIVATE_ACCESS_TOKEN\nCookie: session=PRIVATE; other=SECRET")
    assert "PRIVATE" not in result and "SECRET" not in result


def test_resource_actions_validate_pack_ids_and_permissions(commands, bridge):
    bridge.setPermission("write", True)
    bridge.setPermission("online", True)
    commands.host.resourcePackageRows = [{"packId": "model-vieneu"}]
    commands.host.repairResourcePack = Mock()
    commands.host.removeResourcePack = Mock(return_value=True)
    assert commands.dispatch("resource_repair", {"pack_id": "model-vieneu"})["accepted"]
    with pytest.raises(ValueError):
        commands.dispatch("resource_remove", {"pack_id": "../../outside"})
    bridge.setPermission("delete", True)
    assert commands.dispatch("resource_remove", {"pack_id": "model-vieneu"})["accepted"]
    commands.host.removeResourcePack.assert_called_once_with("model-vieneu")


def test_social_status_exposes_only_verified_public_post_urls(social_commands):
    commands, _item = social_commands
    social = commands.host._tiktok_publisher
    social.busy = False
    social.selected_platform = "tiktok"
    social._accounts = []
    social._publish_settings_snapshot.return_value = {}
    social._model_item.return_value = {"platform_post_url": "https://www.tiktok.com/@test/video/123"}
    result = commands.dispatch("social_status", {"project_id": "project:test"})
    assert result["items"][0]["post_url"].endswith("/123")


def test_social_remove_is_exact_queue_row_and_never_publishes(social_commands, bridge):
    commands, _item = social_commands
    bridge.setPermission("delete", True)
    social = commands.host._tiktok_publisher
    social.remove_item.return_value = True
    assert commands.dispatch("social_remove", {"project_id": "project:test", "item_id": "item-a"})["accepted"]
    social.remove_item.assert_called_once_with(0, confirm=False)
    social.publish_token.assert_not_called()


@pytest.mark.parametrize("command,extra,method,args", [
    ("clip_trim", {"clip_id": "clip-a", "edge": "left", "time_ms": 100}, "trimClip", ("clip-a", "left", 100)),
    ("clip_move", {"clip_id": "clip-a", "start_ms": 200}, "moveClip", ("clip-a", 200, "")),
    ("result_split", {"clip_id": "result-1", "time_ms": 500}, "splitResultClip", ("result-1", 500)),
    ("clip_remove", {"clip_ids": ["subtitle-1"]}, "removeClips", (["subtitle-1"], False)),
    ("background_music_clear", {}, "clearBackgroundMusic", ()),
    ("voice_reference_clear", {}, "clearVoiceCloneReference", ()),
])
def test_new_editor_commands_use_existing_app_workflows(commands, bridge, command, extra, method, args):
    bridge.setPermission("write", True)
    callback = Mock(return_value=True)
    setattr(commands.host, method, callback)
    assert commands.dispatch(command, {"video_id": "test-video", **extra})["accepted"]
    callback.assert_called_once_with(*args)


def test_options_uses_imported_subtitle_language_and_returns_real_model_ids(commands):
    video = commands.host._catalog_videos["test-video"]
    video.target_language, video.subtitle_language = "zh", "vi"
    commands.host.ttsProviderOptionsForLanguage = Mock(return_value=[{"value": "vieneu-gpu"}])
    commands.host.voiceOptionsForLanguageAndProvider = Mock(return_value=[])
    result = commands.dispatch("options", {"video_id": video.video_id})
    assert "gemini-3.5-flash-lite" in result["gemini_models"]
    commands.host.ttsProviderOptionsForLanguage.assert_called_once_with("vi")
    commands.host._apply_config_to_video.assert_not_called()


def test_batch_import_validates_all_sources_before_starting(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    commands.host._project_summaries_by_key["project:test"]["project_type"] = "batch"
    good = tmp_path / "good.mp4"
    good.touch()
    with pytest.raises(ValueError):
        commands.dispatch("batch_import", {"project_id": "project:test", "paths": [str(good), str(good) + ".missing"]})
    commands.host._project_import.import_batch_videos.assert_not_called()
    commands.host._project_import.import_batch_videos.return_value = True
    assert commands.dispatch("batch_import", {"project_id": "project:test", "paths": [str(good)]})["accepted"]


def test_batch_export_uses_app_job_and_exact_membership(commands, bridge, tmp_path):
    bridge.setPermission("write", True)
    commands.host._project_summaries_by_key["project:test"]["project_type"] = "batch"
    commands.host._batch_video_ids = ["test-video"]
    commands.host.processBatchTo = Mock(return_value=True)
    arguments = {"project_id": "project:test", "directory": str(tmp_path)}
    assert commands.dispatch("export_batch", arguments)["accepted"]
    commands.host.processBatchTo.assert_called_once_with(
        "project:test", ["test-video"], "source", str(tmp_path), False, False)
    commands.host._batch_video_ids = ["unknown-video"]
    with pytest.raises(ValueError):
        commands.dispatch("export_batch", arguments)
    assert commands.host.processBatchTo.call_count == 1


def test_channel_candidates_are_paginated_and_retried_by_stable_id(commands, bridge):
    from haizflow.schemas.channel_import import ChannelVideoCandidate

    bridge.setPermission("write", True)
    bridge.setPermission("online", True)
    commands.host._project_summaries_by_key["project:test"]["project_type"] = "download"
    candidate = ChannelVideoCandidate(remote_video_id="remote-a", source_url="https://example.com/?token=private",
                                      title="Video A", platform="tiktok", error="api_key=SECRET")
    model = SimpleNamespace(candidates=Mock(return_value=[candidate]))
    commands.host._media_downloader.channelCandidateModel = model
    result = commands.dispatch("channel_candidates", {"project_id": "project:test", "limit": 1})
    assert result["total"] == 1 and result["items"][0]["candidate_id"] == "remote-a"
    assert "SECRET" not in str(result) and "source_url" not in result["items"][0]
    assert commands.dispatch("channel_retry", {"project_id": "project:test", "candidate_id": "remote-a"})["accepted"]
    commands.host._media_downloader.retryChannelVideo.assert_called_once_with(0)
    with pytest.raises(ValueError):
        commands.dispatch("channel_retry", {"project_id": "project:test", "candidate_id": "old-id"})


def test_review_and_voice_commands_do_not_bypass_online_or_selection_guards(commands, bridge):
    bridge.setPermission("write", True)
    bridge.setPermission("online", False)
    commands.host.configureAndRunManualVoice = Mock(return_value=True)
    arguments = {"video_id": "test-video", "provider": "edge", "voice": "vi-VN-HoaiMyNeural"}
    with pytest.raises(ValueError, match="online"):
        commands.dispatch("voice_run", arguments)
    commands.host.configureAndRunManualVoice.assert_not_called()
    assert commands.dispatch("voice_run", {**arguments, "provider": "vieneu-gpu", "voice": "vieneu:Trúc Ly",
                                           "segment_id": "cue-a"})["accepted"]
    commands.host.configureAndRunManualVoice.assert_called_once_with(
        "vieneu-gpu", "vieneu:Trúc Ly", "segment", "cue-a", "single")
    commands.host.saveTranslationReviewDraft = Mock(return_value=True)
    with pytest.raises(ValueError):
        commands.dispatch("review_save", {"video_id": "test-video", "segments": []})
    commands.host.saveTranslationReviewDraft.assert_not_called()


def test_sdk_srt_replace_and_force_rerun_flags_are_discoverable_and_forwarded():
    from mcp import Client

    client = Mock()
    client.call.return_value = {"accepted": True}

    async def run():
        async with Client(create_server(client), raise_exceptions=True) as session:
            result = await session.call_tool("haizflow_import_srt", {
                "video_id": "test-video", "path": "E:/captions.srt", "language": "vi", "replace": True,
            })
            assert not result.is_error
            result = await session.call_tool("haizflow_run_tool", {
                "video_id": "test-video", "tool": "voice", "force_rerun": True,
            })
            assert not result.is_error

    asyncio.run(run())
    assert client.call.call_args_list[0].args == ("import_srt", {
        "video_id": "test-video", "path": "E:/captions.srt", "language": "vi", "replace": True,
    })
    assert client.call.call_args_list[1].args == ("run", {
        "video_id": "test-video", "tool": "voice", "force_rerun": True,
    })


def test_layout_apply_rejects_stale_preview_and_preserves_other_styles(commands, bridge, monkeypatch):
    from haizflow.mcp.visuals import revision

    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    context = {"width": 720, "height": 1280, "style": video.subtitle_style.model_dump(),
               "crop": video.crop.model_dump(), "output_format": "keep_ratio", "cues": []}
    context["revision"] = revision(context)
    monkeypatch.setattr(commands, "_visual_context", lambda _id: context)
    arguments = {"video_id": video.video_id, "style_patch": {"position_y_percent": 70},
                 "expected_revision": "old-preview"}
    with pytest.raises(ValueError, match="changed"):
        commands.dispatch("subtitle_layout_apply", arguments)
    commands.host._apply_config_to_video.assert_not_called()
    assert commands.dispatch("subtitle_layout_apply", {
        **arguments, "expected_revision": context["revision"],
    })["accepted"]
    config = commands.host._apply_config_to_video.call_args.args[1]
    assert config.subtitle_style.position_y_percent == 70
    assert config.subtitle_style.text_color == video.subtitle_style.text_color
    assert config.subtitle_layout_override


def test_visual_context_rejects_foreign_media_paths(commands, monkeypatch, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "other.mp4"
    outside.write_bytes(b"other user's media")
    commands.host._catalog_videos["test-video"].files["video_input"] = str(outside)
    monkeypatch.setattr("haizflow.services.video_store.get_video_dir", lambda _id: str(root))
    with pytest.raises(ValueError, match="workspace"):
        commands.dispatch("visual_context", {"video_id": "test-video"})


def test_visual_context_is_readonly_json_and_bound_to_source_identity(commands, monkeypatch, tmp_path):
    from haizflow.mcp.visuals import revision

    source = tmp_path / "input.mp4"
    source.write_bytes(b"private test media")
    video = commands.host._catalog_videos["test-video"]
    video.files["video_input"] = str(source)
    video.video_width, video.video_height = 720, 1280
    commands.host._video_source_key = Mock(return_value="source-v1")
    commands.host.reviewSegments = []
    monkeypatch.setattr("haizflow.services.video_store.get_video_dir", lambda _id: str(tmp_path))
    monkeypatch.setattr("haizflow.services.editor_documents.load", lambda _id: None)
    monkeypatch.setattr("haizflow.services.video_export.current_render", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("haizflow.pipeline.manual_tools._ocr_region", lambda _video: None)
    result = commands.dispatch("visual_context", {"video_id": video.video_id})
    assert result["source_path"] == str(source.resolve())
    assert result["revision"] == revision(result)
    json.dumps(result)
    source.write_bytes(b"changed private media")
    changed = commands.dispatch("visual_context", {"video_id": video.video_id})
    assert changed["revision"] != result["revision"]
    commands.host._apply_config_to_video.assert_not_called()


def test_manual_translation_patch_is_one_editor_command_and_stales_only_changed_voice(commands, bridge, monkeypatch):
    from haizflow.schemas.editor import EditorClip, EditorDocument

    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    state = {"revision": "review-v1", "source": [], "segments": [
        {"segment_id": "a", "start": 0, "end": 2, "text": "Bạn tới rồi."},
        {"segment_id": "b", "start": 2, "end": 4, "text": "Chào anh."},
    ]}
    monkeypatch.setattr(commands, "_translation_snapshot", lambda _id: (video, state))
    document = EditorDocument(video_id=video.video_id, clips=[
        EditorClip(clip_id="sub-a", track_id="subtitles", kind="subtitle", segment_id="a", name="Bạn tới rồi.",
                   duration_ms=2000),
        EditorClip(clip_id="voice-a", track_id="voice", kind="voice", segment_id="a", name="Bạn tới rồi.",
                   duration_ms=2000),
        EditorClip(clip_id="voice-b", track_id="voice", kind="voice", segment_id="b", name="Chào anh.",
                   duration_ms=2000),
    ])
    def apply(_label, callback):
        callback(document)
        return True
    commands.host._apply_editor_mutation = Mock(side_effect=apply)
    result = commands.dispatch("translation_patch", {"video_id": video.video_id, "expected_revision": "review-v1",
        "edits": [{"cue_id": "cue-1", "expected_text": "Bạn tới rồi.", "text": "Chị tới rồi."}]})
    assert result["accepted"] and result["processing_started"] is False
    assert document.clips[0].name == "Chị tới rồi."
    assert not document.clips[1].enabled and document.clips[2].enabled
    commands.host._apply_editor_mutation.assert_called_once()
    commands.host.runManualTool.assert_not_called()
    commands.host._project_commands.approve_translation_review.assert_not_called()


def test_sdk_export_forwards_explicit_replacement_and_process_flags():
    from mcp import Client

    client = Mock()
    client.call.return_value = {"accepted": True}

    async def run():
        async with Client(create_server(client), raise_exceptions=True) as session:
            result = await session.call_tool("haizflow_export_video", {
                "video_id": "test-video", "destination": "E:/hongnguyenky/10.mp4",
                "overwrite": True, "process": True,
            })
            assert not result.is_error

    asyncio.run(run())
    client.call.assert_called_once_with("export", {
        "video_id": "test-video", "destination": "E:/hongnguyenky/10.mp4", "preset": "source",
        "overwrite": True, "process": True, "segment_id": "",
    })


@pytest.mark.parametrize(
    "method,params",
    [
        ("__dict__", {}),
        ("delete_current_project", {}),
        ("status", {"extra": "x"}),
        ("projects", {"limit": True}),
        ("projects", {"offset": -1}),
        ("projects", {"limit": 10000}),
    ],
)
def test_unknown_commands_and_invalid_arguments_rejected(commands, method, params):
    with pytest.raises(ValueError):
        commands.dispatch(method, params)


def test_readonly_does_not_mutate_and_write_needs_permission(commands, bridge):
    assert commands.dispatch("video", {"video_id": "test-video"})["video_id"] == "test-video"
    with pytest.raises(ValueError, match="permission"):
        commands.dispatch("run", {"video_id": "test-video", "tool": "voice"})
    commands.host.runManualTool.assert_not_called()
    bridge.setPermission("write", True)
    with pytest.raises(ValueError, match="Unknown video"):
        commands.dispatch("run", {"video_id": "../../somewhere", "tool": "voice"})


def test_online_permission_checks_effective_ui_config(commands, bridge):
    bridge.setPermission("write", True)
    commands.host._build_config = lambda: VideoConfig(tts_provider="edge")
    with pytest.raises(ValueError, match="online"):
        commands.dispatch("run", {"video_id": "test-video", "tool": "voice"})
    commands.host.runManualTool.assert_not_called()


def test_selection_and_cache_owner_guard(commands, bridge):
    bridge.setPermission("write", True)
    commands.host._selected_video_id = "another"
    with pytest.raises(ValueError, match="exact video"):
        commands.dispatch("configure", {"video_id": "test-video", "settings": {"output_speed": 2.0}})
    commands.host._apply_config_to_video.assert_not_called()


def test_delete_executes_directly_with_permission_and_preflight_is_optional(commands, bridge):
    with pytest.raises(ValueError, match="permission"):
        commands.dispatch("delete", {"project_id": "project:test"})
    bridge.setPermission("delete", True)
    request = commands.dispatch("prepare_delete", {"project_id": "project:test"})
    assert request["ready"] and request["requires_confirmation"] is False
    assert bridge.approval == {}
    commands.host._project_commands._delete_confirmed_project.assert_not_called()
    commands.host._project_commands._delete_confirmed_project.return_value = True
    assert commands.dispatch("delete", {"project_id": "project:test"})["accepted"]
    commands.host._project_commands._delete_confirmed_project.assert_called_once()
    commands.host._project_commands.is_deleting.return_value = True
    with pytest.raises(ValueError):
        commands.dispatch("delete", {"project_id": "project:test"})


def test_delete_rejects_active_project(commands, bridge):
    bridge.setPermission("delete", True)
    commands.host._processing_queue.contains.return_value = True
    with pytest.raises(ValueError, match="pause/cancel"):
        commands.dispatch("prepare_delete", {"project_id": "project:test"})
    with pytest.raises(ValueError, match="pause/cancel"):
        commands.dispatch("delete", {"project_id": "project:test"})


def test_configuration_cannot_inject_file_paths(commands, bridge):
    bridge.setPermission("write", True)
    with pytest.raises(ValueError, match="Unknown"):
        commands.dispatch("configure", {"video_id": "test-video", "settings": {"background_music_path": "secret"}})
    commands.host._apply_config_to_video.assert_not_called()


def test_every_direct_host_method_exists():
    import ast
    from pathlib import Path

    from haizflow.desktop.qml_controller import HaizFlowController

    tree = ast.parse(Path("src/haizflow/desktop/mcp_commands.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "self"
                and owner.attr == "host"
            ):
                assert hasattr(HaizFlowController, node.func.attr), node.func.attr


@pytest.fixture
def social_commands(commands, bridge, tmp_path):
    bridge.setPermission("publish", True)
    bridge.setPermission("online", True)
    host = commands.host
    host._project_summaries_by_key["project:test"]["project_type"] = "publish"
    file = tmp_path / "post.mp4"
    file.write_bytes(b"test video")
    item = {"id": "item-a", "file_path": str(file), "caption": "Caption", "hashtags": "#test", "status": "draft"}
    social = Mock()
    social._state = {"selected_account_id": "account-one"}
    social._consent_confirmed = False
    social.selected_platform = "tiktok"
    social._queue_items.return_value = [item]
    social._waiting_to_publish.side_effect = lambda value: value["status"] == "draft"
    social._publish_settings_snapshot.return_value = {"privacy_level": "SELF_ONLY", "publish_now": True}
    social.publish_token.return_value = True
    host._tiktok_publisher = social
    return commands, item


def test_social_publish_executes_without_ui_confirmation_and_only_for_exact_items(social_commands, bridge):
    commands, item = social_commands
    request = commands.dispatch("prepare_publish", {"project_id": "project:test", "item_ids": [item["id"]]})
    arguments = {
        "project_id": "project:test",
        "item_ids": [item["id"]],
    }
    assert request["ready"] and request["requires_confirmation"] is False
    commands.host._tiktok_publisher.publish_token.assert_not_called()
    assert bridge.approval == {}
    assert commands.dispatch("publish", arguments)["accepted_item_ids"] == [item["id"]]
    commands.host._tiktok_publisher.publish_token.assert_called_once_with("project:test:item-a")
    item["status"] = "uploading"
    with pytest.raises(ValueError):
        commands.dispatch("publish", arguments)


@pytest.mark.parametrize("changed", ["status", "revoke", "offline", "missing_account", "missing_file"])
def test_social_publish_revalidates_readiness_and_permissions(social_commands, bridge, changed):
    commands, item = social_commands
    commands.dispatch("prepare_publish", {"project_id": "project:test", "item_ids": [item["id"]]})
    social = commands.host._tiktok_publisher
    if changed == "status":
        item["status"] = "published"
    elif changed == "offline":
        bridge.setPermission("online", False)
    elif changed == "missing_account":
        social._state["selected_account_id"] = ""
    elif changed == "missing_file":
        item["file_path"] += ".missing"
    else:
        bridge.setPermission("publish", False)
    with pytest.raises(ValueError):
        commands.dispatch(
            "publish",
            {
                "project_id": "project:test",
                "item_ids": [item["id"]],
            },
        )
    social.publish_token.assert_not_called()


def test_manual_translation_does_not_require_a_second_app_confirmation(commands, bridge):
    bridge.setPermission("write", True)
    assert commands.dispatch("run", {"video_id": "test-video", "tool": "translation"})["accepted"]
    commands.host.runManualTool.assert_called_once_with("translation", False, confirm_existing_voice=False)


def test_restart_executes_directly_and_still_rejects_busy_video(commands, bridge):
    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    video.project_type = "single"
    video.status = "done"
    assert commands.dispatch("prepare_restart", {"video_id": "test-video"})["requires_confirmation"] is False
    commands.host._project_commands.restart_selected_video.side_effect = (
        lambda **_kwargs: setattr(commands.host._processing_queue.contains, "return_value", True))
    assert commands.dispatch("restart", {"video_id": "test-video"})["accepted"]
    commands.host._project_commands.restart_selected_video.assert_called_once_with(confirm=False)
    with pytest.raises(ValueError, match="busy"):
        commands.dispatch("restart", {"video_id": "test-video"})


def test_pipe_replay_conflict_revocation_and_bad_frames(bridge):
    class Socket:
        def __init__(self, data):
            self.data, self.response, self.aborted = data, b"", False

        def readAll(self):
            value, self.data = self.data, b""
            return value

        def write(self, data):
            self.response += data

        def disconnectFromServer(self):
            pass

        def abort(self):
            self.aborted = True

    calls = []
    bridge._dispatcher = lambda method, params: calls.append(method) or {"ok": True}
    request = {"version": 1, "id": "fixed-id", "method": "create", "params": {}}

    def send(data):
        socket = Socket(data)
        bridge._connections[socket] = bytearray()
        bridge._read(socket, Mock())
        return json.loads(socket.response) if socket.response else None

    data = encode_frame(request, MAX_REQUEST)
    assert send(data)["result"] == {"ok": True}
    assert send(data)["result"] == {"ok": True}
    assert calls == ["create"]
    assert "error" in send(encode_frame({**request, "method": "delete"}, MAX_REQUEST))
    bridge.setPermission("write", True)
    assert "error" in send(data)
    assert calls == ["create"]
    assert "error" in send(b"[]\n")
    assert "error" in send(b"{}\n{}\n")
    assert "error" in send(b"not-json\n")


def test_model_discovery_uses_filtered_cached_openrouter_metadata_without_keys(commands, monkeypatch):
    from haizflow.services import translation_catalog_cache, translation_connections, translation_privacy

    identifier = "a" * 32
    monkeypatch.setattr(translation_connections, "get_connection", lambda value: {
        "id": identifier, "provider": "openrouter", "model": "", "format": "json_object"})
    monkeypatch.setattr(translation_connections.secure_credentials, "read_secret",
                        Mock(side_effect=AssertionError("Discovery must never read secrets")))
    monkeypatch.setattr(translation_privacy, "allowed", lambda profile: False)
    monkeypatch.setattr(translation_catalog_cache, "load", lambda: [
        {"value": "vendor/paid", "label": "A paid", "pricing_kind": "paid"},
        {"value": "nvidia/nemotron-3.5-super-vl:free", "label": "Nemotron", "pricing_kind": "free"},
        {"value": "dots-studio/dots-3-note-preview:free", "label": "Dots", "pricing_kind": "free"}])
    result = commands.dispatch("translation_models", {"connection_id": identifier, "limit": 1})
    assert result["total"] == 3 and result["has_more"]
    assert result["provider"] == "openrouter" and result["catalogue"] == "offline_cached"
    first = result["items"][0]
    assert first["model"] == "dots-studio/dots-3-note-preview:free"
    assert first["value"] == f"api:{identifier}:" + first["model"]
    assert first["reasoning"]["toggle"] and first["pricing_kind"] == "free"
    assert "base_url" not in str(result) and "api_key" not in str(result)
    result = commands.dispatch("translation_models", {
        "provider": "openrouter", "query": "NEMOTRON", "free_only": True})
    assert result["total"] == 1 and not result["has_more"]
    assert result["items"][0]["data_collection"]["required"]
    assert not result["items"][0]["data_collection"]["allowed"]
    assert "collect" in result["items"][0]["data_collection"]["notice"]
    result = commands.dispatch("translation_models", {"provider": "openrouter", "offset": 1, "free_only": True})
    assert result["total"] == 2 and len(result["items"]) == 1
    assert result["requires_connection"] and "quota" in result["availability"]


def test_model_discovery_and_scoped_options_work_in_read_many(commands):
    result = commands.dispatch("read_many", {"requests": [
        {"command": "translation_models", "arguments": {"provider": "gemini", "query": "3.5"}},
        {"command": "options", "arguments": {"video_id": "test-video", "section": "export"}}]})
    rows = result["results"]
    assert rows[0]["result"]["items"][0]["reasoning"]["default"] == "minimal"
    assert rows[1]["result"] == {"export_presets": ["source", "1080p", "1080p-high", "720p", "2160p"]}
    assert commands.host._apply_config_to_video.call_count == 0


@pytest.mark.parametrize("arguments", [{"limit": 0}, {"limit": 201}, {"offset": -1},
    {"provider": "unknown"}, {"query": "x" * 201}, {"free_only": "true"}, {"connection_id": "missing"}])
def test_bad_model_discovery_is_rejected_before_any_mutation(commands, arguments):
    with pytest.raises(ValueError):
        commands.dispatch("translation_models", arguments)
    commands.host._apply_config_to_video.assert_not_called()


def test_scoped_translation_snapshot_omits_voice_and_large_guidance(commands, monkeypatch):
    from haizflow.mcp.efficiency import encoded_size
    from haizflow.services import translation_connections

    video = commands.host._catalog_videos["test-video"]
    video.translation_model = "gemini-3.5-flash-lite"
    video.gemini_translation_style = "natural"
    video.gemini_translation_instructions = "x" * 4000
    monkeypatch.setattr(translation_connections, "list_connections", lambda: [])
    result = commands.dispatch("options", {"video_id": video.video_id, "section": "translation"})
    assert result["style"] == "natural" and result["reasoning"]["effective"] == "minimal"
    assert result["selected_reasoning"] == "" and result["model_lookup"] == "translation_models"
    assert "natural" in result["styles"] and "voices" not in result
    assert "instructions" not in result and encoded_size(result) < 1200


@pytest.mark.parametrize("language,sample,expected", [
    ("ja", "日本語", "Dela Gothic One"), ("ko", "안녕하세요", "Pretendard ExtraBold"),
    ("zh", "你好", "Noto Sans SC Black"), ("vi", "Xin chào", "Bangers")])
def test_font_discovery_follows_published_subtitle_language(commands, language, sample, expected):
    video = commands.host._catalog_videos["test-video"]
    video.subtitle_language, video.target_language = language, "en"
    result = commands.dispatch("subtitle_fonts", {"video_id": video.video_id, "sample": sample})
    assert result["language"] == language and result["effective"] == expected
    assert result["automatic_by_script"] and expected in result["families"]
    assert commands.dispatch("options", {"video_id": video.video_id, "section": "subtitles"})["language"] == language
    commands.host._apply_config_to_video.assert_not_called()


@pytest.mark.parametrize("project_type", ["manual", "single"])
@pytest.mark.parametrize("effort", ["", "minimal", "high"])
def test_configure_style_keeps_reasoning_and_new_model_resets_it(commands, bridge, project_type, effort):
    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    video.project_type, video.translation_model = project_type, "gemini-3.5-flash-lite"
    video.translation_reasoning_effort = effort
    commands.dispatch("configure", {"video_id": video.video_id, "settings": {"gemini_translation_style": "natural"}})
    config = commands.host._apply_config_to_video.call_args.args[1]
    assert config.translation_reasoning_effort == effort and config.gemini_translation_style == "natural"
    commands.dispatch("configure", {"video_id": video.video_id, "settings": {"translation_model": "gemini-3.8-flash"}})
    assert commands.host._apply_config_to_video.call_args.args[1].translation_reasoning_effort == ""
    calls = commands.host._apply_config_to_video.call_count
    with pytest.raises(ValueError, match="reasoning"):
        commands.dispatch("configure", {"video_id": video.video_id, "settings": {
            "translation_model": "gemini-3.8-flash", "translation_reasoning_effort": "minimal"}})
    assert commands.host._apply_config_to_video.call_count == calls


def test_batch_configure_uses_batch_fields_without_opening_confirmation(commands, bridge):
    from haizflow.services import batch_settings

    bridge.setPermission("write", True)
    video = commands.host._catalog_videos["test-video"]
    commands.host._project_summaries_by_key["project:test"]["project_type"] = "batch"
    current = batch_settings.values_for(video)
    current.update(translationModel="gemini-3.5-flash-lite", translationReasoningEffort="high")
    commands.host.batchSettings = Mock(return_value=current)
    commands.host.applyBatchSettingsValues = Mock(side_effect=AssertionError("Must not open a modal"))
    apply = commands.host._project_commands.apply_batch_settings_values
    apply.return_value = True
    result = commands.dispatch("batch_configure", {"project_id": "project:test",
        "settings": {"geminiTranslationStyle": "natural"}, "replace_overrides": True})
    assert result["accepted"]
    apply.assert_called_once_with("project:test", {"geminiTranslationStyle": "natural"}, True)
    commands.dispatch("batch_configure", {"project_id": "project:test",
        "settings": {"translationModel": "gemini-3.8-flash"}})
    assert apply.call_args.args[1]["translationReasoningEffort"] == ""
    for settings in ({"translationModel": "gemini-3.8-flash", "translationReasoningEffort": "minimal"},
                     {"translation_model": "gemini-3.8-flash"}, {}, {"translationModel": 42}):
        count = apply.call_count
        with pytest.raises(ValueError):
            commands.dispatch("batch_configure", {"project_id": "project:test", "settings": settings})
        assert apply.call_count == count


def test_voice_studio_and_library_are_no_longer_exposed(commands, bridge):
    removed = {
        "voice_design", "voice_design_status", "voice_design_cancel", "voice_presets",
        "voice_preset_save", "voice_preset_archive", "voice_audio_export",
        "voice_audio_export_status", "voice_audio_export_cancel", "voice_studio_logs",
        "vieneu_studio_status", "vieneu_reference_import", "vieneu_preview",
        "vieneu_preview_cancel", "vieneu_preset_save",
    }
    schema = commands.dispatch("capabilities", {"area": "voice"})
    assert not removed & schema["commands"].keys()
    assert {"voice_configuration", "voice_run", "voice_reference", "voice_reference_clear"} <= schema["commands"].keys()
    bridge.setPermission("write", True)
    for name in removed:
        assert name not in COMMANDS
        assert not hasattr(commands, "_" + name)
        with pytest.raises(ValueError):
            commands.dispatch(name, {})


def test_manual_voice_selection_reuses_bounded_controller_contract(commands, bridge):
    video = commands.host._catalog_videos["test-video"]
    video.project_type = "manual"
    commands.host._project_type = "manual"
    commands.host.configureAndRunManualVoice = Mock(return_value=True)
    bridge.setPermission("write", True)
    assert commands.dispatch("voice_run", {"video_id": video.video_id,
        "provider": "vieneu-gpu", "voice": "vieneu:Trúc Ly", "segment_ids": ["a", "c"]})["accepted"]
    commands.host.configureAndRunManualVoice.assert_called_once_with(
        "vieneu-gpu", "vieneu:Trúc Ly", "selection", "", "single", ["a", "c"])
    for patch in ({"segment_ids": []}, {"segment_ids": ["a", "a"]}, {"segment_ids": ["a"], "segment_id": "b"}):
        with pytest.raises(ValueError):
            commands.dispatch("voice_run", {"video_id": video.video_id,
                "provider": "vieneu-gpu", "voice": "vieneu:Trúc Ly", **patch})
