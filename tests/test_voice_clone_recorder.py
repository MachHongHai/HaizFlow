import array
import tempfile
import unittest
import wave
from enum import Enum
from pathlib import Path
from unittest.mock import patch

from PySide6.QtMultimedia import QAudioFormat

from haizflow.desktop.voice_clone_recorder import VoiceCloneRecorder


class VoiceCloneRecorderTests(unittest.TestCase):
    def test_source_no_error_from_distinct_qt_enum_is_accepted(self):
        class SourceError(Enum):
            NoError = 0

        class FakeDevice:
            def isNull(self):
                return False

            def preferredFormat(self):
                result = QAudioFormat()
                result.setSampleRate(48_000)
                result.setChannelCount(2)
                result.setSampleFormat(QAudioFormat.SampleFormat.Float)
                return result

            def isFormatSupported(self, _audio_format):
                return False

        class FakeSource:
            def __init__(self, _device, _audio_format):
                pass

            def start(self):
                return object()

            def error(self):
                return SourceError.NoError

            def stop(self):
                pass

            def deleteLater(self):
                pass

        with tempfile.TemporaryDirectory() as temporary:
            recorder = VoiceCloneRecorder()
            with (
                patch("haizflow.desktop.voice_clone_recorder.QMediaDevices.defaultAudioInput", return_value=FakeDevice()),
                patch("haizflow.desktop.voice_clone_recorder.QAudioSource", FakeSource),
            ):
                self.assertTrue(recorder.start(str(Path(temporary) / "sample.wav")))
            recorder.cancel()

    def test_native_float_stereo_is_downmixed_for_voice_reference(self):
        recorder = VoiceCloneRecorder()
        capture_format = QAudioFormat()
        capture_format.setSampleRate(48_000)
        capture_format.setChannelCount(2)
        capture_format.setSampleFormat(QAudioFormat.SampleFormat.Float)
        recorder._capture_format = capture_format
        pcm = recorder._mono_int16(array.array("f", [0.5, 0.5, -0.5, -0.5]).tobytes())
        samples = array.array("h")
        samples.frombytes(pcm)
        self.assertEqual(len(samples), 2)
        self.assertGreater(samples[0], 16_000)
        self.assertLess(samples[1], -16_000)

    def test_pcm_capture_produces_valid_wave_and_real_levels(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.wav"
            recorder = VoiceCloneRecorder()
            recorder._path = str(path)
            recorder._sample_rate = 16_000
            recorder._wave = wave.open(str(path), "wb")
            recorder._wave.setnchannels(1)
            recorder._wave.setsampwidth(2)
            recorder._wave.setframerate(16_000)

            recorder._consume_pcm(array.array("h", [0] * 8_000).tobytes())
            quiet = recorder.poll()["peaks"][-1]
            recorder._consume_pcm(array.array("h", [12_000] * 8_000).tobytes())
            loud = recorder.poll()["peaks"][-1]
            saved = recorder.stop()

            self.assertEqual(saved, str(path))
            self.assertLess(quiet, loud)
            with wave.open(str(path), "rb") as sample:
                self.assertEqual(sample.getnchannels(), 1)
                self.assertEqual(sample.getframerate(), 16_000)
                self.assertEqual(sample.getnframes(), 16_000)

    def test_short_capture_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "short.wav"
            recorder = VoiceCloneRecorder()
            recorder._path = str(path)
            recorder._sample_rate = 16_000
            recorder._wave = wave.open(str(path), "wb")
            recorder._wave.setnchannels(1)
            recorder._wave.setsampwidth(2)
            recorder._wave.setframerate(16_000)
            recorder._consume_pcm(array.array("h", [100] * 1_000).tobytes())

            self.assertEqual(recorder.stop(), "")
            self.assertIn("quá ngắn", recorder.error)

    def test_silent_capture_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "silent.wav"
            recorder = VoiceCloneRecorder()
            recorder._path = str(path)
            recorder._sample_rate = 16_000
            recorder._wave = wave.open(str(path), "wb")
            recorder._wave.setnchannels(1)
            recorder._wave.setsampwidth(2)
            recorder._wave.setframerate(16_000)
            recorder._consume_pcm(array.array("h", [0] * 16_000).tobytes())

            self.assertEqual(recorder.stop(), "")
            self.assertIn("Không thấy tiếng", recorder.error)


if __name__ == "__main__":
    unittest.main()
