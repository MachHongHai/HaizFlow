import subprocess
from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS
from haizflow.services.video_store import log_to_video
from haizflow.pipeline.process_registry import check_cancellation, communicate_process

def extract_audio(video_path: str, output_wav_path: str, video_id: str):
    """Extracts audio from video to a 16kHz mono WAV file."""
    log_to_video(video_id, f"Extracting audio from: {video_path}")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        output_wav_path
    ]
    
    check_cancellation(video_id)
    
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = communicate_process(
        video_id,
        p,
        label="FFmpeg audio extraction",
        timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
    )
    
    check_cancellation(video_id)
    
    if p.returncode != 0:
        log_to_video(video_id, f"FFmpeg Error output:\n{stderr}")
        raise RuntimeError(f"FFmpeg extraction failed with exit code {p.returncode}")
        
    log_to_video(video_id, f"Successfully extracted audio to: {output_wav_path}")
