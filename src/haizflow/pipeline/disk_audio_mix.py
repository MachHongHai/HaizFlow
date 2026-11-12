"""PCM accumulator with Pydub's saturating overlay semantics and bounded copies."""

from pathlib import Path
import os
import subprocess
import tempfile

from pydub.audio_segment import audioop

from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.utils.ffmpeg import _binary


class DiskAudioMix:
    def __init__(self, audio, directory, process_id):
        self._temporary = tempfile.TemporaryDirectory(prefix=".audio-pcm-", dir=directory)
        self.path = Path(self._temporary.name) / "mix.pcm"
        self.sample_width = audio.sample_width
        self.channels = audio.channels
        self.frame_rate = audio.frame_rate
        self.process_id = process_id
        self._stream = None
        try:
            self.path.write_bytes(audio.raw_data)
            self._stream = self.path.open("r+b")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._temporary.cleanup()

    def _promote(self, sample_width, frame_rate):
        if (sample_width, frame_rate) == (self.sample_width, self.frame_rate):
            return
        target = self.path.with_suffix(".promoted")
        self._stream.seek(0)
        state = None
        with target.open("wb") as output:
            while block := self._stream.read(65536 * self.channels * self.sample_width):
                check_cancellation(self.process_id)
                if frame_rate != self.frame_rate:
                    block, state = audioop.ratecv(block, self.sample_width, self.channels,
                                                  self.frame_rate, frame_rate, state)
                if sample_width != self.sample_width:
                    block = audioop.lin2lin(block, self.sample_width, sample_width)
                output.write(block)
        self._stream.close()
        self._stream = None
        os.replace(target, self.path)
        self._stream = self.path.open("r+b")
        self.sample_width, self.frame_rate = sample_width, frame_rate
        self._align_milliseconds()

    def _align_milliseconds(self):
        frame_width = self.channels * self.sample_width
        self._stream.seek(0, os.SEEK_END)
        size = self._stream.tell()
        milliseconds = round(size / frame_width / self.frame_rate * 1000)
        target = int(milliseconds * self.frame_rate / 1000) * frame_width
        if target > size:
            self._stream.write(b"\0" * (target - size))
        elif target < size:
            self._stream.truncate(target)

    def overlay(self, audio, position=0):
        self._promote(max(self.sample_width, audio.sample_width), max(self.frame_rate, audio.frame_rate))
        self._align_milliseconds()
        audio = audio.set_channels(self.channels).set_frame_rate(self.frame_rate).set_sample_width(self.sample_width)
        frame_width = self.channels * self.sample_width
        offset = int(max(0, position) * self.frame_rate / 1000) * frame_width
        self._stream.seek(0, os.SEEK_END)
        remaining = max(0, self._stream.tell() - offset)
        data = memoryview(audio.raw_data)
        count = min(len(data), remaining)
        block_size = 65536 * frame_width
        for cursor in range(0, count, block_size):
            check_cancellation(self.process_id)
            size = min(block_size, count - cursor)
            self._stream.seek(offset + cursor)
            mixed = audioop.add(self._stream.read(size), data[cursor:cursor + size], self.sample_width)
            self._stream.seek(offset + cursor)
            self._stream.write(mixed)
        return self

    def export(self, destination, duration_ms):
        self._align_milliseconds()
        self._stream.flush()
        format_name = {1: "s8", 2: "s16le", 3: "s24le", 4: "s32le"}[self.sample_width]
        check_cancellation(self.process_id)
        process = subprocess.Popen([
            _binary("ffmpeg"), "-y", "-v", "error", "-f", format_name,
            "-ar", str(self.frame_rate), "-ac", str(self.channels), "-i", str(self.path),
            "-t", f"{duration_ms / 1000:.6f}", "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s24le", str(destination),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _, error = communicate_process(self.process_id, process, label="Audio PCM publication")
        if process.returncode:
            raise RuntimeError(f"Audio PCM publication failed: {error[-900:]}")
        check_cancellation(self.process_id)
        return open(destination, "rb")
