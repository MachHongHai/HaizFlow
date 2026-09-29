"""Microphone capture for an authorised OmniVoice reference sample.

Pulling PCM from QAudioSource gives the recorder an actual level meter and
lets us close a valid WAV before the project imports it. QMediaRecorder's
container finalisation is asynchronous on Windows, which made the previous
fixed-delay import race with the encoder.
"""

import array
import math
import sys
import wave

from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices


class VoiceCloneRecorder:
    BAR_COUNT = 48

    def __init__(self) -> None:
        self._source: QAudioSource | None = None
        self._stream = None
        self._wave = None
        self._path = ""
        self._sample_rate = 0
        self._capture_format: QAudioFormat | None = None
        self._pending_pcm = b""
        self._sample_bytes = 0
        self._max_rms = 0.0
        self._peaks: list[float] = [0.04] * self.BAR_COUNT
        self.error = ""

    @property
    def active(self) -> bool:
        return self._source is not None

    @property
    def path(self) -> str:
        return self._path

    def start(self, path: str) -> bool:
        self.cancel()
        self.error = ""
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.error = "Không tìm thấy microphone. Hãy kiểm tra thiết bị ghi âm trong Windows."
            return False

        try:
            # WASAPI often advertises mono/16 kHz conversion yet refuses to
            # open that format while another app has the microphone. Start in
            # the device's native format first and convert to mono PCM for the
            # managed WAV. Retry common formats if native startup fails.
            candidates = [device.preferredFormat()]
            for sample_rate in (48_000, 44_100, 16_000, 24_000):
                audio_format = QAudioFormat()
                audio_format.setSampleRate(sample_rate)
                audio_format.setChannelCount(1)
                audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
                if device.isFormatSupported(audio_format):
                    candidates.append(audio_format)
            opened = None
            last_error = "NoError"
            for audio_format in candidates:
                source = QAudioSource(device, audio_format)
                stream = source.start()
                # PySide6 exposes QAudioSource.Error and QAudio.Error as
                # different enum classes. Their NoError members print alike
                # but compare unequal on Windows.
                if stream is not None and source.error().value == 0:
                    opened = (source, stream, audio_format)
                    break
                last_error = source.error().name
                source.stop()
                source.deleteLater()
            if opened is None:
                raise RuntimeError(
                    "Không thể mở microphone "
                    f"({last_error}). Hãy kiểm tra thiết bị và quyền microphone trong Windows."
                )
            self._source, self._stream, self._capture_format = opened
            self._wave = wave.open(path, "wb")
            self._wave.setnchannels(1)
            self._wave.setsampwidth(2)
            self._wave.setframerate(self._capture_format.sampleRate())
        except (OSError, RuntimeError) as exc:
            self.error = str(exc)
            self.cancel()
            return False

        self._path = path
        self._sample_rate = self._capture_format.sampleRate()
        self._sample_bytes = 0
        self._max_rms = 0.0
        self._pending_pcm = b""
        self._peaks = [0.04] * self.BAR_COUNT
        return True

    def _mono_int16(self, data: bytes) -> bytes:
        audio_format = self._capture_format
        if audio_format is None:
            return data[: len(data) - len(data) % 2]
        channels = max(1, audio_format.channelCount())
        sample_format = audio_format.sampleFormat()
        if sample_format == QAudioFormat.SampleFormat.Float:
            kind, width, scale = "f", 4, 32767
        elif sample_format == QAudioFormat.SampleFormat.Int32:
            kind, width, scale = "i", 4, 1 / 65536
        elif sample_format == QAudioFormat.SampleFormat.UInt8:
            kind, width, scale = "B", 1, 256
        else:
            kind, width, scale = "h", 2, 1
        frame_bytes = width * channels
        combined = self._pending_pcm + data
        usable_bytes = len(combined) - len(combined) % frame_bytes
        self._pending_pcm = combined[usable_bytes:]
        samples = array.array(kind)
        samples.frombytes(combined[:usable_bytes])
        if sys.byteorder != "little" and width > 1:
            samples.byteswap()
        mono = array.array("h")
        for offset in range(0, len(samples), channels):
            level = sum(samples[offset:offset + channels]) / channels
            if kind == "B":
                level -= 128
            mono.append(max(-32768, min(32767, round(level * scale))))
        if sys.byteorder != "little":
            mono.byteswap()
        return mono.tobytes()

    def _consume_pcm(self, data: bytes) -> None:
        if not data or self._wave is None:
            return
        usable = self._mono_int16(data)
        if not usable:
            return
        self._wave.writeframesraw(usable)
        self._sample_bytes += len(usable)
        samples = array.array("h")
        samples.frombytes(usable)
        if sys.byteorder != "little":
            samples.byteswap()
        rms = math.sqrt(sum(value * value for value in samples) / len(samples))
        self._max_rms = max(self._max_rms, rms)
        peak = round(max(0.04, min(1.0, rms / 10_000)), 3)
        self._peaks = [*self._peaks[1:], peak]

    def poll(self) -> dict[str, object]:
        if self._stream is not None:
            try:
                self._consume_pcm(bytes(self._stream.readAll()))
            except (OSError, RuntimeError):
                self.error = "Không thể ghi mẫu giọng. Hãy kiểm tra microphone và dung lượng ổ đĩa."
        if self._source is not None and (
            self._source.error().value != 0
            or self._source.state().name == "StoppedState"
        ):
            self.error = "Microphone đã ngừng hoạt động. Hãy kiểm tra thiết bị ghi âm."
        if self._source is not None and self.error:
            self._close_capture()
        return {
            "active": self.active,
            "durationMs": round(self._sample_bytes * 1000 / (self._sample_rate * 2)) if self._sample_rate else 0,
            "peaks": self._peaks,
            "error": self.error,
        }

    def stop(self) -> str:
        self.poll()
        path = self._path
        duration_ms = round(self._sample_bytes * 1000 / (self._sample_rate * 2)) if self._sample_rate else 0
        self._close_capture()
        if self.error:
            return ""
        if not path or duration_ms < 1_000:
            self.error = "Mẫu ghi âm quá ngắn hoặc không có tiếng. Hãy ghi ít nhất một giây."
            return ""
        if self._max_rms < 100:
            self.error = "Không thấy tiếng từ microphone. Hãy kiểm tra đầu vào âm thanh rồi ghi lại."
            return ""
        return path

    def cancel(self) -> str:
        path = self._path
        self._close_capture()
        self._path = ""
        return path

    def _close_capture(self) -> None:
        source, self._source = self._source, None
        self._stream = None
        self._capture_format = None
        self._pending_pcm = b""
        if source is not None:
            source.stop()
            source.deleteLater()
        if self._wave is not None:
            self._wave.close()
            self._wave = None
