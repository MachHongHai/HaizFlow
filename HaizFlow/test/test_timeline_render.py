import tempfile
import unittest
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from haizflow.pipeline.audio_timeline import _segment_slot_end_ms
from haizflow.pipeline import render
from haizflow.schemas.video import CropSettings, SubtitleStyle


class TimelineRenderTests(unittest.TestCase):
    def test_ffmpeg_progress_uses_rendered_timestamp(self):
        self.assertAlmostEqual(
            render._ffmpeg_progress_fraction("out_time_us=2500000\nprogress=continue\n", 10.0),
            0.25,
        )
        self.assertEqual(
            render._ffmpeg_progress_fraction("out_time=00:00:15.000000\n", 10.0),
            1.0,
        )
        self.assertIsNone(render._ffmpeg_progress_fraction("progress=continue\n", 10.0))

    def test_default_subtitle_size_is_legible_without_an_ocr_region(self):
        self.assertEqual(SubtitleStyle().font_size, 60)

    def test_fallback_subtitles_are_large_sequential_single_line_phrases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subtitle_path = root / "subtitles.srt"
            ass_path = root / "positioned_subtitles.ass"
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:03,000\n"
                "This fallback caption is deliberately long enough to need multiple readable phrases\n\n"
                "2\n00:00:03,000 --> 00:00:06,000\n"
                "A second long fallback caption must retain exactly the same font size\n",
                encoding="utf-8",
            )
            style = SubtitleStyle()
            layout = render._default_subtitle_layout(style, 1080, 1920)
            render._write_positioned_ass(
                str(subtitle_path), str(ass_path), style, 1080, 1920, layout,
                fixed_font_size=True,
            )
            dialogue_lines = [
                line for line in ass_path.read_text(encoding="utf-8-sig").splitlines()
                if line.startswith("Dialogue:")
            ]

        self.assertGreater(len(dialogue_lines), 1)
        self.assertTrue(all("\\N" not in line for line in dialogue_lines))
        self.assertTrue(all("\\fs60" in line for line in dialogue_lines))

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

    def test_voice_slot_ends_with_the_original_spoken_segment(self):
        self.assertEqual(
            _segment_slot_end_ms(1000, 2200, 3000, 5000, is_last=False),
            2200,
        )
        self.assertEqual(
            _segment_slot_end_ms(3000, 4100, 5000, 5000, is_last=True),
            4100,
        )

    def test_voice_slot_never_crosses_the_next_segment(self):
        self.assertEqual(
            _segment_slot_end_ms(1000, 3500, 3000, 5000, is_last=False),
            3000,
        )

    def test_invalid_legacy_end_uses_safe_fallback_boundary(self):
        self.assertEqual(
            _segment_slot_end_ms(1000, 1000, 3000, 5000, is_last=False),
            3000,
        )
        self.assertEqual(
            _segment_slot_end_ms(3000, 0, 5000, 5000, is_last=True),
            4880,
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

    def test_editor_proxy_render_seeks_and_limits_the_source_range(self):
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
                mock.patch.object(render, "get_video_duration", return_value=30.0),
                mock.patch.object(render, "get_media_stream_types", return_value={"video", "audio"}),
                mock.patch.object(render, "preferred_video_encoder", return_value=("libx264", [])),
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
                    "editor-preview",
                    watermark_text="HaizFlow",
                    source_start_seconds=12.5,
                    source_duration_seconds=3.25,
                    compatibility_preview=True,
                )

        command = captured["command"]
        self.assertEqual(command[command.index("-ss") + 1], "12.500000")
        self.assertEqual(command[command.index("-t") + 1], "3.250000")
        filter_graph = command[command.index("-vf") + 1]
        self.assertIn("(t+12.500000)", filter_graph)
        self.assertIn("format=yuv420p", filter_graph)
        self.assertIn("libx264", command)
        self.assertEqual(command[command.index("-color_range") + 1], "tv")
        self.assertEqual(command[command.index("-colorspace") + 1], "bt709")

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
                    "HaizFlow",
                    original_subtitle_removal_mode="blur",
                )
            ass_text = (root / "positioned_subtitles.ass").read_text(encoding="utf-8-sig")

        command = captured["command"]
        self.assertIn("-filter_complex", command)
        filter_graph = command[command.index("-filter_complex") + 1]
        self.assertIn("crop=1152:76:384:842[original_region]", filter_graph)
        self.assertIn("gblur=sigma=14:steps=4,crop=1152:76:42:42", filter_graph)
        self.assertIn("0.94+0.06*min(1", filter_graph)
        self.assertIn("overlay=384:842", command[command.index("-filter_complex") + 1])
        self.assertNotIn("between(t", command[command.index("-filter_complex") + 1])
        self.assertIn("drawtext=fontfile=", command[command.index("-filter_complex") + 1])
        self.assertIn("text='HaizFlow'", command[command.index("-filter_complex") + 1])
        self.assertIn("fontsdir=", command[command.index("-filter_complex") + 1])
        self.assertIn("\\an5\\pos(960,886)\\fs", ass_text)
        self.assertIn("\\fscx100", ass_text)
        self.assertIn("Style: Default,Bangers,", ass_text)
        self.assertIn("&H0000EFFF,&H00FFFFFF", ass_text)
        self.assertIn("\\shad2", ass_text)
        self.assertIn("{\\kf", ass_text)
        self.assertIn("\\pos(960,886)", ass_text)

    def test_manual_subtitle_layout_does_not_disable_original_subtitle_blur(self):
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
            style = SubtitleStyle(font_size=74, position_x_percent=50, position_y_percent=94)
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
                    str(root / "output.mp4"), "keep_ratio", style, CropSettings(), "video-id",
                    {"x_percent": 20, "y_percent": 78, "width_percent": 60, "height_percent": 7},
                    subtitle_layout_override=True,
                    original_subtitle_removal_mode="blur",
                )

        command = captured["command"]
        filter_graph = command[command.index("-filter_complex") + 1]
        self.assertIn("crop=1152:76:384:842", filter_graph)
        self.assertIn("overlay=384:842", filter_graph)

    def test_ocr_cover_mode_ignores_a_stale_manual_subtitle_layout(self):
        from haizflow.pipeline.process_video import _manual_subtitle_layout_for_render

        stale_video = SimpleNamespace(
            remove_original_subtitles=True,
            subtitle_layout_override=True,
        )
        manual_video = SimpleNamespace(
            remove_original_subtitles=False,
            subtitle_layout_override=True,
        )

        self.assertFalse(_manual_subtitle_layout_for_render(stale_video))
        self.assertTrue(_manual_subtitle_layout_for_render(manual_video))

    def test_bundled_karaoke_font_is_available_to_ffmpeg(self):
        font_directory = render._karaoke_font_directory()

        self.assertTrue((font_directory / render.KARAOKE_FONT_FILENAME).is_file())
        self.assertGreater(
            (font_directory / render.KARAOKE_FONT_FILENAME).stat().st_size,
            50_000,
        )

    def test_subtitle_blur_radius_fits_a_short_detected_region(self):
        blur_filter = render._subtitle_blur_filter(398, 64)

        self.assertEqual(
            blur_filter,
            "gblur=sigma=12:steps=4",
        )

    def test_text_watermark_uses_a_bold_italic_social_video_treatment(self):
        watermark = render._watermark_filter("HaizFlow: creator's cut", 1080, 1920)

        self.assertIn("drawtext=fontfile='", watermark)
        self.assertIn("text='HaizFlow\\: creator\\'s cut'", watermark)
        self.assertIn("fontsize=31", watermark)
        self.assertIn("fontcolor=white@0.46", watermark)
        self.assertIn("borderw=2", watermark)
        self.assertIn("bordercolor=black@0.48", watermark)
        self.assertIn("shadowx=1:shadowy=1:shadowcolor=black@0.22", watermark)
        self.assertIn("sin(2*PI*t/31)", watermark)
        self.assertIn("sin(2*PI*t/43+1.2)", watermark)

    def test_watermark_font_has_a_safe_bundled_fallback(self):
        fallback = render._karaoke_font_directory() / render.KARAOKE_FONT_FILENAME

        with mock.patch.dict(render.os.environ, {"WINDIR": r"Z:\\missing-windows"}):
            self.assertEqual(render._watermark_font_path(), fallback)

    def test_empty_watermark_adds_no_filter(self):
        self.assertEqual(render._watermark_filter("   ", 1080, 1920), "")

    def test_subtitle_blur_radius_fits_the_smallest_supported_region(self):
        blur_filter = render._subtitle_blur_filter(40, 2)

        self.assertEqual(
            blur_filter,
            "gblur=sigma=3:steps=4",
        )

    def test_subtitle_blur_uses_one_exact_static_box(self):
        filter_prefix = render._subtitle_blur_prefix(
            (78, 562, 418, 54), 576, 1024,
        )

        self.assertIn("crop=418:54:78:562", filter_prefix)
        self.assertIn("overlay=78:562", filter_prefix)
        self.assertIn("crop=478:114:48:532,gblur=sigma=10:steps=4,crop=418:54:30:30", filter_prefix)
        self.assertIn("0.94+0.06*min(1", filter_prefix)
        self.assertNotIn("between(t", filter_prefix)
        self.assertNotIn("drawbox", filter_prefix)

    def test_removal_region_preserves_the_detected_bottom_edge_when_even_aligned(self):
        region = {
            "x_percent": 9.44,
            "y_percent": 84.9,
            "width_percent": 79.31,
            "height_percent": 8.42,
        }

        result = render._source_subtitle_removal_region(region, 1280, 720)

        # work4's OCR interval ends at 671.904px. The old origin+height
        # flooring ended at 670px; exact edge quantization reaches 672px.
        self.assertEqual(result, (120, 610, 1016, 62))

    def test_subtitle_patch_copies_real_pixels_from_an_adjacent_strip(self):
        filter_prefix = render._subtitle_patch_prefix(
            (78, 562, 418, 54), 576, 1024,
        )

        self.assertEqual(
            filter_prefix,
            "[0:v]split=2[source_clean][source_patch];"
            "[source_patch]crop=418:54:78:504,format=rgba,"
            "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            "a='255*min(1,min(min(X,W-1-X),min(Y,H-1-Y))/3)'[subtitle_patch];"
            "[source_clean][subtitle_patch]overlay=78:562[source_without_original];",
        )
        self.assertNotIn("gblur", filter_prefix)
        self.assertNotIn("delogo", filter_prefix)

    def test_subtitle_removal_mode_defaults_to_existing_blur(self):
        region = (78, 562, 418, 54)

        self.assertIn(
            "gblur=",
            render._original_subtitle_removal_prefix(region, 576, 1024, "unknown"),
        )
        self.assertIn(
            "[source_patch]crop=",
            render._original_subtitle_removal_prefix(region, 576, 1024, "patch"),
        )

    def test_subtitle_patch_uses_the_available_side_near_frame_edges(self):
        self.assertEqual(
            render._subtitle_patch_source_y((40, 20, 300, 80), 1024),
            106,
        )
        self.assertEqual(
            render._subtitle_patch_source_y((40, 900, 300, 80), 1024),
            814,
        )

    def test_subtitle_patch_falls_back_to_blur_when_no_clean_strip_fits(self):
        filter_prefix = render._subtitle_patch_prefix(
            (20, 40, 300, 160), 576, 220,
        )

        self.assertIn("gblur=", filter_prefix)

    def test_removal_region_does_not_change_vertical_caption_preset(self):
        region = {
            "x_percent": 14,
            "y_percent": 53,
            "width_percent": 72,
            "height_percent": 15,
            "line_height_percent": 5.8,
        }
        layout = render._output_subtitle_region_layout(
            region, 576, 1024, "keep_ratio", CropSettings(), 576, 1024,
        )
        style = render._style_for_original_subtitle_region(
            SubtitleStyle(font_size=36), layout, 576, 1024,
        )

        self.assertIsNotNone(layout)
        self.assertAlmostEqual(layout.height, 153.6)
        self.assertAlmostEqual(layout.line_height, 59.392)
        self.assertEqual(style.font_size, 39)

        much_taller_layout = render.SubtitleRegionLayout(20, 400, 530, 300, 120)
        much_taller_style = render._style_for_original_subtitle_region(
            SubtitleStyle(font_size=20), much_taller_layout, 576, 1024,
        )
        self.assertEqual(much_taller_style.font_size, 39)

    def test_common_video_formats_use_stable_caption_presets(self):
        style = SubtitleStyle(font_size=12)

        vertical = render._style_for_original_subtitle_region(style, None, 1080, 1920)
        landscape = render._style_for_original_subtitle_region(style, None, 1920, 1080)
        square = render._style_for_original_subtitle_region(style, None, 1080, 1080)

        self.assertEqual(vertical.font_size, 74)
        self.assertEqual(landscape.font_size, 64)
        self.assertEqual(square.font_size, 66)

    def test_manual_subtitle_frame_maps_position_and_size_to_output(self):
        style = SubtitleStyle(
            font_size=72,
            position_x_percent=30,
            position_y_percent=40,
            box_width_percent=50,
            box_height_percent=12,
        )

        layout = render._manual_subtitle_layout(style, 1080, 1920)

        self.assertEqual(layout.width, 540)
        self.assertEqual(layout.height, 230.4)
        self.assertEqual(layout.x, 54)
        self.assertAlmostEqual(layout.y, 652.8)

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
                fixed_font_size=True,
            )
            dialogue_lines = [
                line for line in ass_path.read_text(encoding="utf-8-sig").splitlines()
                if line.startswith("Dialogue:")
            ]

        self.assertGreater(len(dialogue_lines), 1)
        self.assertTrue(all("\\N" not in line for line in dialogue_lines))
        self.assertTrue(all("\\fs" in line for line in dialogue_lines))
        self.assertTrue(all("\\fscx100" in line for line in dialogue_lines))
        rendered_phrases = [
            line.split("}", 1)[1].split()
            for line in dialogue_lines
        ]
        self.assertTrue(all(len(words) >= 2 for words in rendered_phrases))
        font_sizes = [
            int(line.split("\\fs", 1)[1].split("\\", 1)[0].split("}", 1)[0])
            for line in dialogue_lines
        ]
        self.assertTrue(all(font_size == 36 for font_size in font_sizes))
        self.assertEqual(len(set(font_sizes)), 1)

    def test_contiguous_sentence_fragments_are_joined_before_phrase_splitting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subtitle_path = root / "subtitles.srt"
            ass_path = root / "positioned_subtitles.ass"
            subtitle_path.write_text(
                "1\n00:00:04,481 --> 00:00:05,570\n"
                "Vậy tôi nên đi đến nơi này như\n\n"
                "2\n00:00:05,570 --> 00:00:05,861\n"
                "thế nào?\n",
                encoding="utf-8",
            )
            render._write_positioned_ass(
                str(subtitle_path),
                str(ass_path),
                SubtitleStyle(font_size=45),
                576,
                1024,
                render.SubtitleRegionLayout(78, 550, 418, 116, 59),
            )
            dialogue_lines = [
                line for line in ass_path.read_text(encoding="utf-8-sig").splitlines()
                if line.startswith("Dialogue:")
            ]
            rendered_text = [re.sub(r"\{[^}]*\}", "", line.split(",,", 1)[1]) for line in dialogue_lines]

        self.assertNotIn("thế nào?", rendered_text)
        self.assertTrue(any("thế nào?" in phrase and len(phrase.split()) >= 4 for phrase in rendered_text))

    def test_karaoke_sweeps_from_white_to_gold_and_uses_the_full_duration(self):
        rendered = render._karaoke_ass_text("xin chào bạn", 1.37)
        durations = [int(value) for value in re.findall(r"\\kf(\d+)", rendered)]

        self.assertEqual(len(durations), 3)
        self.assertEqual(sum(durations), 137)
        self.assertIn("xin ", rendered)
        self.assertTrue(rendered.endswith("bạn"))

    def test_no_space_language_is_split_into_balanced_character_phrases(self):
        parts = render._split_subtitle_words("这是一个没有空格的长字幕句子", 6)

        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), "这是一个没有空格的长字幕句子")
        self.assertLessEqual(max(map(len, parts)) - min(map(len, parts)), 1)


if __name__ == "__main__":
    unittest.main()
