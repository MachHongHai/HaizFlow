"""Exercise real pointer events, including overlay dismissal on release."""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

QML = Path(__file__).resolve().parents[1] / "src/hflow/desktop/qml"


class DropdownToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def check_toggle(self, declaration, trigger_name, popup_name, *, bottom=False, helpers=""):
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData((
            'import QtQuick\nimport QtQuick.Controls.Basic\nimport QtQuick.Layouts\n'
            f'import "{QML.as_uri()}"\n'
            'ApplicationWindow { width: 780; height: 620; visible: true; ' + helpers
            + 'Item { x: 60; y: ' + ('550' if bottom else '40') + '; width: 620; height: 42; '
            + declaration + ' }}'
        ).encode(), QUrl())
        self.assertTrue(component.isReady(), "\n".join(e.toString() for e in component.errors()))
        window = component.create()
        self.assertIsNotNone(window)
        try:
            QTest.qWait(60)
            trigger = window.findChild(QQuickItem, trigger_name)
            popup = window.findChild(QObject, popup_name)
            self.assertIsNotNone(trigger)
            self.assertIsNotNone(popup)
            center = trigger.mapToScene(QPointF(trigger.width() / 2, trigger.height() / 2)).toPoint()
            # Include clicks during enter transitions, not only fully opened.
            for delay in (0, 180, 0, 180):
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                QTest.qWait(delay)
                self.assertTrue(popup.property("visible"), "first click must open")
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                QTest.qWait(200)
                self.assertFalse(popup.property("visible"), "second click must close, not reopen")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
            QTest.qWait(180)
            QTest.keyClick(window, Qt.Key_Escape)
            QTest.qWait(200)
            self.assertFalse(popup.property("visible"))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
            QTest.qWait(180)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(760, 600))
            QTest.qWait(200)
            self.assertFalse(popup.property("visible"), "outside click must still dismiss")
        finally:
            window.close()
            window.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_voice_picker_above_and_below_trigger(self):
        declaration = '''VoicePicker { objectName: "trigger"; width: 280;
            model: [{voice: "edge:male", label: "Nam", category: "natural"}];
            currentValue: "edge:male" }'''
        for bottom in (False, True):
            with self.subTest(bottom=bottom):
                self.check_toggle(declaration, "trigger", "voicePickerPopup", bottom=bottom)

    def test_language_search_picker(self):
        self.check_toggle('''SearchableLanguageCombo { width: 280; selectedCode: "vi";
            options: [{code: "vi", label: "Tiếng Việt", search: "vi tiếng việt"},
                      {code: "en", label: "English", search: "english"}] }''',
            "languageDisplayButton", "languageSearchPopup")

    def test_basic_combo_and_ratio_combo(self):
        for kind, properties in (("AppComboBox", 'model: ["Một", "Hai"];'), ("OutputFrameCombo", "")):
            with self.subTest(kind=kind):
                self.check_toggle(kind + ' { objectName: "trigger"; width: 220; '
                    + properties + ' Component.onCompleted: popup.objectName = "testedPopup" }',
                    "trigger", "testedPopup")

    def test_help_popover(self):
        self.check_toggle('HelpPopover { objectName: "trigger"; helpText: "Trợ giúp" }',
                          "trigger", "helpPopoverPopup")

    def test_layer_and_track_menus(self):
        self.check_toggle('''OcrLayerList { width: 300; layers: [{clip_id: "a", track_id: "ocr-a",
            primary: true, visible: true}]; selectedId: "a" }''', "ocrLayerMenuButton", "ocrLayerMenu")
        self.check_toggle('TrackHeader { width: 240; height: 42; title: "Phụ đề"; kind: "subtitle" }',
                          "trackMenuButton", "trackMenu")

    def test_social_and_resource_menus(self):
        # Keep the production handlers/layout; substitute only controller
        # data so UI tests cannot start an upload or mutate installed packs.
        fake = '''QtObject { id: testController;
            property bool tiktokPublishBusy: false; property bool zernioAccountSyncing: false;
            property bool zernioApiKeyVerified: true; property bool zernioAccountReady: true;
            property bool zernioCredentialBusy: false; property bool zernioApiKeyConfigured: true;
            property int zernioSelectedAccountIndex: 0; property string zernioSelectedPlatform: "tiktok";
            property string zernioSelectedAccountName: "Test"; property bool zernioOauthSyncPending: false;
            property int zernioConnectedAccountCount: 1; property bool zernioCanPostMore: true;
        }'''
        cases = [
            ("SocialPublishRow.qml", '''index: 0; fileName: "Test"; caption: ""; hashtags: "";
                postText: ""; publishStatus: "draft"; publishError: ""; thumbnailSource: "";
                uploadProgress: 0; zernioPostId: ""; platformPostUrl: "";
                platformPostUrlVerified: false; targetPlatform: "tiktok";''',
                "socialRowMenuButton", "socialRowMenu"),
            ("SocialConnectionBar.qml", "", "socialSetupMenuButton", "socialSetupMenu"),
            ("ResourcePackRow.qml", '''packId: "test"; label: "Test"; version: "1"; status: "installed";
                progress: 0; detail: ""; summary: ""; downloadSizeText: ""; installedSizeText: "";
                canInstall: true; canRemove: true; blockedReason: ""; hardwareCompatible: true;
                hardwareWarning: ""; groupFirst: false; groupTitle: "";''',
                "resourcePackMenuButton", "resourcePackMenu"),
        ]
        for filename, assignments, button, popup in cases:
            with self.subTest(component=filename):
                source = (QML / filename).read_text(encoding="utf-8")
                body = "\n".join(line for line in source.splitlines()
                                 if not line.startswith(("pragma ", "import ")))
                body = body.replace("AppController.", "testController.")
                body = body.replace("id: root", "id: root\n" + assignments, 1)
                self.check_toggle('Loader { width: 620; sourceComponent: testedComponent }', button, popup,
                                  helpers=fake + 'Component { id: testedComponent; ' + body + '}')


if __name__ == "__main__":
    unittest.main()
