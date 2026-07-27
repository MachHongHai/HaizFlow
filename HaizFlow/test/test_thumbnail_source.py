import os
import sys
import tempfile
import threading
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

    def test_thumbnail_replacement_is_atomic_and_does_not_keep_stale_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mp4"
            output = Path(temp_dir) / "thumbnail.jpg"
            source.write_bytes(b"video")
            output.write_bytes(b"stale")

            def render_thumbnail(command, **_kwargs):
                Path(command[-1]).write_bytes(b"fresh-thumbnail")
                return type("Result", (), {"returncode": 0})()

            with patch(
                "haizflow.desktop.media.subprocess.run",
                side_effect=render_thumbnail,
            ):
                created = create_video_thumbnail_path(str(source), str(output))
            output_bytes = output.read_bytes()
            temporary_files = list(Path(temp_dir).glob(".thumbnail-*"))

        self.assertEqual(created, str(output))
        self.assertEqual(output_bytes, b"fresh-thumbnail")
        self.assertEqual(temporary_files, [])

    def test_thumbnail_worker_stops_its_ffmpeg_child_during_shutdown(self):
        class FakeProcess:
            def __init__(self):
                self.returncode = None
                self.killed = False

            def poll(self):
                return self.returncode

            def kill(self):
                self.killed = True
                self.returncode = -9

            def wait(self, timeout=None):
                return self.returncode

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mp4"
            output = Path(temp_dir) / "thumbnail.jpg"
            source.write_bytes(b"video")
            cancel_event = threading.Event()
            cancel_event.set()
            process = FakeProcess()
            with patch(
                "haizflow.desktop.media.subprocess.Popen",
                return_value=process,
            ):
                created = create_video_thumbnail_path(
                    str(source),
                    str(output),
                    cancel_event=cancel_event,
                )
            temporary_files = list(Path(temp_dir).glob(".thumbnail-*"))

        self.assertEqual(created, "")
        self.assertTrue(process.killed)
        self.assertEqual(temporary_files, [])


if __name__ == "__main__":
    unittest.main()
