from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from haizflow.update.filesystem import (UpdateError, atomic_json, child, file_lock,
                                       relative_path, remove_owned, sha256)
from haizflow.update.launcher import CoreStillRunningError, launch
from haizflow.update.manifest import Manifest, inventory
from haizflow.update.network import API, GitHubClient, RedirectPolicy, allowed_url
from haizflow.update.packages import generate, reconstruct
from haizflow.update.state import Layout, provision
from haizflow.update.updater import prepare_latest
from haizflow.update.bootstrap import check_install, initialize, uninstall_cores


class Interrupted(BaseException):
    pass


FAKE_CORE = """
import json, os, pathlib, time
root = pathlib.Path(os.environ['HAIZFLOW_BOOTSTRAP_ROOT'])
attempt = os.environ['HAIZFLOW_HEALTH_ATTEMPT']
request = json.loads((root/'update-state'/'ipc'/(attempt+'.request.json')).read_text())
ack = dict(token=request['token'], version=request['version'], pid=os.getpid(), ready=True)
(root/'update-state'/'ipc'/(attempt+'.ack.json')).write_text(json.dumps(ack))
time.sleep(0.25)
"""


class DeltaUpdateTests(unittest.TestCase):
    def test_preparation_reports_real_ordered_phase_progress(self):
        events = []
        self.layout.prepare(self.output / self.delta.data["package_name"], self.delta,
                            progress=lambda state, value: events.append((state, value)))
        self.assertEqual(events[0], ("verifying", 50))
        self.assertEqual(events[-1], ("ready", 90))
        self.assertEqual([value for _, value in events], sorted(value for _, value in events))
        preparing = [value for state, value in events if state == "preparing"]
        self.assertGreater(len(set(preparing)), 3)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="haizflow-delta-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "core-0.1.0"
        self.target = self.root / "core-0.2.0"
        self.base.mkdir()
        self.target.mkdir()
        for directory, payload in ((self.base, b"old-core"), (self.target, b"new-core")):
            (directory / "HaizFlowCore.exe").write_bytes(payload)
            (directory / "_internal").mkdir()
            (directory / "_internal/same.dll").write_bytes(b"same-library" * 512)
        (self.base / "removed.dat").write_bytes(b"remove")
        (self.target / "added.dat").write_bytes(b"added")
        self.output = self.root / "packages"
        self.full1 = generate(None, self.base, self.output, base_version=None, target_version="0.1.0")
        self.full2 = generate(None, self.target, self.output, base_version=None, target_version="0.2.0")
        self.delta = generate(self.base, self.target, self.output, base_version="0.1.0", target_version="0.2.0")
        self.install = self.root / "installation"
        provision(self.install)
        self.layout = Layout(self.install)
        reconstruct(self.output / self.full1.data["package_name"], self.full1, self.layout.core("0.1.0"), None)
        self.layout.seed("0.1.0")
        (self.layout.runtime / "models").mkdir(parents=True)
        (self.layout.runtime / "models/model.bin").write_bytes(b"USER MODEL")
        (self.layout.runtime / "settings.json").write_bytes(b"USER SETTINGS")
        self.external = self.root / "external-project"
        self.external.mkdir()
        (self.external / "project.json").write_bytes(b"USER PROJECT")
        self.before = self.user_data()

    def user_data(self):
        return [(str(p.relative_to(self.root)), sha256(p)) for directory in (self.layout.runtime, self.external)
                for p in sorted(directory.rglob("*")) if p.is_file()]

    def prepare(self):
        return self.layout.prepare(self.output / self.delta.data["package_name"], self.delta)

    def activate(self):
        with self.layout.lock():
            self.layout.activate(core_exited=True)

    def test_live_unconfirmed_core_does_not_roll_back(self):
        self.prepare()
        self.activate()
        with patch("haizflow.update.launcher.start_core", side_effect=CoreStillRunningError("still running")):
            with self.assertRaises(CoreStillRunningError):
                launch(self.install, wait_for_exit=False)
        self.assertEqual(self.layout.active()["active"], "0.2.0")
        self.assertEqual(self.layout.journal()["state"], "pending_health")

    def test_installer_repair_and_pre_copy_busy_gate_preserve_data(self):
        check_install(self.install, "0.1.0")
        initialize(self.install, "0.1.0")
        with file_lock(child(self.layout.state, "launcher.lock")):
            with self.assertRaises(UpdateError):
                check_install(self.install, "0.1.0")
        with file_lock(child(self.layout.state, "updater.lock")):
            with self.assertRaises(UpdateError):
                check_install(self.install, "0.1.0")
            with self.assertRaises(UpdateError):
                uninstall_cores(self.install)
        self.assertEqual(self.before, self.user_data())

    def test_installer_upgrade_and_downgrade_rejection(self):
        reconstruct(self.output / self.full2.data["package_name"], self.full2, self.layout.core("0.2.0"), None)
        initialize(self.install, "0.2.0")
        with self.assertRaisesRegex(UpdateError, "hạ phiên bản"):
            check_install(self.install, "0.1.0")
        self.assertEqual(self.layout.active()["active"], "0.2.0")
        self.assertEqual(self.before, self.user_data())

    def test_uninstaller_removes_cores_but_never_user_data(self):
        reconstruct(self.output / self.full2.data["package_name"], self.full2, self.layout.core("0.2.0"), None)
        uninstall_cores(self.install)
        self.assertEqual(list(self.layout.versions.iterdir()), [])
        self.assertFalse(self.layout.active_path.exists())
        self.assertEqual(self.before, self.user_data())

    def test_uninstaller_corruption_is_detected_before_any_delete(self):
        reconstruct(self.output / self.full2.data["package_name"], self.full2, self.layout.core("0.2.0"), None)
        (self.layout.core("0.2.0") / "added.dat").write_bytes(b"corrupt")
        with self.assertRaises(UpdateError):
            uninstall_cores(self.install)
        self.assertTrue(self.layout.core("0.1.0").exists())
        self.assertTrue(self.layout.core("0.2.0").exists())
        self.assertEqual(self.before, self.user_data())

    def fake_command(self, root):
        return [getattr(sys, "_base_executable", sys.executable), "-c", FAKE_CORE]

    def test_delta_reconstructs_exact_target_without_hardlinks(self):
        journal = self.prepare()
        self.assertEqual(journal["state"], "ready")
        self.assertEqual(inventory(self.layout.core("0.2.0")), inventory(self.target))
        self.assertEqual(self.layout.active()["active"], "0.1.0")
        (self.layout.core("0.2.0") / "_internal/same.dll").write_bytes(b"changed")
        self.assertEqual((self.layout.core("0.1.0") / "_internal/same.dll").read_bytes(), b"same-library" * 512)
        self.assertEqual(self.before, self.user_data())

    def test_end_to_end_health_success_confirms_and_preserves_user_data(self):
        self.prepare()
        self.activate()
        ready = []
        self.assertEqual(launch(self.install, command_for=self.fake_command, timeout=3,
                               on_starting=lambda: ready.append("starting"),
                               on_ready=lambda: ready.append("ready")), 0)
        self.assertEqual(ready, ["starting", "ready"])
        self.assertEqual(self.layout.journal()["state"], "confirmed")
        self.assertEqual(self.layout.active()["active"], "0.2.0")
        self.assertEqual(self.before, self.user_data())

    def test_end_to_end_startup_failure_rolls_back_once(self):
        self.prepare()
        self.activate()
        def command(root):
            return [sys.executable, "-c", "raise SystemExit(7)"] if root.name == "0.2.0" else self.fake_command(root)
        self.assertEqual(launch(self.install, command_for=command, timeout=3), 0)
        self.assertEqual(self.layout.journal()["state"], "rolled_back")
        self.assertEqual(self.layout.active()["active"], "0.1.0")
        self.assertEqual(self.before, self.user_data())

    def test_health_timeout_terminates_only_unconfirmed_core_and_rolls_back(self):
        self.prepare()
        self.activate()
        def command(root):
            return [sys.executable, "-c", "import time; time.sleep(10)"] if root.name == "0.2.0" else self.fake_command(root)
        self.assertEqual(launch(self.install, command_for=command, timeout=0.6), 0)
        self.assertEqual(self.layout.journal()["state"], "rolled_back")

    def test_crash_after_successful_health_does_not_rollback(self):
        self.prepare()
        self.activate()
        self.assertEqual(launch(self.install, command_for=lambda _: [getattr(sys, "_base_executable", sys.executable), "-c", FAKE_CORE + "\nraise SystemExit(8)"], timeout=3), 8)
        self.assertEqual(self.layout.journal()["state"], "confirmed")

    def test_interrupted_staging_recovery_keeps_old_core(self):
        with patch("haizflow.update.state.reconstruct", side_effect=Interrupted):
            with self.assertRaises(Interrupted):
                self.prepare()
        with self.layout.lock():
            self.assertEqual(self.layout.recover(), "failed")
        self.assertEqual(self.layout.active()["active"], "0.1.0")
        self.assertEqual(self.before, self.user_data())

    def test_crash_after_staging_promotes_verified_core_on_recovery(self):
        with patch.object(self.layout, "_promote", side_effect=Interrupted):
            with self.assertRaises(Interrupted):
                self.prepare()
        with self.layout.lock():
            self.assertEqual(Layout(self.install).recover(), "ready")
        self.layout.validate_core("0.2.0")
        self.assertEqual(self.layout.active()["active"], "0.1.0")

    def test_interrupted_activation_rolls_back_pointer(self):
        self.prepare()
        with self.layout.lock():
            journal = self.layout.transition(self.layout.journal(), "activating")
            atomic_json(self.layout.active_path, {"schema": 1, "active": "0.2.0", "previous": "0.1.0", "known_good": ["0.1.0"]})
            self.assertEqual(self.layout.recover(), "rolled_back")
        self.assertEqual(self.layout.active(), journal["prior_pointer"])
        self.assertEqual(self.before, self.user_data())

    def test_interrupted_confirmation_uses_durable_health_result(self):
        self.prepare()
        self.activate()
        with self.layout.lock():
            journal = self.layout.transition(self.layout.journal(), "pending_health", attempts=1)
            original = self.layout.transition
            def interrupt_confirmation(data, state, **values):
                if state == "confirmed":
                    raise Interrupted()
                return original(data, state, **values)
            with patch.object(self.layout, "transition", side_effect=interrupt_confirmation), self.assertRaises(Interrupted):
                self.layout.confirm(journal)
            self.assertEqual(self.layout.recover(launcher=True), "confirmed")
        self.assertEqual(self.layout.active()["active"], "0.2.0")

    def test_busy_core_cannot_activate(self):
        self.prepare()
        with self.layout.lock(), self.assertRaises(UpdateError):
            self.layout.activate(core_exited=False)
        self.assertEqual(self.layout.active()["active"], "0.1.0")

    def test_incomplete_existing_version_is_not_promoted(self):
        self.layout.core("0.2.0").mkdir()
        with self.assertRaises((ValueError, OSError)):
            self.prepare()
        self.assertEqual(self.layout.active()["active"], "0.1.0")

    def test_wrong_base_hash_rejected_and_full_can_repair_missing_base_file(self):
        (self.layout.core("0.1.0") / "_internal/same.dll").unlink()
        with self.assertRaises(UpdateError):
            self.prepare()
        self.layout.prepare(self.output / self.full2.data["package_name"], self.full2)
        self.layout.validate_core("0.2.0")

    def test_corrupted_package_never_changes_active(self):
        package = self.output / self.delta.data["package_name"]
        package.write_bytes(b"broken")
        with self.assertRaises(UpdateError):
            self.prepare()
        self.assertEqual(self.layout.active()["active"], "0.1.0")
        self.assertEqual(self.before, self.user_data())

    def test_disk_full_does_not_activate(self):
        with patch("haizflow.update.packages.shutil.disk_usage", return_value=shutil._ntuple_diskusage(1, 1, 0)):
            with self.assertRaisesRegex(UpdateError, "dung lượng"):
                self.prepare()
        self.assertEqual(self.layout.active()["active"], "0.1.0")

    def test_schema_migration_update_is_rejected_before_staging(self):
        data = copy.deepcopy(self.full2.data)
        data["data_compatibility"]["project_schema"] = 5
        with self.assertRaisesRegex(UpdateError, "Schema"):
            self.layout.prepare(self.output / self.full2.data["package_name"], Manifest.parse(data))

    def test_manifest_invalid_inputs(self):
        invalid = [{"target_version": "../2"}, {"manifest_schema": 2}, {"architecture": "arm64"},
                   {"package_sha256": "wrong"}, {"base_version": "0.2.0"}, {"package_size": True}]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(UpdateError):
                Manifest.parse(dict(self.delta.data, **changes))
        data = dict(self.delta.data)
        del data["product"]
        with self.assertRaises(UpdateError):
            Manifest.parse(data)

    def test_unsafe_windows_paths(self):
        for name in ("../escape", "/absolute", "C:/absolute", "\\\\server\\share", "\\\\?\\C:\\file",
                     "CON", "x/NUL.txt", "a/../b", "name.", "file:stream", "x//y", "a\\b"):
            with self.subTest(name=name), self.assertRaises(UpdateError):
                relative_path(name)

    def test_duplicate_and_case_collision_paths_rejected(self):
        for name in ("HaizFlowCore.exe", "haizflowcore.exe", "HaizFlowCore.exe/child"):
            data = copy.deepcopy(self.delta.data)
            data["target_files"].append(dict(data["target_files"][0], path=name))
            with self.subTest(name=name), self.assertRaises(UpdateError):
                Manifest.parse(data)

    def test_zip_traversal_cannot_extract_even_with_correct_package_digest(self):
        package = self.output / self.delta.data["package_name"]
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("../escape", "BAD")
        data = dict(self.delta.data, package_size=package.stat().st_size, package_sha256=sha256(package))
        with self.assertRaises(UpdateError):
            reconstruct(package, Manifest.parse(data), self.root / "stage", self.base)
        self.assertFalse((self.root / "escape").exists())

    def test_no_change_delta_is_supported(self):
        other = generate(self.base, self.base, self.root / "unchanged", base_version="0.1.0", target_version="0.1.1")
        reconstruct(self.root / "unchanged" / other.data["package_name"], other, self.root / "unchanged-stage", self.base)
        self.assertEqual(inventory(self.root / "unchanged-stage"), inventory(self.base))

    def test_locks_release_on_exit_and_block_concurrent_process(self):
        path = self.layout.state / "update.lock"
        with file_lock(path), self.assertRaises(UpdateError):
            with file_lock(path):
                self.fail("concurrent lock acquired")
        with file_lock(path):
            pass

    def test_concurrent_launcher_never_starts_second_core(self):
        with file_lock(child(self.layout.state, "launcher.lock")), self.assertRaises(UpdateError), \
                patch("haizflow.update.launcher.subprocess.Popen") as spawned:
            launch(self.install, popen=spawned)
        spawned.assert_not_called()

    def test_missing_core_without_previous_gives_repair_error(self):
        (self.layout.core("0.1.0") / "HaizFlowCore.exe").unlink()
        with self.assertRaisesRegex(UpdateError, "Không có Core hợp lệ"):
            launch(self.install, command_for=self.fake_command)
        self.assertEqual(self.before, self.user_data())

    def test_wrong_base_version_and_malformed_journal_do_not_change_active(self):
        data = dict(self.delta.data, base_version="0.0.9", package_name="HaizFlow-Core-0.2.0-windows-x64-from-0.0.9.zip")
        with self.assertRaisesRegex(UpdateError, "Delta không hỗ trợ"):
            self.layout.prepare(self.output / self.delta.data["package_name"], Manifest.parse(data))
        self.layout.journal_path.write_text("[]")
        with self.layout.lock(), self.assertRaises(UpdateError):
            self.layout.recover()
        self.assertEqual(self.layout.active()["active"], "0.1.0")

    def test_cleanup_rejects_user_data_and_protects_versions(self):
        self.prepare()
        self.assertEqual(self.layout.cleanup_versions(running_versions={"0.1.0"}), [])
        with self.assertRaises(UpdateError):
            remove_owned(self.layout.staging, self.external)
        self.assertEqual(self.before, self.user_data())

    def test_malformed_state_recovers_only_confirmed_snapshot(self):
        self.layout.active_path.write_text("[]")
        self.assertEqual(launch(self.install, command_for=self.fake_command, timeout=3), 0)
        self.assertEqual(self.layout.active()["active"], "0.1.0")
        self.assertEqual(self.before, self.user_data())

    def test_malformed_state_without_confirmed_snapshot_refuses_guessing(self):
        self.layout.active_path.write_text("[]")
        (self.layout.state / "last-confirmed.json").write_text("[]")
        with self.assertRaises(UpdateError):
            launch(self.install, command_for=self.fake_command)
        self.assertEqual(self.before, self.user_data())

    def test_full_fallback_uses_only_verified_release_assets(self):
        class Client:
            def latest(inner):
                return {"tag_name": "v0.2.0", "assets": [{"name": self.full2.data["package_name"]}]}
            def fetch_manifest(inner, *_):
                return self.full2
            def asset(inner, release, name):
                return {"sha256": self.full2.data["package_sha256"], "size": self.full2.data["package_size"], "name": name}
            def download(inner, asset, directory, *, progress):
                return self.output / asset["name"]
        self.assertEqual(prepare_latest(self.layout, "0.2.0", client=Client())["state"], "ready")
        self.layout.validate_core("0.2.0")

    def test_independent_updater_waits_permission_and_actual_exit(self):
        from haizflow.update.updater import create_request, run_request
        token = create_request(self.layout, "0.2.0")
        (self.install / "HaizFlow.exe").write_bytes(b"launcher fixture")
        atomic_json(child(self.layout.ipc, token + ".activate.json"), {"token": token, "activate": True})
        with patch("haizflow.update.updater.prepare_latest", side_effect=lambda *_a, **_k: self.prepare()), \
                patch("haizflow.update.updater.subprocess.Popen") as spawned:
            run_request(self.install, token, alive=lambda _: False, launch_process=spawned)
            spawned.assert_called_once()
        self.assertEqual(self.layout.journal()["state"], "pending_health")
        self.assertEqual(self.before, self.user_data())

    def test_independent_updater_defer_never_terminates_old_core(self):
        from haizflow.update.updater import create_request, run_request
        token = create_request(self.layout, "0.2.0")
        with patch("haizflow.update.updater.prepare_latest", side_effect=lambda *_a, **_k: self.prepare()), \
                patch("haizflow.update.updater.subprocess.Popen") as spawned:
            run_request(self.install, token, activation_timeout=0, launch_process=spawned)
            spawned.assert_not_called()
        self.assertEqual(self.layout.journal()["state"], "ready")
        self.assertEqual(self.layout.active()["active"], "0.1.0")

    def test_junction_cleanup_rejected(self):
        if os.name != "nt":
            self.skipTest("Windows junction test")
        self.layout.staging.mkdir(parents=True)
        owned = self.layout.staging / "owned"
        owned.mkdir()
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(owned / "link"), str(self.external)],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            self.skipTest("junction creation unavailable")
        try:
            with self.assertRaises(UpdateError):
                remove_owned(self.layout.staging, owned)
        finally:
            os.rmdir(owned / "link")  # unlink junction only; never recursive
        self.assertEqual(self.before, self.user_data())


class Response(BytesIO):
    def __init__(self, value, url):
        super().__init__(value)
        self.url = url
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class DownloadTests(unittest.TestCase):
    def test_official_public_release_requires_stable_tag_repo(self):
        payload = {"tag_name": "v0.2.0", "html_url": "https://github.com/MachHongHai/HaizFlow/releases/tag/v0.2.0",
                   "draft": False, "prerelease": False, "assets": []}
        for changes in ({}, {"draft": True}, {"tag_name": "v0.2.0-rc1"}, {"html_url": "https://github.com/other/repo/releases/tag/v0.2.0"}):
            client = GitHubClient(opener=lambda *_args, **_kwargs: Response(json.dumps(dict(payload, **changes)).encode(), API))
            if changes:
                with self.assertRaises(UpdateError):
                    client.latest()
            else:
                self.assertEqual(client.latest(), payload)

    def test_redirect_policy_rejects_before_contacting_untrusted_host(self):
        for url in ("http://github.com/file", "https://evil.invalid/file", "https://github.com/other/repo/releases/download/v1/file",
                    "https://github.com@evil.invalid/file"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                allowed_url(url)
        request = __import__("urllib.request", fromlist=["Request"]).Request("https://github.com/MachHongHai/HaizFlow/releases/download/v0.2.0/file.zip")
        with self.assertRaises(UpdateError):
            RedirectPolicy().redirect_request(request, None, 302, "Found", {}, "https://evil.invalid/a")

    def test_partial_and_wrong_digest_downloads_never_publish(self):
        data = b"package"
        asset = {"name": "file.zip", "url": "https://github.com/MachHongHai/HaizFlow/releases/download/v0.2.0/file.zip",
                 "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            for body in (b"half", b"wrong!!"):
                client = GitHubClient(opener=lambda *_args, **_kwargs: Response(body, asset["url"]))
                with self.assertRaises(UpdateError):
                    client.download(asset, Path(directory))
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_api_failure_propagates_without_mutating_files(self):
        client = GitHubClient(opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timeout")))
        with self.assertRaises(TimeoutError):
            client.latest()

    def test_asset_missing_digest_or_wrong_repo_is_rejected(self):
        name = "HaizFlow-Core-0.2.0-windows-x64-full.zip"
        asset = {"name": name, "size": 1, "state": "uploaded", "digest": "sha256:" + "1" * 64,
                 "browser_download_url": "https://github.com/MachHongHai/HaizFlow/releases/download/v0.2.0/" + name}
        client = GitHubClient()
        for changes in ({"digest": None}, {"size": -1}, {"state": "new"}, {"browser_download_url": "https://evil.invalid/file"}):
            with self.assertRaises(UpdateError):
                client.asset({"tag_name": "v0.2.0", "assets": [dict(asset, **changes)]}, name)


if __name__ == "__main__":
    unittest.main()
