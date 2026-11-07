"""Real Qt controller and QML exercised in a subprocess with pytest's isolated data root."""

import subprocess
import sys
from pathlib import Path


def check_native():
    import tempfile
    import threading
    import time

    from PySide6.QtCore import Q_ARG, QMetaObject, QUrl
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow

    from haizflow.desktop.qml_controller import HaizFlowController
    from haizflow.services import desktop_settings, project_store

    app = QGuiApplication.instance() or QGuiApplication([])
    for font_name in ("SegUIVar.ttf", "segoeui.ttf", "segmdl2.ttf"):
        font_path = Path("C:/Windows/Fonts") / font_name
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI"))
    desktop_settings.save_settings({"keep_models_warm": False})
    HaizFlowController._start_startup_maintenance = lambda self: None
    host = HaizFlowController()
    bridge = host.mcpBridge
    assert not bridge.enabled
    assert bridge.setEnabled(True)
    assert all(bridge.permissions.values())
    bridge.setPermission("write", True)
    bridge.setPermission("delete", True)
    dispatch = bridge._dispatcher
    assert dispatch("status", {})["permissions"]["delete"]
    assert dispatch("resources", {})["packs"]
    assert len(dispatch("capabilities", {})["commands"]) >= 60
    with tempfile.TemporaryDirectory(prefix="mcp-test-project-") as directory:
        host._project_directory = directory
        result = dispatch("create", {"name": "MCP test only", "kind": "manual"})
        assert result["accepted"]
        project_id = result["project_id"]
        project = project_store.get_project(project_id)
        project_root = Path(project["project_root"])
        assert project_root.is_dir()
        assert dispatch("project", {"project_id": project_id})["videos"] == []

        # Exercise the real controller through a real stdio adapter, not only
        # direct dispatcher calls, while the Qt event loop services the pipe.
        failures = []

        def read_via_stdio():
            import asyncio

            from mcp import Client
            from mcp.client.stdio import StdioServerParameters

            async def read():
                params = StdioServerParameters(command=sys.executable,
                                              args=["-m", "haizflow.mcp", "--endpoint", bridge.endpoint])
                async with Client(params, raise_exceptions=False) as session:
                    result = await session.call_tool("haizflow_status", {})
                    assert not result.is_error
                    result = await session.call_tool("haizflow_execute", {
                        "command": "translation_models", "arguments": {"provider": "gemini", "query": "3.5"}})
                    assert not result.is_error and "minimal" in str(result.content)
                    result = await session.call_tool("haizflow_execute", {"command": "capabilities", "arguments": {}})
                    assert not result.is_error and "subtitle_fonts" in str(result.content)
                    assert "input_schema" not in str(result.content)
                    result = await session.call_tool("haizflow_list_projects", {})
                    assert not result.is_error and project_id in str(result.content)
                    result = await session.call_tool("haizflow_list_projects", {"limit": -1})
                    assert result.is_error and "limit must be between 1 and 200" in str(result.content)

            try:
                asyncio.run(read())
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=read_via_stdio, daemon=True)
        worker.start()
        deadline = time.monotonic() + 20
        while worker.is_alive() and time.monotonic() < deadline:
            app.processEvents()
            worker.join(.005)
        assert not worker.is_alive(), "Native MCP client did not finish"
        assert not failures, failures

        engine = QQmlEngine()
        component = QQmlComponent(engine)
        qml_dir = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
        engine.rootContext().setContextProperty("testBridge", bridge)
        component.setData(
            (
                f'import QtQuick\nimport QtQuick.Controls.Basic\nimport "{qml_dir.as_uri()}"\n'
                "ApplicationWindow { width: 960; height: 900; visible: true; color: Theme.window; "
                "McpSettingsPage { id: panel; anchors.fill: parent; anchors.margins: 20; bridge: testBridge } }"
            ).encode(),
            QUrl(),
        )
        assert not component.isError(), [error.toString() for error in component.errors()]
        window = component.create()
        assert window, [error.toString() for error in component.errors()]
        assert isinstance(window, QQuickWindow)
        for _ in range(12):
            app.processEvents()
        assert window.findChild(object, "mcpEnabledSwitch") is not None
        for name in ("mcpWriteSwitch", "mcpOnlineSwitch", "mcpDeleteSwitch", "mcpPublishSwitch"):
            switch = window.findChild(object, name)
            assert switch is not None and switch.property("checked") is True
        online = window.findChild(object, "mcpOnlineSwitch")
        online.setProperty("checked", False)
        QMetaObject.invokeMethod(online, "toggled")
        app.processEvents()
        assert not bridge.permissions["online"] and bridge.permissions["write"]
        assert bridge.setEnabled(True)
        app.processEvents()
        assert online.property("checked") is False
        guide = window.findChild(object, "mcpConnectionGuide")
        client = window.findChild(object, "mcpGuideClient")
        configuration = window.findChild(object, "mcpGuideConfiguration")
        copy_button = window.findChild(object, "mcpGuideCopyButton")
        assert guide and client and configuration and copy_button
        test_button = window.findChild(object, "mcpTestConnectionButton")
        assert test_button and QMetaObject.invokeMethod(test_button, "clicked")
        deadline = time.monotonic() + 20
        while bridge.connectionState == "checking" and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert bridge.connectionState == "success", bridge.connectionMessage
        assert "nội bộ" in bridge.connectionMessage
        assert window.findChild(object, "mcpLaunchCommand").property("text") == bridge.launchDetails["command"]
        assert not guide.property("troubleshootingExpanded")
        troubleshoot = window.findChild(object, "mcpGuideTroubleshootingToggle")
        assert QMetaObject.invokeMethod(troubleshoot, "clicked")
        app.processEvents()
        assert guide.property("troubleshootingExpanded")
        assert QMetaObject.invokeMethod(troubleshoot, "clicked")
        app.processEvents()
        assert not guide.property("troubleshootingExpanded")
        import json
        import tomllib

        for index in range(5):
            client.setProperty("currentIndex", index)
            QMetaObject.invokeMethod(client, "activated", Q_ARG(int, index))
            app.processEvents()
            text = configuration.property("text")
            if index == 0:
                assert "haizflow" in tomllib.loads(text)["mcp_servers"]
            elif index == 1:
                assert "haizflow" in json.loads(text[text.index("{"):])["mcpServers"]
                assert "haizflow_status" in text
            else:
                assert "haizflow" in json.loads(text)["mcpServers"]
            assert QMetaObject.invokeMethod(copy_button, "clicked")
            assert app.clipboard().text() == text
            assert guide.property("copied")
            assert guide.property("setupInstructions")
            assert guide.property("reconnectInstructions")
        client.setProperty("currentIndex", 0)
        app.processEvents()
        window.setWidth(760)
        window.setHeight(720)
        for _ in range(6):
            app.processEvents()
        assert guide.property("width") <= 720
        window.setWidth(960)
        window.setHeight(900)
        for _ in range(6):
            app.processEvents()
        capture = guide.grabToImage()
        if capture:
            deadline = time.monotonic() + 2
            while capture.image().isNull() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            if not capture.image().isNull():
                capture.saveToFile(str(Path(__file__).parents[1] / "build/mcp-guide-review.png"))
        from PySide6.QtCore import QTranslator

        translator = QTranslator()
        assert translator.load(str(qml_dir.parent / "translations/haizflow_en.qm"))
        app.installTranslator(translator)
        engine.retranslate()
        app.processEvents()
        assert guide.property("title") == "Connection guide"
        assert "Open the Codex" in guide.property("setupInstructions"), (
            client.property("currentIndex"), guide.property("setupInstructions"))
        assert "Server missing" in window.findChild(object, "mcpGuideTroubleshooting").property("text")
        app.removeTranslator(translator)
        engine.retranslate()
        request = dispatch("prepare_delete", {"project_id": project_id})
        assert request["requires_confirmation"] is False
        assert project_root.is_dir()  # preparing is never destructive
        for _ in range(12):
            app.processEvents()
        image = window.grabWindow()
        if not image.isNull():
            image.save(str(Path(__file__).parents[1] / "build/mcp-settings-review.png"))
        assert dispatch("delete", {"project_id": project_id})[
            "accepted"
        ]
        deadline = time.monotonic() + 10
        while project_root.exists() and time.monotonic() < deadline:
            host._project_commands.drain_deletion_events()
            app.processEvents()
            time.sleep(0.02)
        assert not project_root.exists()
        host._project_commands.drain_deletion_events()
        bridge.setEnabled(False)
        assert not any(bridge.permissions.values())
        window.close()
        window.deleteLater()
        del engine
    host.shutdown()
    print("MCP_NATIVE_OK")


def test_mcp_dedicated_routes_menu_and_page_ownership():
    qml = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
    main = (qml / "Main.qml").read_text(encoding="utf-8")
    menu = (qml / "AppMenuBar.qml").read_text(encoding="utf-8")
    workspace = (qml / "SettingsWorkspace.qml").read_text(encoding="utf-8")
    routes = (qml / "RouteHost.qml").read_text(encoding="utf-8")
    assert 'routeMcp: "mcp"' in main
    assert "onMcpRequested: root.navigate(root.routeMcp)" in main
    assert 'objectName: "mcpSettingsMenuItem"' in menu
    assert "onTriggered: root.mcpRequested()" in menu
    assert '"mcp": 13' in routes
    assert "selected: settingsPages.currentIndex === 3" in workspace
    assert "sourceComponent: Component { McpSettingsPage {} }" in workspace
    assert "SettingsMcpGroup {" not in (qml / "SettingsPage.qml").read_text(encoding="utf-8")
    guide = (qml / "McpConnectionGuide.qml").read_text(encoding="utf-8")
    assert "chatgpt" not in guide.lower()
    assert "ExternalTextLink" not in guide
    assert "stepNumber: 5" in guide


def test_mcp_real_controller_qml_and_project_delete():
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve())],
        capture_output=True, encoding="utf-8", errors="replace", timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MCP_NATIVE_OK" in result.stdout


def test_mcp_guide_strings_have_english_translations():
    import json
    import re
    import xml.etree.ElementTree as ET

    desktop = Path(__file__).parents[1] / "src/haizflow/desktop"
    catalog = ET.parse(desktop / "translations/haizflow_en.ts").getroot()
    for context_name in ("McpConnectionGuide", "SettingsMcpGroup", "McpLaunchFields"):
        context = next(item for item in catalog.findall("context") if item.findtext("name") == context_name)
        translations = {item.findtext("source"): item.findtext("translation") for item in context.findall("message")}
        source = (desktop / "qml" / f"{context_name}.qml").read_text("utf-8")
        for literal in re.findall(r'qsTr\(("(?:[^"\\]|\\.)*")\)', source):
            value = json.loads(literal)
            assert translations.get(value), f"Missing English translation: {value}"


if __name__ == "__main__":
    check_native()
