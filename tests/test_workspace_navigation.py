"""Exercise navigation with the real controller, without loading AI models."""
import json
import subprocess
import sys
from pathlib import Path


def test_real_workspace_navigation():
    try:
        result = subprocess.run([sys.executable, "-u", "-X", "utf8", str(Path(__file__).resolve())],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"Navigation probe timed out: {exc.stdout!r}\n{exc.stderr!r}") from exc
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)


def exercise():
    import faulthandler
    import statistics
    import tempfile
    import time

    from PySide6.QtCore import QByteArray, QUrl
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    from haizflow.desktop.qml_controller import HaizFlowController
    from haizflow.services import desktop_settings, project_store

    faulthandler.dump_traceback_later(20, repeat=True)
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
    desktop_settings.save_settings({"keep_models_warm": False})
    HaizFlowController._start_startup_maintenance = lambda self: None
    host = HaizFlowController()
    qml = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
    main = (qml / "Main.qml").read_text("utf-8")
    handlers = main.split("onSectionRequested:", 1)[1].split("ColumnLayout", 1)[0]
    refresh_on_navigation = "AppController.refreshVideos()" in handlers
    with tempfile.TemporaryDirectory(prefix="navigation-projects-") as directory:
        created_keys = []
        # Catalog size makes redundant synchronous refreshes measurable.
        for index in range(12):
            created_keys.append(project_store.create_project(f"Navigation {index}", directory, "manual")["key"])
        selected = project_store.create_project("Selected manual project", directory, "manual")
        created_keys.append(selected["key"])
        host.refreshVideos()
        deadline = time.monotonic() + 5
        while selected["key"] not in host._project_summaries_by_key and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert selected["key"] in host._project_summaries_by_key, (
            host.projectCatalogState, host._project_workspace._refresh_running,
            host._project_workspace._refresh_again)
        assert host._select_project_summary(host._project_summaries_by_key[selected["key"]])
        print("NAVIGATION_CATALOG_READY", flush=True)
        engine = QQmlEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
        engine.rootContext().setContextProperty("refreshOnNavigation", refresh_on_navigation)
        component = QQmlComponent(engine)
        component.setData(QByteArray(b'''
            import QtQuick
            import QtQuick.Controls.Basic
            import "."
            ApplicationWindow {
                id: window
                width: 1440; height: 900; visible: true
                color: Theme.window
                property string route: "settings"
                property string requestedRoute: "settings"
                onRequestedRouteChanged: {
                    if (refreshOnNavigation) AppController.refreshVideos();
                    route = requestedRoute;
                }
                RouteHost { anchors.fill: parent; currentRoute: window.route }
            }
        '''), QUrl.fromLocalFile(str(qml / "NavigationTest.qml")))
        assert component.isReady(), [e.toString() for e in component.errors()]
        window = component.create()
        assert isinstance(window, QQuickWindow), warnings
        print("NAVIGATION_UI_READY", flush=True)
        QTest.qWait(150)
        timings = {}
        warm_timings = {}
        refresh_timings = []
        for _ in range(3):
            start = time.perf_counter()
            host.refreshVideos()
            refresh_timings.append((time.perf_counter() - start) * 1000)
        routes = ("api-keys", "mcp", "packages", "settings",
                  "api-keys", "mcp", "packages", "settings",
                  "manual-projects", "projects", "home", "settings")
        for _ in range(3):
            for index, route in enumerate(routes):
                start = time.perf_counter()
                window.setProperty("requestedRoute", route)
                app.processEvents()
                timings.setdefault(route, []).append(round((time.perf_counter() - start) * 1000, 2))
                if 5 <= index < 10:
                    warm_timings.setdefault(route, []).append(timings[route][-1])
                QTest.qWait(35)
        # Background bindings must not start a model or alter project ownership.
        assert host.projectKey == selected["key"]
        assert not warnings, warnings
        print(json.dumps({"refresh_on_navigation": refresh_on_navigation,
                          "catalog_refresh_ms": round(statistics.median(refresh_timings), 2),
                          "navigation_median_ms": {key: round(statistics.median(values), 2)
                                                   for key, values in timings.items()},
                          "warm_settings_ms": {key: round(statistics.median(values), 2)
                                               for key, values in warm_timings.items()}}, ensure_ascii=False))
        screenshots = Path(__file__).parents[1] / "build"
        screenshots.mkdir(exist_ok=True)
        for route in ("settings", "api-keys", "packages", "mcp"):
            window.setProperty("requestedRoute", route)
            QTest.qWait(180)
            assert window.grabWindow().save(str(screenshots / f"navigation-{route}.png"))
        assert not warnings, warnings
        window.close()
        window.deleteLater()
        QTest.qWait(60)
        host.shutdown()
        for key in created_keys:
            project_store.delete_project_by_key(key)
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    exercise()
