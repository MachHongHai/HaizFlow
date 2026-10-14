"""Bounded, non-blocking preview audio through the export's FFmpeg tempo filter."""

from __future__ import annotations

import queue
import subprocess
import threading

from hflow.utils.ffmpeg import _binary


class PreviewTempoStream:
    def __init__(self, mixer, cursor, rate, sample_rate=48000):
        from hflow.pipeline.audio_timeline import _atempo_filters

        self._queue = queue.Queue(maxsize=8)
        self._pending = bytearray()
        self._stop = threading.Event()
        self.error = ""
        self._process = subprocess.Popen(
            [_binary("ffmpeg"), "-v", "error", "-nostdin", "-threads", "1",
             "-f", "s16le", "-ar", str(sample_rate), "-ac", "2",
             "-probesize", "32", "-analyzeduration", "0", "-i", "pipe:0",
             "-filter_threads", "1", "-af", _atempo_filters(rate),
             "-f", "s16le", "-ar", str(sample_rate), "-ac", "2", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Output queue and OS pipes provide backpressure; no full-video mix or
        # disk cache. PCM mixing and pipe I/O never run on the GUI timer.
        self._writer = threading.Thread(
            target=self._feed, args=(mixer, int(cursor), sample_rate // 20),
            name="preview-tempo-input", daemon=True,
        )
        self._reader = threading.Thread(target=self._receive, name="preview-tempo-output", daemon=True)
        self._writer.start()
        self._reader.start()

    def _feed(self, mixer, cursor, count):
        try:
            while not self._stop.is_set():
                data = memoryview(mixer(cursor, count))
                while data and not self._stop.is_set():
                    written = self._process.stdin.write(data)
                    if not written:
                        return
                    data = data[written:]
                cursor += count
        except Exception:
            if not self._stop.is_set():
                self.error = "Không thể chuẩn bị âm thanh tăng tốc xem trước."
        finally:
            self._process.stdin.close()

    def _receive(self):
        try:
            while not self._stop.is_set():
                data = self._process.stdout.read(8192)
                if not data:
                    if not self._stop.is_set():
                        self.error = "Bộ lọc tốc độ âm thanh xem trước đã dừng."
                    return
                while not self._stop.is_set():
                    try:
                        self._queue.put(data, timeout=.05)
                        break
                    except queue.Full:
                        continue
        except (OSError, ValueError):
            if not self._stop.is_set():
                self.error = "Không thể phát âm thanh tăng tốc xem trước."
        finally:
            self._process.stdout.close()

    def peek(self, frames):
        """Only take already-produced PCM; preserve odd/partial device writes."""
        size = frames * 4
        while len(self._pending) < size:
            try:
                self._pending.extend(self._queue.get_nowait())
            except queue.Empty:
                break
        return bytes(self._pending[:min(size, len(self._pending) // 4 * 4)])

    def consume(self, size):
        del self._pending[:size]

    def close(self):
        self._stop.set()
        if self._process.poll() is None:
            try:
                self._process.kill()
            except OSError:
                pass
        # Reaping is bounded and does not wait for a blocked queue producer.
        try:
            self._process.wait(timeout=.25)
        except subprocess.TimeoutExpired:
            pass
        self._pending.clear()
