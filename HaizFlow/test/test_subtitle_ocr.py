import unittest

from haizflow.pipeline.subtitle_ocr import TextCandidate, select_subtitle_region


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

    def test_rejects_static_lower_third_or_watermark(self):
        self.assertIsNone(select_subtitle_region([
            candidate(1, "NEWS LIVE", x=5, width=28),
            candidate(2, "NEWS LIVE", x=5, width=28),
            candidate(3, "NEWS LIVE", x=5, width=28),
            candidate(4, "NEWS LIVE", x=5, width=28),
        ]))

    def test_rejects_text_outside_subtitle_band_and_low_confidence(self):
        self.assertIsNone(select_subtitle_region([
            candidate(1, "headline one", y=30),
            candidate(2, "headline two", y=30),
            candidate(3, "headline three", y=30),
            candidate(4, "headline four", y=30),
            candidate(5, "caption", confidence=0.4),
        ]))


if __name__ == "__main__":
    unittest.main()
