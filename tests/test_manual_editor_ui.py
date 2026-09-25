from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


QML_DIR = Path(__file__).resolve().parents[1] / "src" / "haizflow" / "desktop" / "qml"


def test_manual_toolbar_loads_and_exposes_compact_actions():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "ManualEditorToolbar.qml")))
    assert component.isReady(), "\n".join(error.toString() for error in component.errors())
    toolbar = component.createWithInitialProperties({"width": 1280.0, "hasVideo": True})
    try:
        assert toolbar is not None, "\n".join(error.toString() for error in component.errors())
        assert toolbar.property("comparing") is False
        assert toolbar.property("hasVideo") is True
    finally:
        if toolbar is not None:
            toolbar.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_manual_workspace_components_parse():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    try:
        for name in (
            "ManualWorkspace.qml",
            "ManualComparePreview.qml",
            "ManualStageInspector.qml",
            "SubtitleTimeline.qml",
            "CompactTextStyleBar.qml",
            "ManualSubtitleStyleControls.qml",
            "ManualWatermarkStyleControls.qml",
            "TextColorStrip.qml",
            "ColorPickerPopup.qml",
            "TrackHeader.qml",
            "EditorDockGroup.qml",
            "ManualToolNavigator.qml",
            "ManualSelectionPanel.qml",
            "ManualSourceToolPanel.qml",
            "ManualTranslationToolPanel.qml",
            "ManualSubtitleToolPanel.qml",
            "ManualImageToolPanel.qml",
            "ManualVoiceToolPanel.qml",
            "ManualAudioToolPanel.qml",
            "ManualExportToolPanel.qml",
        ):
            component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / name)))
            assert component.isReady(), f"{name}: " + "\n".join(
                error.toString() for error in component.errors()
            )
    finally:
        engine.deleteLater()
        app.processEvents()


def test_export_panel_never_claims_ready_before_preflight_and_subtitle_style_is_compact():
    inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
    export = (QML_DIR / "ManualExportToolPanel.qml").read_text(encoding="utf-8")
    subtitle = (QML_DIR / "ManualSubtitleToolPanel.qml").read_text(encoding="utf-8")
    assert '"canExport": false' in inspector
    assert "Component.onCompleted:" in inspector
    assert "Boolean(root.inspector.exportPreflight.canExport)" in export
    assert "Cần khoảng %1" not in export
    assert "Kiểm tra trước khi xuất" not in export
    assert "InspectorSection {" not in subtitle


def test_editor_hides_single_tool_header_and_removed_subtitle_actions():
    dock = (QML_DIR / "EditorDockGroup.qml").read_text(encoding="utf-8")
    workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
    dialog = (QML_DIR / "ManualSubtitleEditorDialog.qml").read_text(encoding="utf-8")
    editor = (QML_DIR / "SubtitleTextEditor.qml").read_text(encoding="utf-8")
    image = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
    slider = (QML_DIR / "AppSlider.qml").read_text(encoding="utf-8")
    assert "visible: root.panelIds.length > 1" in dock
    assert 'return side === "left" ? ["tools"] : ["tasks"];' in workspace
    assert 'activatePanel("tasks", "right");' in workspace
    assert "Tách tại vạch phát" not in dialog
    assert "Gộp với đoạn sau" not in dialog
    assert "Đã lưu" not in editor
    assert '"translation", "image", "export"' in image
    assert "implicitWidth: 18" in slider
    assert "implicitWidth: root.pressed" not in slider


def test_manual_layout_has_one_toolbar_and_on_demand_comparison():
    workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
    preview = (QML_DIR / "ManualComparePreview.qml").read_text(encoding="utf-8")
    inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
    timeline = (QML_DIR / "SubtitleTimeline.qml").read_text(encoding="utf-8")

    assert "ManualEditorToolbar {" in workspace
    assert "ManualWorkflowBar {" not in workspace
    assert "EditorCommandBar {" not in workspace
    assert "comparing: root.comparing" in workspace
    assert "visible: root.comparing" in preview
    assert "ManualToolNavigator {" in workspace
    assert "tools: root.toolModel.slice(0, 6)" in workspace
    assert "EditorDockGroup {" in workspace
    assert 'onExportRequested: {\n                root.selectedStageIndex = 6;' in workspace
    assert 'root.activatePanel("tasks", "right");' in workspace
    assert '"voice": 4, "source-audio": 5, "music": 5' in workspace
    assert "ManualAssetPanel {" not in workspace
    assert "EditorFloatingDock {" not in workspace
    assert "onPanelMoved:" not in (QML_DIR / "EditorDockGroup.qml").read_text(encoding="utf-8")
    assert 'objectName: "manualToolSelector"' not in inspector
    assert "resetWorkspaceLayout()" in workspace
    assert "CornerScaleHandle {" not in (QML_DIR / "EditorOverlayLayer.qml").read_text(encoding="utf-8")
    assert "RotationHandle {" not in (QML_DIR / "EditorOverlayLayer.qml").read_text(encoding="utf-8")
    assert "model: root.visibleTicks" in timeline
    assert "model: root.visibleSegments" in timeline
    assert "function toggleTrackCollapsed(trackId)" in timeline
    assert "SplitView.preferredHeight: root.height < 780 ? 210" in workspace


def test_voice_and_subtitles_share_one_timeline_lane_without_merging_data():
    timeline = (QML_DIR / "SubtitleTimeline.qml").read_text(encoding="utf-8")
    header = (QML_DIR / "TrackHeader.qml").read_text(encoding="utf-8")

    assert 'y: combinedVoice ? 104 : root.trackY(index)' in timeline
    assert 'if (String(track.track_id || "") === "voice")' in timeline
    assert 'title: qsTr("Phụ đề · Giọng đọc")' in timeline
    assert 'onSecondaryMuteToggled: root.trackStateRequested("voice", "muted", !secondaryMuted)' in timeline
    assert 'root.clipSelected(editorClip.clipId,' in timeline
    assert 'text: qsTr("Tắt tiếng giọng đọc")' in header


def test_text_style_controls_are_inline_in_both_editor_tools():
    inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
    image = (QML_DIR / "ManualImageToolPanel.qml").read_text(encoding="utf-8")
    subtitle = (QML_DIR / "ManualSubtitleToolPanel.qml").read_text(encoding="utf-8")
    selection = (QML_DIR / "ManualSelectionPanel.qml").read_text(encoding="utf-8")
    subtitle_controls = (QML_DIR / "ManualSubtitleStyleControls.qml").read_text(encoding="utf-8")
    watermark_controls = (QML_DIR / "ManualWatermarkStyleControls.qml").read_text(encoding="utf-8")
    bar = (QML_DIR / "CompactTextStyleBar.qml").read_text(encoding="utf-8")
    assert "TextStyleLibraryDialog" not in inspector
    assert "ManualWatermarkStyleControls {" in image
    assert "ManualSubtitleStyleControls {" in subtitle
    assert "ManualWatermarkStyleControls {" in selection
    assert "ManualSubtitleStyleControls {" not in selection
    assert '"outline_width": Math.round(AppController.watermarkOutlinePercent / 50)' in watermark_controls
    assert 'AppController.applyTextStyle([], patch, "project")' in subtitle_controls
    assert "Style chung" not in subtitle_controls
    assert "Đoạn này" not in subtitle_controls
    assert "compactFontSelector" not in bar
    assert 'root.changeRequested({ "font_weight": checked ? 700 : 400 })' in bar
    assert 'root.changeRequested({ "outline_width": value })' in bar


def test_manual_layout_preferences_are_bounded_and_survive_partial_updates(tmp_path, monkeypatch):
    from haizflow.services import desktop_settings

    monkeypatch.setattr(desktop_settings, "SETTINGS_PATH", tmp_path / "desktop-settings.json")
    desktop_settings.save_settings({
        "manual_editor_inspector_width": 9999,
        "manual_editor_timeline_height": 50,
        "manual_editor_compare": True,
    })
    desktop_settings.save_settings({"language": "vi"})
    saved = desktop_settings.load_settings()
    assert saved["manual_editor_inspector_width"] == 520
    assert saved["manual_editor_timeline_height"] == 200
    assert saved["manual_editor_compare"] is True


def test_manual_workspace_dock_preferences_are_normalized(tmp_path, monkeypatch):
    from haizflow.services import desktop_settings

    monkeypatch.setattr(desktop_settings, "SETTINGS_PATH", tmp_path / "desktop-settings.json")
    saved = desktop_settings.save_settings({"manual_editor_workspace": {
        "placements": {"tools": "float", "assets": "invalid", "tasks": "left"},
        "leftActive": "assets", "rightActive": "tasks",
        "leftWidth": 9999, "monitor": "unknown",
    }})["manual_editor_workspace"]
    assert saved["placements"] == {
        "tools": "left", "properties": "right", "tasks": "right",
    }
    assert saved["leftActive"] == "tools"
    assert saved["leftWidth"] == 480
    assert saved["monitor"] == "result"
    assert desktop_settings.load_settings()["manual_editor_workspace"] == saved
    desktop_settings.SETTINGS_PATH.write_text(
        '{"manual_editor_workspace": {"placements": "broken", "monitor": "invalid"}}',
        encoding="utf-8",
    )
    recovered = desktop_settings.load_settings()["manual_editor_workspace"]
    assert recovered["placements"]["tools"] == "left"
    assert recovered["placements"]["tasks"] == "right"
    assert recovered["monitor"] == "result"
