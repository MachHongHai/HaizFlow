import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import extract_audio as extract_audio_module


class ExtractAudioTests(unittest.TestCase):
    def test_extraction_requests_stereo_48khz_24bit_master(self):
        process = mock.Mock(returncode=0)
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(extract_audio_module, "get_media_stream_types", return_value={"video", "audio"}),
            mock.patch.object(extract_audio_module, "log_to_video"),
            mock.patch.object(extract_audio_module.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(extract_audio_module, "communicate_process", return_value=("", "")),
            mock.patch.object(extract_audio_module.os.path, "getsize", return_value=100),
        ):
            extract_audio_module.extract_audio("video.mp4", str(Path(temporary) / "audio.wav"), "v")
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("-ar") + 1], "48000")
        self.assertEqual(args[args.index("-ac") + 1], "2")
        self.assertEqual(args[args.index("-c:a") + 1], "pcm_s24le")

    def test_video_without_audio_fails_before_ffmpeg_with_actionable_message(self):
        with (
            mock.patch.object(extract_audio_module, "get_media_stream_types", return_value={"video"}),
            mock.patch.object(extract_audio_module, "log_to_video"),
            mock.patch.object(extract_audio_module.subprocess, "Popen") as popen,
            self.assertRaisesRegex(RuntimeError, "source video has no audio track"),
        ):
            extract_audio_module.extract_audio("video.mp4", "audio.wav", "video-id")

        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
