"""Queue proximity and actual wheel scrolling with a virtualised long list."""

import os
import subprocess
import sys
import time
from pathlib import Path
import unittest

from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from haizflow.desktop.models import SocialPublishListModel


QML_DIR = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


class SocialPublishLayoutUiTests(unittest.TestCase):
    # The main test process registers the real AppController singleton in
    # other QML engines. Run this mock-controller fixture in its own Qt process.
    __test__ = False
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf", "segmdl2.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))

    def create_page(self, count, height=720):
        engine = QQmlEngine()
        state = QQmlPropertyMap()
        model = SocialPublishListModel()
        model.set_items([{
            "id": f"post-{index}", "file_name": f"Video {index + 1}.mp4",
            "file_path": "", "caption": "Nội dung bài đăng", "hashtags": "#video",
            "post_text": "Nội dung bài đăng #video", "status": "published",
            "error": "", "thumbnail_source": "", "upload_progress": 100,
            "zernio_post_id": f"remote-{index}", "target_platform": "tiktok",
            "platform_post_url": "https://example.com/post", "platform_post_url_verified": True,
        } for index in range(count)])
        for name, value in {
            "projectName": "Hàng đợi", "tiktokPublishBusy": False,
            "tiktokWaitingCount": 0, "tiktokPublishCount": count, "tiktokPublishModel": model,
            "tiktokDefaultCaption": "Nội dung mặc định", "tiktokDefaultHashtags": "#video",
            "zernioApiKeyConfigured": True, "zernioApiKeyVerified": True,
            "zernioAccountReady": True, "zernioAccountSyncing": False,
            "zernioOauthSyncPending": False, "zernioConnectedAccountCount": 1,
            "zernioCanPostMore": True, "zernioSelectedAccountIndex": 0,
            "zernioSelectedPlatform": "tiktok", "zernioSelectedAccountName": "Tài khoản",
        }.items():
            state.insert(name, value)
        engine.rootContext().setContextProperty("TestController", state)
        engine.rootContext().setContextProperty("AppController", state)
        component = QQmlComponent(engine)
        component.setData((QML_DIR / "SocialPublishPage.qml").read_text(encoding="utf-8")
                          .replace("AppController", "TestController").encode(),
                          QUrl.fromLocalFile(str(QML_DIR / "SocialPublishPage.qml")))
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        page = component.create()
        self.assertIsNotNone(page)
        window = QQuickWindow()
        window.setColor("#101010")
        window.resize(1280, height)
        page.setParent(window)
        page.setParentItem(window.contentItem())
        page.setSize(window.size())
        window.show()
        QTest.qWait(80)
        self.addCleanup(self.dispose, window, page, engine)
        # Keep the context objects alive until after their QML bindings die.
        self.context_objects = (state, model)
        return window, page

    def dispose(self, window, page, engine):
        window.close()
        page.deleteLater()
        window.deleteLater()
        engine.deleteLater()
        self.app.processEvents()

    def test_short_queue_is_close_to_heading_without_stretching_rows(self):
        window, page = self.create_page(6, height=900)
        header = page.findChild(QQuickItem, "socialQueueHeader")
        surface = page.findChild(QQuickItem, "socialQueueSurface")
        queue = page.findChild(QQuickItem, "socialQueueList")
        header_bottom = header.mapToScene(QPointF(0, header.height())).y()
        surface_top = surface.mapToScene(QPointF()).y()
        self.assertGreaterEqual(surface_top - header_bottom, 0)
        self.assertLessEqual(surface_top - header_bottom, 20)
        self.assertEqual(queue.property("count"), 6)
        self.assertAlmostEqual(queue.property("contentHeight"), 6 * 64, delta=1)
        self.assertLessEqual(surface.height(), 6 * 64 + 1)
        if os.environ.get("HAIZFLOW_UI_CAPTURE"):
            target = QML_DIR.parents[3] / "build" / "social-queue-short.png"
            self.assertTrue(window.grabWindow().save(str(target)))

    def test_long_queue_scrolls_down_up_and_after_resize(self):
        window, page = self.create_page(80)
        queue = page.findChild(QQuickItem, "socialQueueList")
        self.assertGreater(queue.property("contentHeight"), queue.height())
        self.assertGreater(queue.height(), 100)

        def wheel(delta):
            position = queue.mapToScene(QPointF(queue.width() / 2, queue.height() / 2))
            event = QWheelEvent(position, QPointF(window.mapToGlobal(position.toPoint())),
                                QPoint(), QPoint(0, delta), Qt.NoButton, Qt.NoModifier,
                                Qt.NoScrollPhase, False)
            event.setTimestamp(int(time.monotonic() * 1000))
            self.app.sendEvent(window, event)
            QTest.qWait(30)
            for _ in range(60):
                if not queue.property("moving"):
                    break
                QTest.qWait(30)
            self.assertFalse(queue.property("moving"))

        wheel(-1200)
        after_down = queue.property("contentY")
        self.assertGreater(after_down, 0)
        wheel(1200)
        self.assertLess(queue.property("contentY"), after_down)
        window.resize(1280, 540)
        page.setSize(window.size())
        QTest.qWait(30)
        self.assertGreater(queue.height(), 80)
        self.assertGreater(queue.property("contentHeight"), queue.height())
        wheel(-1200)
        self.assertGreater(queue.property("contentY"), 0)


def test_social_publish_queue_layout_in_isolated_qt_process():
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--run-qt-tests"],
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
