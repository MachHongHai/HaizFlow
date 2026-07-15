import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.pipeline import process_job


class GpuRecoveryTests(unittest.TestCase):
    def test_recovery_checkpoint_is_not_a_pause_resume_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "timeline.wav"
            artifact.write_bytes(b"audio")
            job = SimpleNamespace(
                checkpoints={"timeline": "signature"},
                resume_step="",
                runtime_recovery_step="rendering",
            )

            self.assertFalse(process_job._checkpoint_valid(job, "timeline", "signature", [str(artifact)]))
            self.assertTrue(process_job._recovery_checkpoint_valid(job, "timeline", "signature", [str(artifact)]))

    def test_gpu_preflight_stops_before_a_new_stage_when_power_is_lost(self):
        profile = SimpleNamespace(cuda_available=True)
        unavailable = SimpleNamespace(cuda_available=True, ac_powered=False)
        with (
            mock.patch.object(process_job, "runtime_profile", return_value=profile),
            mock.patch.object(process_job, "detect_hardware_capabilities", return_value=unavailable),
        ):
            with self.assertRaises(process_job.GpuRuntimeUnavailable):
                process_job._ensure_gpu_available("translation")

    def test_gpu_failure_switches_one_job_to_cpu_once(self):
        job = SimpleNamespace(gpu_recovery_attempted=False)
        profile = SimpleNamespace(cuda_available=True)
        with (
            mock.patch.object(process_job, "get_job", return_value=job),
            mock.patch.object(process_job, "runtime_profile", return_value=profile),
            mock.patch.object(process_job, "update_job") as update_job,
            mock.patch.object(process_job, "log_to_job"),
            mock.patch("autodub.pipeline.transcribe.release_warm_whisperx_model"),
            mock.patch.object(process_job, "shutdown_hymt2_worker"),
            mock.patch.object(process_job, "configure_processing_device") as configure,
        ):
            recovered = process_job._recover_gpu_to_cpu(
                "video-1",
                "translating",
                RuntimeError("CUDA driver lost"),
            )

        self.assertTrue(recovered)
        configure.assert_called_once_with("cpu")
        self.assertTrue(update_job.call_args.kwargs["gpu_recovery_attempted"])
        self.assertEqual(update_job.call_args.kwargs["runtime_recovery_step"], "translating")

    def test_second_gpu_failure_is_not_retried_automatically(self):
        job = SimpleNamespace(gpu_recovery_attempted=True)
        with mock.patch.object(process_job, "get_job", return_value=job):
            self.assertFalse(
                process_job._recover_gpu_to_cpu("video-1", "translating", RuntimeError("CUDA device lost"))
            )


if __name__ == "__main__":
    unittest.main()
