"""Retired studios must not load, while normal project voices remain available."""
from pathlib import Path

from haizflow.desktop import presenters
from haizflow.services.project_store import PROJECT_TYPES

QML = Path(__file__).parents[1] / "src/haizflow/desktop/qml"


def test_navigation_and_settings_have_no_studio_or_library():
    assert "voice" not in PROJECT_TYPES
    for name in ("Main", "RouteHost", "SettingsWorkspace", "NavigationRail", "AppMenuBar",
                 "ProjectSetupDialog", "ProjectsHubPage", "VoicePicker", "haizflow.qmltypes", "qmldir"):
        path = QML / (name if name in {"haizflow.qmltypes", "qmldir"} else name + ".qml")
        source = path.read_text("utf-8")
        for retired in ("voice-design", "voice-library", "voice-workspace", "voiceDesigner",
                        "vieneuVoiceStudio", "Kho giọng", "Thiết kế giọng"):
            assert retired not in source, (name, retired)


def test_existing_voice_catalogs_keep_clone_and_previews():
    for provider in ("omnivoice", "vieneu", "vieneu-gpu"):
        rows = presenters.voice_options_for_language("vi", "vi", provider)
        backend = "vieneu" if provider.startswith("vieneu") else "omnivoice"
        assert any(row["voice"] == backend + ":clone" for row in rows)
        assert any(row["voice"].startswith(backend + ":") and row["voice"] != backend + ":clone" for row in rows)
        assert not any(":saved_" in row["voice"] for row in rows)
