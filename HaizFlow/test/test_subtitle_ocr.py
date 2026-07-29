import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from haizflow.pipeline.subtitle_ocr import TextCandidate, _ocr_candidates, select_subtitle_region


def candidate(frame, text, *, x=25, y=78, width=50, height=5, confidence=0.9):
    return TextCandidate(frame, x, y, width, height, text, confidence)


class SubtitleOcrSelectionTests(unittest.TestCase):
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
        self.assertLessEqual(region["x_percent"], 17)
        self.assertGreaterEqual(region["x_percent"] + region["width_percent"], 77)

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
        self.assertLessEqual(region["x_percent"], 21.5)
        self.assertGreaterEqual(region["x_percent"] + region["width_percent"], 78.5)

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
        self.assertLessEqual(region["y_percent"], 54.7)
        self.assertGreaterEqual(region["y_percent"] + region["height_percent"], 65.3)
        self.assertAlmostEqual(region["line_height_percent"], 5.0)

    def test_single_third_line_sample_does_not_oversize_the_region(self):
        items = []
        for frame in range(1, 13):
            items.extend([
                candidate(frame, f"caption line one {frame}", x=22, y=54, width=56, height=5),
                candidate(frame, f"caption line two {frame}", x=24, y=59, width=52, height=5),
            ])
        items.append(candidate(6, "caption line three", x=28, y=64, width=44, height=5))

        region = select_subtitle_region(items, sample_count=24)

        self.assertIsNotNone(region)
        self.assertLess(region["height_percent"], 12)

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


if __name__ == "__main__":
    unittest.main()
