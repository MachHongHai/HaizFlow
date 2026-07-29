import os
import subprocess
import tempfile
from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS
from haizflow.services.video_store import log_to_video
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.utils.ffmpeg import _binary, get_media_stream_types

def extract_audio(video_path: str, output_wav_path: str, video_id: str):
    """Extracts audio from video to a 16kHz mono WAV file."""
    log_to_video(video_id, f"Extracting audio from: {video_path}")
    stream_types = get_media_stream_types(video_path)
    if "audio" not in stream_types:
        message = (
            "The source video has no audio track, so speech cannot be transcribed or dubbed. "
            "Replace it with a video that includes audio."
        )
        log_to_video(video_id, message)
        raise RuntimeError(message)

    output_directory = os.path.dirname(os.path.abspath(output_wav_path))
    os.makedirs(output_directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(
        prefix=".extracted-audio-",
        suffix=".wav",
        dir=output_directory,
    )
    os.close(handle)
    try:
        cmd = [
            _binary("ffmpeg"), "-y",
            "-i", video_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            temporary_path,
        ]

        check_cancellation(video_id)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _stdout, stderr = communicate_process(
            video_id,
            process,
            label="FFmpeg audio extraction",
            timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS,
        )
        check_cancellation(video_id)
        if process.returncode != 0:
            log_to_video(video_id, f"FFmpeg Error output:\n{stderr}")
            raise RuntimeError(f"FFmpeg extraction failed with exit code {process.returncode}")
        if os.path.getsize(temporary_path) <= 44:
            raise RuntimeError("FFmpeg audio extraction produced an empty WAV file.")
        os.replace(temporary_path, output_wav_path)
        temporary_path = ""
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass

    log_to_video(video_id, f"Successfully extracted audio to: {output_wav_path}")
