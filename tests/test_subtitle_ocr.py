import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from haizflow.pipeline import subtitle_ocr
from haizflow.pipeline.subtitle_ocr import (
    TextCandidate,
    _ocr_candidates,
    select_subtitle_region,
)


def candidate(frame, text, *, x=25, y=78, width=50, height=5, confidence=0.9):
    return TextCandidate(frame, x, y, width, height, text, confidence)


class SubtitleOcrSelectionTests(unittest.TestCase):
    def test_detector_downscales_frames_and_reports_scan_progress(self):
        captured = {}

        class FakeProcess:
            returncode = 0

            def __init__(self, command, **_kwargs):
                captured["command"] = command
                pattern = command[-1]
                count = int(command[command.index("-frames:v") + 1])
                for index in range(1, count + 1):
                    Path(pattern.replace("%03d", f"{index:03d}")).write_bytes(b"frame")

        updates = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "input.mp4"
            video_path.write_bytes(b"source")
            with (
                patch.object(subtitle_ocr, "get_video_duration", return_value=10.0),
                patch.object(subtitle_ocr, "get_video_dimensions", return_value=(1080, 1920)),
                patch.object(subtitle_ocr.subprocess, "Popen", FakeProcess),
                patch.object(subtitle_ocr, "communicate_process", return_value=("", "")),
                patch.object(subtitle_ocr, "check_cancellation"),
                patch.object(subtitle_ocr, "_ocr_candidates", return_value=[]),
                patch.object(subtitle_ocr, "log_to_video"),
            ):
                result = subtitle_ocr.detect_original_subtitle_region(
                    str(video_path),
                    str(root / "temp"),
                    "video-id",
                    lambda current, total: updates.append((current, total)),
                )

        command = captured["command"]
        self.assertIsNone(result)
        self.assertIn("fps=3.60000000,scale=720:1280", command)
        self.assertEqual(command[command.index("-frames:v") + 1], "36")
        self.assertEqual(updates[0], (0, 36))
        self.assertEqual(updates[-1], (36, 36))

    def test_selects_repeated_lower_subtitles_with_changing_text(self):
        region = select_subtitle_region([
            candidate(1, "first caption"),
            candidate(2, "second caption", x=27, width=46),
            candidate(3, "third caption", x=24, width=52),
            candidate(4, "fourth caption"),
        ], sample_count=12)

        self.assertIsNotNone(region)
        self.assertGreaterEqual(region["y_percent"], 70)
        self.assertLessEqual(region["y_percent"] + region["height_percent"], 100)
        self.assertEqual(region["samples"], 4)

    def test_region_covers_the_widest_observed_caption_not_its_median_width(self):
        region = select_subtitle_region([
            candidate(1, "short line", x=32, width=28),
            candidate(2, "a much longer subtitle line", x=18, width=58),
            candidate(3, "another long subtitle line", x=20, width=55),
            candidate(4, "medium line", x=28, width=36),
        ], sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(region["x_percent"], 18)
        self.assertEqual(region["x_percent"] + region["width_percent"], 76)

    def test_near_widest_trustworthy_box_beats_padded_low_confidence_outlier(self):
        region = select_subtitle_region([
            candidate(1, "short caption", x=30, width=40, height=8, confidence=0.90),
            candidate(2, "long caption", x=26.5, width=48.2, height=8, confidence=0.92),
            candidate(3, "another caption", x=28, width=44, height=8, confidence=0.91),
            candidate(4, "padded detector box", x=27.2, width=48.4, height=10.6, confidence=0.77),
        ], sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(region["x_percent"], 26.5)
        self.assertEqual(region["width_percent"], 48.2)
        self.assertEqual(region["height_percent"], 8)

    def test_merges_separate_word_boxes_before_measuring_caption_width(self):
        items = []
        for frame, left_text, right_text in [
            (1, "first", "caption"),
            (2, "second", "caption"),
            (3, "third", "caption"),
            (4, "fourth", "caption"),
        ]:
            items.extend([
                candidate(frame, left_text, x=23, width=20),
                candidate(frame, right_text, x=47, width=30),
            ])

        region = select_subtitle_region(items, sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(region["x_percent"], 23)
        self.assertEqual(region["x_percent"] + region["width_percent"], 77)

    def test_merges_two_subtitle_lines_into_the_detected_region(self):
        items = []
        for frame, first, second in [
            (1, "Excuse me can I ask", "you for directions"),
            (2, "Where do", "you need to go"),
            (3, "It is just right", "across the street"),
            (4, "And how do I get", "to this restaurant"),
        ]:
            items.extend([
                candidate(frame, first, x=22, y=55, width=56, height=5),
                candidate(frame, second, x=18, y=60, width=64, height=5),
            ])

        region = select_subtitle_region(items, sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(region["y_percent"], 55)
        self.assertEqual(region["y_percent"] + region["height_percent"], 65)
        self.assertAlmostEqual(region["line_height_percent"], 5.0)

    def test_does_not_merge_a_small_moving_watermark_below_the_caption(self):
        items = []
        for frame, caption_x, caption_width, watermark_x in [
            (1, 27, 46, 59),
            (2, 31, 40, 49),
            (3, 30, 42, 40),
            (4, 28, 45, 21),
        ]:
            items.extend([
                candidate(
                    frame,
                    f"changing caption {frame}",
                    x=caption_x,
                    y=66,
                    width=caption_width,
                    height=8,
                ),
                candidate(
                    frame,
                    "@creator",
                    x=watermark_x,
                    y=74.7,
                    width=24,
                    height=3.1,
                    confidence=0.8,
                ),
            ])

        region = select_subtitle_region(items, sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(region["height_percent"], 8)
        self.assertEqual(region["width_percent"], 46)

    def test_similar_height_creator_handle_does_not_enlarge_cjk_caption(self):
        items = []
        for frame, caption, watermark_x, watermark_text in [
            (1, "皇帝每天都要吃草", 15, "抖音@凡人匠"),
            (2, "为什么这草也要吃", 24, "科音@凡人匠"),
            (3, "等干透后点燃烧尽", 42, "抖音@H人匠"),
            (4, "接着用细筛过滤", 58, "科音@凡人匠"),
        ]:
            items.extend([
                candidate(frame, caption, x=20, y=69, width=60, height=4),
                candidate(
                    frame,
                    watermark_text,
                    x=watermark_x,
                    y=74.7,
                    width=24,
                    height=3.3,
                    confidence=0.93,
                ),
            ])

        region = select_subtitle_region(items, sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(region["y_percent"], 69)
        self.assertEqual(region["height_percent"], 4)
        self.assertEqual(region["width_percent"], 60)

    def test_largest_real_three_line_caption_defines_the_static_region(self):
        items = []
        for frame in range(1, 13):
            items.extend([
                candidate(frame, f"caption line one {frame}", x=22, y=54, width=56, height=5),
                candidate(frame, f"caption line two {frame}", x=24, y=59, width=52, height=5),
            ])
        items.append(candidate(6, "caption line three", x=28, y=64, width=44, height=5))

        region = select_subtitle_region(items, sample_count=24)

        self.assertIsNotNone(region)
        self.assertEqual(region["y_percent"], 54)
        self.assertEqual(region["height_percent"], 15)

    def test_repeated_third_subtitle_line_expands_the_region(self):
        items = []
        for frame in range(1, 13):
            items.extend([
                candidate(frame, f"caption line one {frame}", x=22, y=54, width=56, height=5),
                candidate(frame, f"caption line two {frame}", x=24, y=59, width=52, height=5),
            ])
            if frame in {3, 6, 9}:
                items.append(candidate(frame, f"caption line three {frame}", x=28, y=64, width=44, height=5))

        region = select_subtitle_region(items, sample_count=24)

        self.assertIsNotNone(region)
        self.assertGreater(region["height_percent"], 14)

    def test_does_not_merge_distant_central_overlay_into_subtitles(self):
        items = []
        for frame in range(1, 5):
            items.extend([
                candidate(frame, "STATIC BRAND", x=35, y=35, width=30, height=4),
                candidate(frame, f"changing caption {frame}", x=24, y=58, width=52, height=5),
            ])

        region = select_subtitle_region(items, sample_count=12)

        self.assertIsNotNone(region)
        self.assertGreater(region["y_percent"], 50)

    def test_rejects_static_lower_third_or_watermark(self):
        self.assertIsNone(select_subtitle_region([
            candidate(1, "NEWS LIVE", x=5, width=28),
            candidate(2, "NEWS LIVE", x=5, width=28),
            candidate(3, "NEWS LIVE", x=5, width=28),
            candidate(4, "NEWS LIVE", x=5, width=28),
        ]))

    def test_selects_changing_subtitles_in_middle_of_frame(self):
        region = select_subtitle_region([
            candidate(1, "middle caption one", y=42),
            candidate(2, "middle caption two", y=43),
            candidate(3, "middle caption three", y=41),
            candidate(4, "middle caption four", y=42),
        ], sample_count=12)

        self.assertIsNotNone(region)
        self.assertLess(region["y_percent"], 50)
        self.assertGreater(region["y_percent"] + region["height_percent"], 40)

    def test_selects_changing_subtitles_near_top_of_frame(self):
        region = select_subtitle_region([
            candidate(1, "top caption one", y=5),
            candidate(2, "top caption two", y=6),
            candidate(3, "top caption three", y=5),
            candidate(4, "top caption four", y=6),
        ], sample_count=12)

        self.assertIsNotNone(region)
        self.assertLess(region["y_percent"], 12)

    def test_rejects_off_centre_interface_text_and_low_confidence(self):
        self.assertIsNone(select_subtitle_region([
            candidate(1, "menu one", x=2, y=30, width=16),
            candidate(2, "menu two", x=2, y=30, width=16),
            candidate(3, "menu three", x=2, y=30, width=16),
            candidate(4, "menu four", x=2, y=30, width=16),
        ], sample_count=12))
        self.assertIsNone(select_subtitle_region([
            candidate(1, "caption one", y=42, confidence=0.4),
            candidate(2, "caption two", y=42, confidence=0.4),
            candidate(3, "caption three", y=42, confidence=0.4),
            candidate(4, "caption four", y=42, confidence=0.4),
        ], sample_count=12))

    @patch("haizflow.pipeline.subtitle_ocr._ocr_engine")
    def test_ocr_coordinates_use_the_complete_frame(self, engine):
        engine.return_value.return_value = SimpleNamespace(
            boxes=[[[200, 300], [600, 300], [600, 360], [200, 360]]],
            txts=["middle subtitle"],
            scores=[0.92],
        )

        items = _ocr_candidates(Path("frame.jpg"), 1, 1000, 1000)

        self.assertEqual(len(items), 1)
        self.assertAlmostEqual(items[0].y, 30.0)
        self.assertAlmostEqual(items[0].height, 6.0)

    def test_static_region_uses_one_complete_observation_without_mixing_axes(self):
        region = select_subtitle_region([
            candidate(1, "wide but short", x=10, y=62, width=80, height=4),
            candidate(2, "largest complete caption", x=18, y=54, width=64, height=10),
            candidate(3, "another caption", x=20, y=56, width=60, height=9),
            candidate(4, "short caption", x=30, y=60, width=40, height=5),
        ], sample_count=12)

        self.assertIsNotNone(region)
        self.assertEqual(
            (
                region["x_percent"],
                region["y_percent"],
                region["width_percent"],
                region["height_percent"],
            ),
            (18, 54, 64, 10),
        )
        self.assertNotIn("timeline", region)


if __name__ == "__main__":
    unittest.main()
