import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.media import create_video_thumbnail_path, thumbnail_source


class ThumbnailSourceTests(unittest.TestCase):
    def test_thumbnail_url_changes_after_replacing_the_same_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            thumbnail = Path(temp_dir) / "thumbnail.jpg"
            thumbnail.write_bytes(b"old")
            first_source = thumbnail_source(str(thumbnail))
            time.sleep(0.002)
            thumbnail.write_bytes(b"new-thumbnail")
            os.utime(thumbnail, None)
            second_source = thumbnail_source(str(thumbnail))

        self.assertTrue(first_source.startswith("file:"))
        self.assertNotEqual(first_source, second_source)

    def test_thumbnail_creation_has_a_bounded_ffmpeg_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mp4"
            output = Path(temp_dir) / "thumbnail.jpg"
            source.write_bytes(b"video")

            with patch("haizflow.desktop.media.subprocess.run") as run:
                create_video_thumbnail_path(str(source), str(output))

        self.assertEqual(run.call_args.kwargs["timeout"], 30.0)


if __name__ == "__main__":
    unittest.main()
