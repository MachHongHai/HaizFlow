import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController


class StartupWarmupQueueTests(unittest.TestCase):
    def _host(self, warmup_done):
        return SimpleNamespace(
            _deleted_video_ids=set(),
            _initial_model_warmup_done=warmup_done,
            _model_runtime_lock=threading.Lock(),
            _shutdown_started=False,
            _runtime_probe_error="",
            _model_setup_state="ready",
        )

    def test_pause_while_waiting_for_warmup_never_starts_the_pipeline(self):
        warmup_done = threading.Event()
        paused = threading.Event()
        video = SimpleNamespace(status="processing")
        controller = ProcessingLifecycleController(self._host(warmup_done))

        with (
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.get_video", return_value=video),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.update_video") as update,
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.log_to_video"),
            patch("haizflow.desktop.processing_lifecycle_controller.is_cancelled", side_effect=paused.is_set),
            patch("haizflow.desktop.processing_lifecycle_controller.is_paused", side_effect=paused.is_set),
            patch("haizflow.pipeline.process_video.process_video_sync") as process_video,
        ):
            worker = threading.Thread(target=controller.execute_pipeline, args=("video-1",))
            worker.start()
            time.sleep(0.03)
            paused.set()
            warmup_done.set()
            worker.join(1)

        self.assertFalse(worker.is_alive())
        process_video.assert_not_called()
        self.assertTrue(any(call.kwargs.get("step") == "waiting_for_models" for call in update.call_args_list))

    def test_video_starts_once_when_warmup_completes_without_pause(self):
        warmup_done = threading.Event()
        video = SimpleNamespace(status="processing")
        controller = ProcessingLifecycleController(self._host(warmup_done))

        with (
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.get_video", return_value=video),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.update_video"),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.log_to_video"),
            patch("haizflow.desktop.processing_lifecycle_controller.is_cancelled", return_value=False),
            patch("haizflow.desktop.processing_lifecycle_controller.is_paused", return_value=False),
            patch("haizflow.pipeline.process_video.process_video_sync") as process_video,
        ):
            worker = threading.Thread(target=controller.execute_pipeline, args=("video-2",))
            worker.start()
            time.sleep(0.03)
            self.assertTrue(worker.is_alive())
            warmup_done.set()
            worker.join(1)

        self.assertFalse(worker.is_alive())
        process_video.assert_called_once_with("video-2")


if __name__ == "__main__":
    unittest.main()
