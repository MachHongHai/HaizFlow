import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from haizflow.pipeline import audio_timeline


class AudioTimelineIntegrityTests(unittest.TestCase):
    def _segments_file(self, root: Path) -> Path:
        path = root / "segments.json"
        path.write_text(json.dumps([{"start": 0, "end": 1, "text": "hello"}]), encoding="utf-8")
        return path

    def test_missing_required_voice_segment_fails_the_timeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(audio_timeline, "get_video_duration", return_value=2.0),
                mock.patch.object(audio_timeline, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Missing or empty generated voice segment 1"):
                    audio_timeline.build_audio_timeline(
                        str(self._segments_file(root)),
                        str(root / "voices"),
                        str(root / "input.mp4"),
                        str(root / "output.wav"),
                        "video-1",
                    )

    def test_missing_required_background_track_fails_the_timeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(audio_timeline, "get_video_duration", return_value=2.0),
                mock.patch.object(audio_timeline, "log_to_video"),
            ):
                with self.assertRaisesRegex(FileNotFoundError, "Required original/background audio track is missing"):
                    audio_timeline.build_audio_timeline(
                        str(self._segments_file(root)),
                        str(root / "voices"),
                        str(root / "input.mp4"),
                        str(root / "output.wav"),
                        "video-1",
                        background_audio_path=str(root / "missing-background.wav"),
                    )


if __name__ == "__main__":
    unittest.main()
