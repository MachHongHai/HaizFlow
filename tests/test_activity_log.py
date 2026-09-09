import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.activity_log import ActivityLogBuffer
from haizflow.desktop.models import ActivityEventModel
from haizflow.services import video_store


class ActivityLogBufferTests(unittest.TestCase):
    def test_video_log_entries_are_structured_and_keep_multiline_errors_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "logs.txt"
            path.touch()
            emitted = []
            with (
                patch.object(video_store, "get_video_logs_path", return_value=str(path)),
                patch.object(video_store, "emit_log", lambda _video_id, line: emitted.append(line)),
            ):
                video_store.log_to_video(
                    "video-id",
                    "Render failed\nTraceback line",
                    level="ERROR",
                    component="RENDER",
                )
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertTrue(all("[ERROR] [RENDER]" in line for line in lines))
        self.assertTrue(lines[0].endswith("Render failed"))
        self.assertTrue(lines[1].endswith("Traceback line"))
        self.assertEqual(emitted, lines)

    def test_buffer_keeps_only_the_recent_bounded_tail(self):
        buffer = ActivityLogBuffer(max_lines=3, max_characters=30)
        buffer.append(["one", "two", "three", "four"])

        self.assertEqual(buffer.text, "two\nthree\nfour")

    def test_read_tail_does_not_load_a_large_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "logs.txt"
            path.write_text("old line\n" * 10_000 + "latest line\n", encoding="utf-8")
            tail = ActivityLogBuffer.read_tail(str(path), max_characters=100)

        self.assertIn("latest line", tail)
        self.assertNotIn("old line\nold line\nold line\nold line\nold line\nold line\nold line\nold line\nold line\nold line", tail)


class ActivityEventModelTests(unittest.TestCase):
    def test_translates_technical_stage_into_compact_activity(self):
        model = ActivityEventModel()
        model.append_lines(["18:21:26 [INFO] [TRANSLATE] Translating subtitles 5-6 of 8"])

        self.assertEqual(model.rowCount(), 1)
        index = model.index(0, 0)
        self.assertEqual(model.data(index, model.TitleRole), "Dịch phụ đề")
        self.assertEqual(model.data(index, model.StageRole), "TRANSLATE")
        self.assertEqual(model.data(index, model.ProgressRole), 75)

    def test_coalesces_model_heartbeat_lines(self):
        model = ActivityEventModel()
        model.append_lines([
            "18:21:26 [INFO] [OMNIVOICE] OmniVoice is still working",
            "18:21:30 [INFO] [OMNIVOICE] OmniVoice is still working",
        ])

        self.assertEqual(model.rowCount(), 1)
        index = model.index(0, 0)
        self.assertEqual(model.data(index, model.TimestampRole), "18:21:30")

    def test_activity_titles_follow_the_interface_language(self):
        model = ActivityEventModel()
        model.append_lines(["18:21:26 [INFO] [TTS] Generating voice 1/4"])
        index = model.index(0, 0)
        self.assertEqual(model.data(index, model.TitleRole), "Tạo giọng")

        model.set_language("en")

        self.assertEqual(model.data(index, model.TitleRole), "Voice generation")

    def test_skips_debug_and_queue_control_lines(self):
        model = ActivityEventModel()
        model.append_lines(["__QUEUE_CHANGED__", "18:21:26 [DEBUG] [PIPELINE] internal state"])
        self.assertEqual(model.rowCount(), 0)

    def test_parses_the_structured_iso_log_format_written_by_video_store(self):
        model = ActivityEventModel()
        model.append_lines([
            "[2026-08-31T12:34:56Z] [INFO] [MANUAL] Cache hit · voice",
        ])

        index = model.index(0, 0)
        self.assertEqual(model.data(index, model.TimestampRole), "12:34:56")
        self.assertEqual(model.data(index, model.StageRole), "MANUAL")
        self.assertEqual(model.data(index, model.TitleRole), "Công cụ Thủ công")


if __name__ == "__main__":
    unittest.main()
