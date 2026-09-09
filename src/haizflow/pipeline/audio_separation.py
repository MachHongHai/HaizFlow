import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR
from haizflow.core.hardware import runtime_profile
from haizflow.core.model_integrity import (
    DEMUCS_MODEL_SIGNATURE,
    ModelIntegrityError,
    verify_demucs_model,
)
from haizflow.core.paths import is_frozen
from haizflow.services.video_store import log_to_video
from haizflow.pipeline.process_registry import check_cancellation, communicate_process


def _demucs_model_directory(video_id: str) -> Path:
    """Return the bootstrap-installed repository without hidden downloads."""
    model_directory = Path(MODELS_DIR) / "demucs"
    try:
        return verify_demucs_model(model_directory)
    except ModelIntegrityError as exc:
        log_to_video(video_id, "The verified Demucs model is not ready.")
        raise RuntimeError(
            "Demucs is missing or corrupted. Return to the model setup screen and retry the download."
        ) from exc


def _demucs_command() -> list[str]:
    if is_frozen():
        return [sys.executable, "--demucs-separate"]
    return [sys.executable, "-m", "demucs.separate"]


def separate_audio(audio_path: str, output_dir: str, video_id: str) -> tuple[str, str]:
    """
    Separates vocals and accompaniment from the given audio file using Demucs.
    Returns a tuple: (vocals_path, no_vocals_path)
    """
    log_to_video(video_id, f"Starting audio source separation using Demucs on: {audio_path}")
    
    # Auto-detect device
    profile = runtime_profile()
    device = "cuda" if profile.cuda_available else "cpu"
    log_to_video(video_id, f"Demucs device selected: {device}")
    model_directory = _demucs_model_directory(video_id)
    
    # We use --two-stems=vocals to output vocals and accompaniment (no_vocals)
    output_parent = os.path.dirname(os.path.abspath(output_dir))
    os.makedirs(output_parent, exist_ok=True)
    staging_dir = tempfile.mkdtemp(prefix=".audio-separation-", dir=output_parent)
    cmd = [
        *_demucs_command(),
        "--two-stems", "vocals",
        "-o", staging_dir,
        "-d", device,
        "-n", DEMUCS_MODEL_SIGNATURE,
        "--repo", str(model_directory),
        audio_path
    ]
    if device == "cpu":
        videos = 1 if profile.key in {"cpu_low_memory", "cpu_minimum"} else max(1, min(4, profile.cpu_threads // 2))
        cmd[-1:-1] = ["--shifts", "0", "--overlap", "0.1", "--segment", "7", "-j", str(videos)]
        log_to_video(
            video_id,
            f"CPU Demucs profile enabled with {videos} worker(s). Source separation will be slower without CUDA.",
        )
    
    log_to_video(video_id, f"Running Demucs command: {' '.join(cmd)}")
    
    check_cancellation(video_id)
    demucs_environment = os.environ.copy()
    # Demucs 4.0.1 does not pass weights_only=False explicitly. PyTorch 2.6+
    # changed torch.load's default to True, which rejects the official Demucs
    # package (it contains the model class as well as tensors). This override is
    # deliberately scoped to the child process and is safe only because the
    # exact local file was full-SHA256 verified immediately above.
    demucs_environment["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    
    # Run Demucs separate as a subprocess
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=demucs_environment,
        )
        _stdout, stderr = communicate_process(
            video_id,
            process,
            label="Demucs audio separation",
            timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
        )

        check_cancellation(video_id)

        if process.returncode != 0:
            log_to_video(video_id, f"Demucs separation failed with exit code {process.returncode}")
            log_to_video(video_id, f"Error details:\n{stderr}")
            raise RuntimeError(f"Demucs audio separation failed with exit code {process.returncode}: {stderr}")

        track_name = os.path.splitext(os.path.basename(audio_path))[0]
        vocals_path = None
        no_vocals_path = None
        for root, _dirs, files in os.walk(staging_dir):
            for file in files:
                if file == "vocals.wav":
                    vocals_path = os.path.join(root, file)
                elif file == "no_vocals.wav":
                    no_vocals_path = os.path.join(root, file)

        if not vocals_path or not no_vocals_path:
            model_name = "htdemucs"
            vocals_path = os.path.join(staging_dir, model_name, track_name, "vocals.wav")
            no_vocals_path = os.path.join(staging_dir, model_name, track_name, "no_vocals.wav")

        if any(
            not os.path.isfile(path) or os.path.getsize(path) <= 44
            for path in (vocals_path, no_vocals_path)
        ):
            raise FileNotFoundError(
                f"Could not locate non-empty separated audio files in {staging_dir}."
            )

        vocals_relative = os.path.relpath(vocals_path, staging_dir)
        no_vocals_relative = os.path.relpath(no_vocals_path, staging_dir)
        backup_dir = ""
        if os.path.isdir(output_dir):
            backup_dir = tempfile.mkdtemp(prefix=".audio-separation-backup-", dir=output_parent)
            os.rmdir(backup_dir)
            os.replace(output_dir, backup_dir)
        try:
            os.replace(staging_dir, output_dir)
        except Exception:
            if backup_dir and os.path.isdir(backup_dir):
                os.replace(backup_dir, output_dir)
            raise
        staging_dir = ""
        if backup_dir:
            shutil.rmtree(backup_dir, ignore_errors=True)
        vocals_path = os.path.join(output_dir, vocals_relative)
        no_vocals_path = os.path.join(output_dir, no_vocals_relative)
    finally:
        if staging_dir:
            shutil.rmtree(staging_dir, ignore_errors=True)
        
    log_to_video(video_id, "Audio source separation completed successfully.")
    log_to_video(video_id, f"Vocals path: {vocals_path}")
    log_to_video(video_id, f"No-vocals path: {no_vocals_path}")
    
    return vocals_path, no_vocals_path
