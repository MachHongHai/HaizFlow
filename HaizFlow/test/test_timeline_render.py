import tempfile
import unittest
from pathlib import Path
from unittest import mock

from haizflow.pipeline.audio_timeline import _segment_slot_end_ms
from haizflow.pipeline import render
from haizflow.schemas.video import CropSettings, SubtitleStyle


class TimelineRenderTests(unittest.TestCase):
    def test_render_rejects_unknown_output_format_before_invoking_ffmpeg(self):
        with self.assertRaisesRegex(ValueError, "Unsupported output format"):
            render.render_video(
                "input.mp4",
                "voice.wav",
                "subtitle.srt",
                "output.mp4",
                "unknown-layout",
                SubtitleStyle(),
                CropSettings(),
                "video-1",
            )

    def test_only_last_voice_slot_keeps_a_small_tail_margin(self):
        self.assertEqual(
            _segment_slot_end_ms(1000, 3000, 5000, is_last=False),
            3000,
        )
        self.assertEqual(
            _segment_slot_end_ms(3000, 5000, 5000, is_last=True),
            4880,
        )

    def test_very_short_final_slot_is_not_overcompressed_for_margin(self):
        self.assertEqual(
            _segment_slot_end_ms(4800, 5000, 5000, is_last=True),
            5000,
        )

    def test_render_is_limited_by_source_duration_instead_of_shortest_stream(self):
        captured = {}

        class FakeProcess:
            returncode = 0

            def __init__(self, command, **kwargs):
                captured["command"] = command
                (Path(kwargs["cwd"]) / command[-1]).resolve().write_bytes(b"rendered-video")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subtitle_path = root / "subtitles.srt"
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            (root / "input.mp4").write_bytes(b"source")
            (root / "voice.wav").write_bytes(b"R" * 100)
            with (
                mock.patch.object(render, "get_video_dimensions", return_value=(1920, 1080)),
                mock.patch.object(render, "get_video_duration", return_value=5.0),
                mock.patch.object(render, "get_media_stream_types", return_value={"video", "audio"}),
                mock.patch.object(render, "preferred_video_encoder", return_value=("libx264", ["-preset", "fast"])),
                mock.patch.object(render.subprocess, "Popen", FakeProcess),
                mock.patch.object(render, "communicate_process", return_value=("", "")),
                mock.patch.object(render, "check_cancellation"),
                mock.patch.object(render, "log_to_video"),
            ):
                render.render_video(
                    str(root / "input.mp4"),
                    str(root / "voice.wav"),
                    str(subtitle_path),
                    str(root / "output.mp4"),
                    "keep_ratio",
                    SubtitleStyle(),
                    CropSettings(),
                    "video-id",
                )

        command = captured["command"]
        self.assertNotIn("-shortest", command)
        self.assertEqual(command[command.index("-t") + 1], "5.000000")

    def test_render_does_not_replace_a_previous_export_when_output_is_invalid(self):
        class FakeProcess:
            returncode = 0

            def __init__(self, command, **kwargs):
                (Path(kwargs["cwd"]) / command[-1]).resolve().write_bytes(b"invalid")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.mp4"
            voice_path = root / "voice.wav"
            subtitle_path = root / "subtitles.srt"
            output_path = root / "output.mp4"
            input_path.write_bytes(b"source")
            voice_path.write_bytes(b"R" * 100)
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            output_path.write_bytes(b"previous-good-export")
            with (
                mock.patch.object(render, "get_video_dimensions", return_value=(1920, 1080)),
                mock.patch.object(render, "get_video_duration", return_value=5.0),
                mock.patch.object(render, "get_media_stream_types", return_value={"video"}),
                mock.patch.object(render, "preferred_video_encoder", return_value=("libx264", [])),
                mock.patch.object(render.subprocess, "Popen", FakeProcess),
                mock.patch.object(render, "communicate_process", return_value=("", "")),
                mock.patch.object(render, "check_cancellation"),
                mock.patch.object(render, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "missing its video or dubbed-audio"):
                    render.render_video(
                        str(input_path),
                        str(voice_path),
                        str(subtitle_path),
                        str(output_path),
                        "keep_ratio",
                        SubtitleStyle(),
                        CropSettings(),
                        "video-id",
                    )
            output_bytes = output_path.read_bytes()
            partial_outputs = list(root.glob(".render-*"))

        self.assertEqual(output_bytes, b"previous-good-export")
        self.assertEqual(partial_outputs, [])

    def test_render_blurs_detected_region_and_places_new_subtitles_there(self):
        captured = {}

        class FakeProcess:
            returncode = 0

            def __init__(self, command, **kwargs):
                captured["command"] = command
                (Path(kwargs["cwd"]) / command[-1]).resolve().write_bytes(b"rendered-video")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "input.mp4").write_bytes(b"source")
            (root / "voice.wav").write_bytes(b"R" * 100)
            subtitle_path = root / "subtitles.srt"
            subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            with (
                mock.patch.object(render, "get_video_dimensions", return_value=(1920, 1080)),
                mock.patch.object(render, "get_video_duration", return_value=5.0),
                mock.patch.object(render, "get_media_stream_types", return_value={"video", "audio"}),
                mock.patch.object(render, "preferred_video_encoder", return_value=("libx264", [])),
                mock.patch.object(render.subprocess, "Popen", FakeProcess),
                mock.patch.object(render, "communicate_process", return_value=("", "")),
                mock.patch.object(render, "check_cancellation"),
                mock.patch.object(render, "log_to_video"),
            ):
                render.render_video(
                    str(root / "input.mp4"), str(root / "voice.wav"), str(subtitle_path),
                    str(root / "output.mp4"), "keep_ratio", SubtitleStyle(), CropSettings(), "video-id",
                    {"x_percent": 20, "y_percent": 78, "width_percent": 60, "height_percent": 7},
                )
            ass_text = (root / "positioned_subtitles.ass").read_text(encoding="utf-8-sig")

        command = captured["command"]
        self.assertIn("-filter_complex", command)
        self.assertIn("boxblur=18:4", command[command.index("-filter_complex") + 1])
        self.assertIn("\\an5\\pos(960,886)\\fs", ass_text)
        self.assertIn("\\fscx", ass_text)
        self.assertIn(",1,5,0,0,40,1", ass_text)
        self.assertIn("\\pos(960,886)", ass_text)

    def test_long_region_cue_is_shown_as_sequential_single_line_phrases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subtitle_path = root / "subtitles.srt"
            ass_path = root / "positioned_subtitles.ass"
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:03,000\n"
                "This translation is deliberately long enough to need several readable phrases\n",
                encoding="utf-8",
            )
            render._write_positioned_ass(
                str(subtitle_path),
                str(ass_path),
                SubtitleStyle(font_size=36),
                608,
                1080,
                render.SubtitleRegionLayout(150, 780, 300, 72),
            )
            dialogue_lines = [
                line for line in ass_path.read_text(encoding="utf-8-sig").splitlines()
                if line.startswith("Dialogue:")
            ]

        self.assertGreater(len(dialogue_lines), 1)
        self.assertTrue(all("\\N" not in line for line in dialogue_lines))
        self.assertTrue(all("\\fs" in line for line in dialogue_lines))
        font_sizes = [
            int(line.split("\\fs", 1)[1].split("\\", 1)[0].split("}", 1)[0])
            for line in dialogue_lines
        ]
        self.assertTrue(all(font_size >= 30 for font_size in font_sizes))


if __name__ == "__main__":
    unittest.main()
