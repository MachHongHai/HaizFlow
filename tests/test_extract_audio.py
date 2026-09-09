import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import extract_audio as extract_audio_module


class ExtractAudioTests(unittest.TestCase):
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
