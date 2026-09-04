import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydub import AudioSegment

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

    def test_unknown_video_duration_is_not_replaced_with_fake_one_second_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(audio_timeline, "get_video_duration", return_value=0.0),
                mock.patch.object(audio_timeline, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "positive source-video duration"):
                    audio_timeline.build_audio_timeline(
                        str(self._segments_file(root)),
                        str(root / "voices"),
                        str(root / "input.mp4"),
                        str(root / "output.wav"),
                        "video-1",
                    )

    def test_empty_transcript_cannot_create_a_background_only_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            segments = root / "segments.json"
            segments.write_text("[]", encoding="utf-8")
            with (
                mock.patch.object(audio_timeline, "get_video_duration", return_value=2.0),
                mock.patch.object(audio_timeline, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "at least one translated voice"):
                    audio_timeline.build_audio_timeline(
                        str(segments),
                        str(root / "voices"),
                        str(root / "input.mp4"),
                        str(root / "output.wav"),
                        "video-1",
                    )

    def test_manual_compositor_can_create_a_mix_without_tts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            segments = root / "segments.json"
            output = root / "output.wav"
            segments.write_text("[]", encoding="utf-8")
            with (
                mock.patch.object(audio_timeline, "get_video_duration", return_value=0.25),
                mock.patch.object(audio_timeline, "log_to_video"),
                mock.patch.object(audio_timeline, "check_cancellation"),
            ):
                audio_timeline.build_audio_timeline(
                    str(segments),
                    str(root / "voices"),
                    str(root / "input.mp4"),
                    str(output),
                    "video-1",
                    require_voice_parts=False,
                )

            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 44)

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

    def test_background_music_is_looped_to_the_video_duration(self):
        music = AudioSegment.silent(duration=300, frame_rate=16000)

        looped = audio_timeline._fit_to_duration(music, 1000)

        self.assertEqual(len(looped), 1000)

    def test_zero_volume_mutes_a_track_without_affecting_other_mix_inputs(self):
        tone = AudioSegment.silent(duration=100, frame_rate=16000)
        with mock.patch.object(audio_timeline, "log_to_video"):
            muted = audio_timeline._apply_volume(tone, 0, "Background music", "video-1")

        self.assertEqual(muted.rms, 0)

    def test_tempo_rounding_tail_is_trimmed_to_the_exact_slot(self):
        audio = AudioSegment.silent(duration=1002, frame_rate=16000)

        fitted = audio_timeline._trim_tempo_rounding(audio, 1000)

        self.assertEqual(len(fitted), 1000)

    def test_large_tempo_mismatch_is_not_silently_truncated(self):
        audio = AudioSegment.silent(duration=1100, frame_rate=16000)

        with self.assertRaisesRegex(RuntimeError, "exceeding its 1000ms slot by 100ms"):
            audio_timeline._trim_tempo_rounding(audio, 1000)

    def test_tempo_chain_supports_slowing_an_edited_subtitle_slot(self):
        self.assertEqual(
            audio_timeline._atempo_filters(0.25),
            "atempo=0.5,atempo=0.500000",
        )

    def test_atomic_audio_replace_retries_a_transient_windows_media_lock(self):
        locked = PermissionError(5, "Access is denied")
        with (
            mock.patch.object(audio_timeline.os, "replace", side_effect=[locked, locked, None]) as replace,
            mock.patch.object(audio_timeline.time, "sleep") as sleep,
        ):
            audio_timeline._replace_exported_audio("new.wav", "voice_final.wav")

        self.assertEqual(replace.call_count, 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
