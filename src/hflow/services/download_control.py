"""Per-download cancellation for yt-dlp network streams and FFmpeg.

No global patches: only the owning YoutubeDL and postprocessor instances are
wrapped. Another project/download is never stopped by this controller.
"""

from __future__ import annotations

import os
import logging
import socket
import subprocess
import threading
from types import MethodType


class _CancellableSocket:
    """Poll reads on the owning stream; preserve its original timeout budget."""

    def __init__(self, sock, control):
        self._socket = sock
        self._control = control
        self._timeout = sock.gettimeout()
        sock.settimeout(0.2)

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def recv_into(self, *args, **kwargs):
        import time
        deadline = time.monotonic() + (self._timeout or 20)
        while True:
            self._control.check()
            try:
                return self._socket.recv_into(*args, **kwargs)
            except TimeoutError:
                self._control.check()
                if time.monotonic() >= deadline:
                    raise


class DownloadControl:
    def __init__(self, downloader, cancel_event, cancelled_error):
        self.downloader = downloader
        self.cancel = cancel_event
        self.error = cancelled_error
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._responses = []
        self._processes = set()
        self._restores = []
        self._watcher = None

    def check(self):
        if self.cancel is not None and self.cancel.is_set():
            raise self.error("Download cancelled.")

    def __enter__(self):
        self.check()
        if self.cancel is None:
            return self
        parameters = getattr(self.downloader, "params", None)
        if isinstance(parameters, dict):
            parameters["socket_timeout"] = min(float(parameters.get("socket_timeout") or 5), 5)
        original = getattr(self.downloader, "urlopen", None)
        if callable(original):
            def open_url(request):
                self.check()
                # Bound connection/header waits too; closing an active response
                # cannot interrupt a connection that has not returned one yet.
                if hasattr(request, "extensions"):
                    request.extensions["timeout"] = min(
                        float(request.extensions.get("timeout") or 5.0), 5.0)
                response = original(request)
                with self._lock:
                    self._responses.append(response)
                self.check()
                stream = getattr(response, "fp", None)
                stream = getattr(stream, "_fp", None) or stream
                stream = getattr(stream, "fp", None) or stream
                raw = getattr(stream, "raw", None)
                if isinstance(raw, socket.SocketIO) and not isinstance(raw._sock, _CancellableSocket):
                    raw._sock = _CancellableSocket(raw._sock, self)
                read = response.read

                def read_checked(*args, **kwargs):
                    self.check()
                    try:
                        data = read(*args, **kwargs)
                    except Exception:
                        self.check()
                        raise
                    self.check()  # Do not write a chunk received after Stop.
                    return data

                response.read = read_checked
                return response

            self._replace(self.downloader, "urlopen", open_url)
        run_pp = getattr(self.downloader, "run_pp", None)
        if callable(run_pp):
            def run_postprocessor(pp, info):
                self.check()
                original_ffmpeg = getattr(pp, "real_run_ffmpeg", None)
                if callable(original_ffmpeg):
                    # All merger/remuxer subclasses use this common method.
                    pp.real_run_ffmpeg = MethodType(self._ffmpeg, pp)
                try:
                    result = run_pp(pp, info)
                    self.check()
                    return result
                finally:
                    if callable(original_ffmpeg):
                        pp.real_run_ffmpeg = original_ffmpeg

            self._replace(self.downloader, "run_pp", run_postprocessor)
        self._watcher = threading.Thread(target=self._watch, name="download-cancellation", daemon=True)
        self._watcher.start()
        return self

    def _replace(self, owner, name, value):
        self._restores.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def _watch(self):
        while not self._done.wait(0.1):
            if not self.cancel.is_set():
                continue
            with self._lock:
                responses, processes = tuple(self._responses), tuple(self._processes)
            logging.getLogger(__name__).debug("download cancellation active streams=%d processes=%d", len(responses), len(processes))
            for process in processes:
                try:
                    process.terminate()
                except OSError:
                    pass
            for response in responses:
                backend = getattr(getattr(response, "fp", None), "_response", None)
                quit_now = getattr(backend, "quit_now", None)
                if quit_now is not None:
                    quit_now.set()
                # Do not close a buffered reader from another thread: Windows
                # waits for its pending read. Socket reads above poll Stop;
                # close/release happens on the owning thread in __exit__.
                elif not hasattr(response, "fp"):
                    response.close()  # Simple/custom non-buffered streams.
            return

    def _ffmpeg(self, pp, inputs, outputs, *, expected_retcodes=(0,)):
        # Command assembly follows yt-dlp FFmpegPostProcessor.real_run_ffmpeg
        # (Unlicense; see THIRD_PARTY_NOTICES.md). Adapted only to poll Stop and
        # own/reap the child. Preserve yt-dlp's options, mapping and timestamps.
        from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessorError
        from yt_dlp.utils import variadic

        self.check()
        pp.check_version()
        oldest = min(os.stat(path).st_mtime for path, _ in inputs if path)
        command = [pp.executable, "-y"]
        if pp.basename == "ffmpeg":
            command += ["-loglevel", "repeat+info"]
        for kind, files in (("i", inputs), ("o", outputs)):
            for number, (path, options) in enumerate(files, 1):
                if not path:
                    continue
                keys = [f"_{kind}{number}", f"_{kind}"]
                args = list(options)
                if kind == "o":
                    args += ["-movflags", "+faststart"]
                    if number == 1:
                        keys.append("")
                args += pp._configuration_args(pp.basename, keys)
                if kind == "i":
                    args.append("-i")
                command += args + [pp._ffmpeg_filename_argument(path)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with self._lock:
            self._processes.add(process)
        try:
            while True:
                self.check()
                try:
                    _, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            self.check()
            if process.returncode not in variadic(expected_retcodes):
                raise FFmpegPostProcessorError(stderr.strip().splitlines()[-1] if stderr.strip() else
                                              "FFmpeg did not finish the download.")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
            with self._lock:
                self._processes.discard(process)
        for path, _ in outputs:
            if path:
                pp.try_utime(path, oldest, oldest)
        return stderr

    def __exit__(self, *_args):
        self._done.set()
        if self._watcher:
            self._watcher.join(timeout=0.5)
        for owner, name, original in reversed(self._restores):
            setattr(owner, name, original)
        # Completed responses must not accumulate over a long channel import.
        for response in self._responses:
            try:
                response.close()
            except (OSError, ValueError):
                pass
        self._responses.clear()
