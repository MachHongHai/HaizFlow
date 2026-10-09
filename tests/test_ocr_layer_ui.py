"""QML integration tests of staged OCR controls and experimental menus."""
from pathlib import Path

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, Property, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


QML_DIR = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


class Backend(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.removes = True
        self.mode = "patch"
        self.calls = []

    @Property(bool, notify=changed)
    def removeOriginalSubtitles(self):
        return self.removes

    @Property(str, notify=changed)
    def originalSubtitleRemovalMode(self):
        return self.mode

    @Property("QVariantMap", constant=True)
    def reviewPreviewMedia(self):
        return {}

    @Slot("QVariantMap", result=bool)
    def setOriginalSubtitleRegion(self, region):
        self.calls.append(("region", dict(region)))
        self.changed.emit()
        return True

    @Slot(str, "QVariantMap", result=bool)
    def setManualSubtitleTreatment(self, mode, region):
        self.calls.append(("region", dict(region)))
        self.calls.append(("mode", mode))
        self.removes = mode != "keep"
        if mode != "keep":
            self.mode = mode
        self.changed.emit()
        return True

    @Slot(result=str)
    def addOcrLayer(self):
        self.calls.append(("add", "extra"))
        return "extra"

    @Slot(str, "QVariantMap", str, result=bool)
    def updateOcrLayer(self, clip_id, region, mode):
        self.calls.append(("layer", clip_id, dict(region), mode))
        return True


def test_keep_selection_is_applied_even_when_region_commit_refreshes_bindings():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("ocrBackend", backend)
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 360; height: 340; visible: true; color: Theme.surface
    QtObject {{
        id: testInspector
        objectName: "testInspector"
        property var selectedOcrLayer: ({{clip_id: "ocr-source-region", primary: true,
            region: {{x_percent: 10, y_percent: 40, width_percent: 60, height_percent: 15}}}})
        property var ocrLayers: [selectedOcrLayer]
        property var ocrModeDrafts: ({{}})
        property var ocrRegionDraft: ({{x_percent: 15, y_percent: 55, width_percent: 60, height_percent: 15}})
        property bool editable: true
        property bool taskQueued: false
        signal ocrModeDraftRequested(string clipId, string mode)
        signal ocrLayerSelected(string clipId)
        signal ocrRegionDiscardRequested()
        onOcrModeDraftRequested: function(clipId, mode) {{
            ocrModeDrafts = Object.assign({{}}, ocrModeDrafts, {{[clipId]: mode}});
        }}
        onOcrLayerSelected: function(id) {{
            selectedOcrLayer = {{clip_id: id, name: "Lớp che 1", primary: false, mode: "blur", region: ocrRegionDraft}};
            ocrLayers = [selectedOcrLayer];
        }}
    }}
    ManualImageToolPanel {{
        id: panel; objectName: "panel"
        x: 16; y: 16; width: parent.width - 32
        inspector: testInspector
        controller: ocrBackend
    }}
    Button {{
        objectName: "applyButton"
        anchors.right: parent.right; anchors.top: panel.bottom; anchors.topMargin: 16
        text: "Apply"; onClicked: panel.applyTreatment()
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert window is not None
    try:
        window.requestActivate()
        QTest.qWait(50)
        selector = window.findChild(QQuickItem, "ocrTreatmentSelector")
        assert selector is not None
        assert window.findChild(QObject, "addOcrLayerButton") is not None
        assert window.findChild(QObject, "ocrLayerSelector") is not None
        selector.setProperty("currentIndex", 0)
        assert QMetaObject.invokeMethod(selector, "activated", Qt.DirectConnection, Q_ARG(int, 0))
        QTest.qWait(30)
        panel = window.findChild(QObject, "panel")
        assert panel.property("draftTreatment") == "keep", {
            "index": selector.property("currentIndex"), "value": selector.property("currentValue"),
            "enabled": selector.property("enabled"), "width": selector.property("width"),
            "selected": panel.property("clipId"),
        }
        # Exercise the same panel command used by the inspector's Apply button;
        # offscreen popup animations can swallow a synthetic second click.
        assert QMetaObject.invokeMethod(panel, "applyTreatment", Qt.DirectConnection)
        QTest.qWait(30)
        assert backend.calls[-1] == ("mode", "keep")
        assert not backend.removes
        # Adding a layer is only a draft. It must not start OCR or apply a mask.
        before = len(backend.calls)
        add = window.findChild(QObject, "addOcrLayerButton")
        assert QMetaObject.invokeMethod(add, "clicked", Qt.DirectConnection)
        assert backend.calls[before:] == [("add", "extra")]
        assert panel.property("clipId") == "extra"
        assert panel.property("draftTreatment") == "blur"
        assert QMetaObject.invokeMethod(selector, "activated", Qt.DirectConnection, Q_ARG(int, 1))
        assert panel.property("draftTreatment") == "patch"
        assert QMetaObject.invokeMethod(panel, "applyTreatment", Qt.DirectConnection)
        assert backend.calls[-1][0:2] == ("layer", "extra")
        assert backend.calls[-1][-1] == "patch"
        assert not backend.removes  # Independent of the primary keep setting.
        import os
        if directory := os.getenv("HAIZFLOW_UI_CAPTURE_DIR"):
            QTest.qWait(100)
            Path(directory).mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(Path(directory) / "ocr-layer-panel.png"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_layer_menu_opens_with_readable_items():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 480; height: 260; visible: true
    OcrLayerList {{
        x: 16; y: 16; width: 420
        selectedId: "extra"
        layers: [{{clip_id: "extra", track_id: "extra", name: "Lớp che 1",
            primary: false, visible: true}}]
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert window is not None
    try:
        QTest.qWait(50)
        button = window.findChild(QQuickItem, "ocrLayerMenuButton")
        point = button.mapToScene(button.boundingRect().center())
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
        QTest.qWait(50)
        menu = window.findChild(QObject, "ocrLayerMenu")
        assert menu.property("opened")
        assert menu.property("width") >= 180
        labels = [obj.property("text") for obj in window.findChildren(QObject, "menuItemLabel")]
        assert "Ẩn lớp" in labels and "Xóa lớp" in labels
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
