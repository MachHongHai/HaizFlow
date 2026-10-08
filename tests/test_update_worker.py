"""Core-delivered updater fixes must not depend on the original bootstrap."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from haizflow.update.updater import worker_main


def test_worker_passes_exact_root_and_token_without_ui(tmp_path):
    token = "a" * 64
    with patch("haizflow.update.updater.run_request") as run:
        assert worker_main(["--install-root", str(tmp_path), "--request-token", token]) == 0
        run.assert_called_once_with(tmp_path, token)


def test_worker_failure_returns_nonzero_without_a_modal_dialog(tmp_path, capsys):
    with patch("haizflow.update.updater.run_request", side_effect=PermissionError("Locked")):
        assert worker_main(["--install-root", str(tmp_path), "--request-token", "b" * 64]) == 1
    assert "Locked" in capsys.readouterr().err


def test_core_prefers_current_version_updater_over_old_bootstrap(tmp_path):
    from haizflow.desktop.app_update_controller import AppUpdateController
    from haizflow.update.state import Layout, provision
    from PySide6.QtCore import QObject, Signal

    class Host(QObject):
        appUpdateAvailable = Signal()

    provision(tmp_path)
    (tmp_path / "HaizFlow.exe").touch()
    (tmp_path / "updater").mkdir()
    (tmp_path / "updater/HaizFlowUpdater.exe").touch()
    core = tmp_path / "versions/0.1.6/HaizFlowCore.exe"
    core.parent.mkdir(parents=True)
    core.touch()
    controller = AppUpdateController(Host())
    controller._delta_layout = Layout(tmp_path)
    controller._latest_version = "0.1.7"
    controller._state = "available"
    with (patch.object(sys, "frozen", True, create=True),
          patch.object(sys, "platform", "win32"), patch.object(sys, "executable", str(core)),
          patch("haizflow.desktop.app_update_controller.__version__", "0.1.6"),
          patch("haizflow.desktop.app_update_controller.subprocess.Popen") as launch):
        assert controller.install()
        assert launch.call_args.args[0][:4] == [str(core), "--app-update-worker", "--install-root", str(tmp_path)]
        assert launch.call_args.kwargs["shell"] is False


def test_worker_entrypoint_precedes_desktop_and_splash():
    entry = (Path(__file__).resolve().parents[1] / "haizflow_desktop.py").read_text(encoding="utf-8")
    assert entry.index('if "--app-update-worker" in sys.argv:') < entry.index('if __name__ == "__main__":')


@pytest.mark.parametrize("base", [f"0.1.{patch}" for patch in range(6)])
def test_every_released_base_can_choose_full_without_an_intermediate_update(tmp_path, base):
    from unittest.mock import Mock
    from haizflow.update.updater import prepare_latest

    layout = Mock()
    layout.active.return_value = {"active": base}
    layout.downloads = tmp_path
    client = Mock()
    name = "HaizFlow-Core-0.1.6-windows-x64-full.manifest.json"
    client.latest.return_value = {"tag_name": "v0.1.6", "assets": [{"name": name}]}
    manifest = Mock()
    manifest.data = {"package_name": name.replace(".manifest.json", ".zip"),
                     "package_sha256": "a" * 64, "package_size": 100}
    client.fetch_manifest.return_value = manifest
    client.asset.return_value = {"sha256": "a" * 64, "size": 100}
    client.download.return_value = tmp_path / "full.zip"
    prepare_latest(layout, "0.1.6", client=client)
    client.fetch_manifest.assert_called_once_with(client.latest.return_value, name, tmp_path)
    layout.prepare.assert_called_once()
