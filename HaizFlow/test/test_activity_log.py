import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.activity_log import ActivityLogBuffer


class ActivityLogBufferTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
