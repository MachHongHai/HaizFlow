"""Cancellation, TLS and project ownership; mock network, real FFmpeg child."""
import hashlib
import ssl
import subprocess
import threading
import time
import sys
import traceback
import urllib.error
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.url_import import VideoUrlImportCoordinator
from haizflow.services import model_bootstrap
from haizflow.services.download_control import DownloadControl
from haizflow.services.video_download import DownloadCancelled
from haizflow.utils.ffmpeg import _binary

_GUI = None


@pytest.fixture(scope="module", autouse=True)
def gui():
    global _GUI
    _GUI = QGuiApplication.instance() or QGuiApplication([])
    yield _GUI


def test_download_tls_augments_os_roots_without_disabling_verification():
    context = Mock()
    with patch.object(ssl, "create_default_context", return_value=context) as create:
        assert model_bootstrap._download_tls_context() is context
    create.assert_called_once_with()
    context.load_verify_locations.assert_called_once_with(cafile=model_bootstrap.certifi.where())
    real = model_bootstrap._download_tls_context()
    assert real.check_hostname and real.verify_mode == ssl.CERT_REQUIRED


def test_untrusted_certificate_is_not_retried_or_downloaded_insecurely(tmp_path):
    asset = model_bootstrap.ModelAsset("test", "CPU", "https://github.com/test/pack", "pack.bin", 1,
                                      hashlib.sha256(b"a").hexdigest())
    error = urllib.error.URLError(ssl.SSLCertVerificationError("untrusted root"))
    with patch.object(model_bootstrap, "_open_download", side_effect=error) as download:
        with pytest.raises(model_bootstrap.ModelBootstrapError, match="kết nối an toàn"):
            model_bootstrap._download_asset(tmp_path, asset, base_completed=0, total_bytes=1,
                                            progress=Mock(), cancel_event=None)
    assert download.call_count == 1
    assert not (tmp_path / "pack.bin").exists()


def test_resource_download_always_passes_a_verified_tls_context():
    response = Mock()
    response.geturl.return_value = "https://github.com/test/pack"
    asset = model_bootstrap.ModelAsset("test", "CPU", response.geturl(), "pack.bin", 1,
                                      hashlib.sha256(b"a").hexdigest())
    with patch.object(model_bootstrap.urllib.request, "urlopen", return_value=response) as opened:
        assert model_bootstrap._open_download(asset, 4) is response
    context = opened.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert opened.call_args.args[0].get_header("Range") == "bytes=4-"


def test_stop_interrupts_a_waiting_stream_and_rejects_the_late_chunk():
    cancel, reading, closed = threading.Event(), threading.Event(), threading.Event()

    def read(_size):
        reading.set()
        assert closed.wait(2)
        return b"late bytes"

    response = SimpleNamespace(read=read, close=closed.set)
    downloader = SimpleNamespace(urlopen=Mock(return_value=response), params={})
    errors = []

    def download():
        try:
            with DownloadControl(downloader, cancel, DownloadCancelled):
                downloader.urlopen("url").read(1024)
        except DownloadCancelled:
            errors.append("cancelled")

    worker = threading.Thread(target=download)
    worker.start()
    assert reading.wait(2)
    cancel.set()
    worker.join(2)
    assert not worker.is_alive() and errors == ["cancelled"]


def test_cancellation_does_not_patch_another_downloader():
    one = SimpleNamespace(urlopen=Mock(), params={})
    two = SimpleNamespace(urlopen=Mock(), params={})
    original = two.urlopen
    cancel = threading.Event()
    with DownloadControl(one, cancel, DownloadCancelled):
        cancel.set()
        with pytest.raises(DownloadCancelled):
            one.urlopen("url")
        assert two.urlopen is original
        two.urlopen("other")
    assert two.urlopen.call_count == 1


def test_stop_interrupts_real_ytdlp_http_read_without_waiting_for_server_timeout():
    import yt_dlp
    cancel, reading, release = threading.Event(), threading.Event(), threading.Event()

    class SlowMedia(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "1000000")
            self.end_headers()
            self.wfile.write(b"partial media")
            self.wfile.flush()
            release.wait(5)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowMedia)
    server.daemon_threads = True
    serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=.1), daemon=True)
    serving.start()
    errors = []
    responses = []

    def download():
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "proxy": ""}) as downloader, \
                    DownloadControl(downloader, cancel, DownloadCancelled):
                response = downloader.urlopen(f"http://127.0.0.1:{server.server_port}/media")
                stream = response.fp
                stream = getattr(stream, "_fp", None) or stream
                stream = getattr(stream, "fp", None) or stream
                responses.append((type(response).__name__, repr(getattr(getattr(stream, "raw", None), "_sock", None))))
                reading.set()
                response.read(1000000)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=download, daemon=True)
    worker.start()
    try:
        assert reading.wait(5)
        cancel.set()
        worker.join(2)
        frames = sys._current_frames()
        stacks = ["".join(traceback.format_stack(frames[t.ident])) for t in threading.enumerate()
                  if t.ident in frames and (t is worker or t.name == "download-cancellation")]
        if worker.is_alive():
            pytest.fail("\n".join(stacks))
        assert len(errors) == 1 and isinstance(errors[0], DownloadCancelled)
    finally:
        cancel.set()
        release.set()
        worker.join(5)
        server.shutdown()
        server.server_close()
        serving.join(2)


def test_stop_terminates_and_reaps_real_ffmpeg_remux(tmp_path):
    source, output = tmp_path / "source.mp4", tmp_path / "result.mp4"
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=s=64x64:d=1:r=5", "-c:v", "libx264", str(source)],
                   check=True, capture_output=True, timeout=20)
    pp = SimpleNamespace(executable=_binary("ffmpeg"), basename="ffmpeg", check_version=Mock(),
                         _configuration_args=lambda *_: [], _ffmpeg_filename_argument=str, try_utime=Mock())
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    control = DownloadControl(SimpleNamespace(), cancel, DownloadCancelled)
    started = time.monotonic()
    timer.start()
    try:
        with control, pytest.raises(DownloadCancelled):
            control._ffmpeg(pp, [(str(source), ["-re", "-stream_loop", "-1"])],
                            [(str(output), ["-c", "copy"])])
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3
    assert not control._processes
    pp.try_utime.assert_not_called()


@pytest.mark.parametrize("callback", ["metadata", "download"])
def test_queued_completion_after_stop_cannot_import(callback, tmp_path):
    coordinator = VideoUrlImportCoordinator()
    ready = Mock()
    coordinator.downloadReady.connect(ready)
    coordinator._state = "downloading"
    coordinator.cancel()
    if callback == "metadata":
        coordinator._handle_metadata(coordinator._generation, {"title": "late"})
    else:
        with patch("haizflow.desktop.url_import.cleanup_download_workspace") as cleanup:
            coordinator._handle_download(coordinator._generation, str(tmp_path / "video.mp4"), str(tmp_path))
        cleanup.assert_called_once()
    assert coordinator.state == "idle"
    ready.assert_not_called()


@pytest.mark.parametrize("stopped", [True, False])
def test_deletion_waits_for_the_owning_download(stopped):
    importer = SimpleNamespace(state="downloading", cancel=Mock(), shutdown=Mock(return_value=stopped), begin=Mock())
    host = SimpleNamespace(_url_import_target={"project_key": "owner"}, _url_importer=importer)
    commands = ProjectCommandsController(host)
    assert commands._stop_project_url_download("unrelated")
    importer.cancel.assert_not_called()
    assert commands._stop_project_url_download("owner") == stopped
    importer.cancel.assert_called_once()
    if stopped:
        assert host._url_import_target is None
        importer.begin.assert_called_once()
    else:
        assert host._url_import_target == {"project_key": "owner"}
        importer.begin.assert_not_called()


def test_deletion_cannot_race_atomic_background_import():
    host = SimpleNamespace(_project_import=SimpleNamespace(has_project_work=Mock(return_value=True)))
    assert not ProjectCommandsController(host)._stop_project_url_download("owner")


@pytest.mark.parametrize("runner_exited", [False, True])
def test_delete_waits_for_owned_runner_finally_after_stop(runner_exited):
    queue = SimpleNamespace(active_video_id="separating", detach_pending=Mock(return_value=("separating", [])))
    host = SimpleNamespace(_processing_queue=queue, appAlertRequested=SimpleNamespace(emit=Mock()))
    def cancel(video_id):
        assert video_id == "separating"
        if runner_exited:
            queue.active_video_id = None
    with patch("haizflow.desktop.project_commands_controller.cancel_video", side_effect=cancel):
        assert ProjectCommandsController(host)._stop_project_processing([SimpleNamespace(video_id="separating")]) == runner_exited
    queue.detach_pending.assert_called_once_with({"separating"})
    assert host.appAlertRequested.emit.called == (not runner_exited)


def test_delete_never_cancels_another_projects_processing():
    queue = SimpleNamespace(active_video_id="unrelated", detach_pending=Mock(return_value=(None, ["owned"])))
    host = SimpleNamespace(_processing_queue=queue, appAlertRequested=SimpleNamespace(emit=Mock()))
    with patch("haizflow.desktop.project_commands_controller.cancel_video") as cancel:
        assert ProjectCommandsController(host)._stop_project_processing([SimpleNamespace(video_id="owned")])
    cancel.assert_not_called()
