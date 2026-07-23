import subprocess
import unittest
from unittest import mock

from haizflow.pipeline import process_registry


class ProcessRegistryTests(unittest.TestCase):
    def setUp(self):
        with process_registry._REGISTRY_LOCK:
            process_registry._cancelled_videos.clear()
            process_registry._paused_videos.clear()
            process_registry._active_processes.clear()

    def tearDown(self):
        self.setUp()

    def test_register_kills_a_process_when_cancel_wins_the_race(self):
        process = mock.Mock()
        process.poll.return_value = None
        process_registry.cancel_video("video-1")

        with mock.patch.object(process_registry, "_kill_process_tree") as kill:
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                process_registry.register_process("video-1", process)

        kill.assert_called_once_with(process)
        with process_registry._REGISTRY_LOCK:
            self.assertEqual(process_registry._active_processes.get("video-1"), [])

    def test_timed_out_process_is_killed_and_unregistered(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.communicate.side_effect = subprocess.TimeoutExpired(["ffmpeg"], 1)

        with mock.patch.object(process_registry, "_kill_process_tree") as kill:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                process_registry.communicate_process(
                    "video-2",
                    process,
                    label="FFmpeg test",
                    timeout_seconds=1,
                )

        kill.assert_called_once_with(process)
        with process_registry._REGISTRY_LOCK:
            self.assertEqual(process_registry._active_processes.get("video-2"), [])


if __name__ == "__main__":
    unittest.main()
