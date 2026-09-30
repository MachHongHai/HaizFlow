"""Exercise two real local GPU/CPU translation chains in an isolated data root."""
import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--warm-recognition", action="store_true")
    args = parser.parse_args()
    root = args.output_root.resolve() / datetime.now(UTC).strftime("clone-check-%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        HAIZFLOW_SMOKE_TEST="1", APP_DATA_DIR=str(root), RUNTIME_DATA_DIR=str(root),
        MODELS_DIR=str(args.models.resolve()), HAIZFLOW_PROCESSING_DEVICE="gpu",
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from haizflow.core.hardware import configure_processing_device
    from haizflow.pipeline.process_video import process_video_sync
    from haizflow.schemas.video import VideoConfig
    from haizflow.services.desktop_videos import create_desktop_video
    from haizflow.services.external_engine import shared_external_engine_pool
    from haizflow.services.video_store import get_video, update_video

    print(f"Diagnostic output: {root}", flush=True)
    for translation in ("full", "q4"):
        configure_processing_device("gpu")
        if args.warm_recognition:
            pool = shared_external_engine_pool()
            context = {"device": "gpu", "model": "large-v3-turbo"}
            if not pool.warm("recognition", context):
                raise RuntimeError("Recognition warm-up engine is unavailable.")
            engine = pool._client(pool.engine_pack("recognition", context))
            warmed_process = engine._process
            pool.release({"recognition"})
            if warmed_process is not None and warmed_process.poll() is None:
                raise RuntimeError("Recognition engine remained alive after foreground release.")
            print("Warmed recognition engine exited before foreground processing", flush=True)
        video = create_desktop_video(str(args.input.resolve()), VideoConfig(
            mode="A", source_language="auto", target_language="en",
            speech_recognition_model="large-v3-turbo", translation_model=translation,
            tts_provider="omnivoice-gpu", tts_voice="omnivoice:clone",
            remove_original_subtitles=False,
        ))
        files = dict(video.files)
        files["voice_reference"] = str(args.reference.resolve())
        files["voice_reference_transcript"] = ""
        update_video(video.video_id, files=files)
        print(f"Starting Whisper GPU / HY-MT2 {translation} / clone GPU", flush=True)
        process_video_sync(video.video_id)
        result = get_video(video.video_id)
        print(f"{translation}: {result.status}: {result.error or ''}", flush=True)
        if result.status != "done":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
