import sys
from pathlib import Path

import pytest

from haizflow.startup_splash import StartupSplash, settings_language


def test_language_defaults_and_saved_preference(tmp_path):
    settings = tmp_path / "settings.json"
    assert settings_language(settings) == "vi"
    settings.write_text('{"language":"en"}', encoding="utf-8")
    assert settings_language(settings) == "en"
    settings.write_text('[]', encoding="utf-8")
    assert settings_language(settings) == "vi"
    settings.write_text('invalid', encoding="utf-8")
    assert settings_language(settings) == "vi"


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows startup UI")
@pytest.mark.parametrize("language", ["vi", "en"])
def test_native_splash_draws_and_closes_without_qt(language):
    splash = StartupSplash(language=language, icon_path=Path(__file__).parents[1]
                           / "src/haizflow/desktop/assets/branding/haizflow.ico").show()
    try:
        assert splash.error is None
        assert splash._hwnd
        splash.opening_interface()
        assert splash.status == ("Opening interface…" if language == "en" else "Đang mở giao diện…")
    finally:
        splash.close()
    assert not splash._thread.is_alive()
    assert splash.error is None
    splash.close()


def test_workers_never_show_startup_ui():
    entry = (Path(__file__).parents[1] / "haizflow_desktop.py").read_text(encoding="utf-8")
    assert entry.index('if "--release-smoke"') < entry.index("from haizflow.startup_splash")
    assert entry.index('if "--omnivoice-server"') < entry.index("from haizflow.startup_splash")
    assert 'os.getenv("HAIZFLOW_STARTUP_SPLASH") != "1"' in entry
