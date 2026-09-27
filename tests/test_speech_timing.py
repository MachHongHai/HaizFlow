import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.pipeline.speech_timing import voiced_subtitle_segments, fitted_speech_duration_ms
from haizflow.pipeline.sequence_compiler import write_subtitles
from haizflow.schemas.editor import EditorDocument, EditorTrack, EditorClip, EditorAsset


class SpeechTimingTests(unittest.TestCase):
    def test_short_voice_leaves_pause_without_mutating_editable_timing(self):
        segments = [{"start": 1, "end": 5.69, "text": "Câu thứ nhất"},
                    {"start": 7, "end": 12.65, "text": "Câu thứ hai"}]
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "voice.wav"
            audio.touch()
            with patch("haizflow.pipeline.speech_timing._trimmed_duration", side_effect=[1930, 2600]):
                result = voiced_subtitle_segments(segments, [str(audio), str(audio)])
        self.assertAlmostEqual(result[0]["end"], 2.93)
        self.assertAlmostEqual(result[1]["end"], 9.60)
        self.assertEqual(segments[0]["end"], 5.69)
        self.assertEqual(result[1]["start"], 7)

    def test_overrun_uses_same_safety_margin_as_audio_export(self):
        self.assertEqual(fitted_speech_duration_ms(3610, 2630), 2610)
        self.assertEqual(fitted_speech_duration_ms(1930, 4690), 1930)
        self.assertEqual(fitted_speech_duration_ms(2630, 2630), 2630)

    def test_no_voice_preserves_source_caption_timing(self):
        segments = [{"start": 1, "end": 5, "text": "Test"}]
        self.assertEqual(voiced_subtitle_segments(segments, [""]), segments)

    def test_export_follows_voice_but_muted_voice_preserves_source_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "voice.wav"
            audio.touch()
            document = EditorDocument(video_id="test", tracks=[
                EditorTrack(track_id="subtitles", kind="subtitle", name="Subtitles"),
                EditorTrack(track_id="voice", kind="voice", name="Voice")],
                clips=[EditorClip(clip_id="s", track_id="subtitles", kind="subtitle",
                                  segment_id="1", name="Test", start_ms=1000, duration_ms=4690),
                       EditorClip(clip_id="v", track_id="voice", kind="voice",
                                  segment_id="1", name="Test", asset_id="a", start_ms=1000,
                                  duration_ms=4690)],
                assets=[EditorAsset(asset_id="a", kind="audio", path=str(audio))])
            output = Path(folder) / "captions.srt"
            with patch("haizflow.pipeline.speech_timing._trimmed_duration", return_value=1930):
                self.assertTrue(write_subtitles(document, output))
                self.assertIn("00:00:01,000 --> 00:00:02,930", output.read_text())
                document.tracks[1].muted = True
                write_subtitles(document, output)
                self.assertIn("00:00:01,000 --> 00:00:05,690", output.read_text())
            self.assertEqual(document.clips[0].duration_ms, 4690)
