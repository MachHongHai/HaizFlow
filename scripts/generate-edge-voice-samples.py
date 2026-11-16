"""Generate verified, prerecorded Edge voice-library samples (explicit opt-in)."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send the public sample sentences to Edge TTS")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to enable sample synthesis")
    sys.path.insert(0, str(ROOT / "src"))
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="edge-samples-", dir=ROOT / "build") as temporary:
        # No installed projects, model caches or user subtitle text are read.
        os.environ["HAIZFLOW_SMOKE_TEST"] = "1"
        os.environ["HAIZFLOW_HOME"] = temporary
        os.environ["RUNTIME_DATA_DIR"] = str(Path(temporary) / "data")
        from haizflow.core.edge_voices import EDGE_VOICES
        from haizflow.pipeline.edge_tts_backend import synthesize_to_mp3, valid_audio
        from haizflow.utils.ffmpeg import get_video_duration

        samples = ROOT / "src/haizflow/desktop/assets/voice_samples"
        manifest = json.loads((samples / "samples.json").read_text(encoding="utf-8"))
        entries = []
        for language, voices in EDGE_VOICES.items():
            for voice, *_labels in voices:
                path = samples / "edge" / voice / f"{language}.mp3"
                if not valid_audio(str(path)):
                    synthesize_to_mp3(manifest["sentences"][language], voice, str(path),
                                      "edge-packaged-sample", language_id=language)
                if not valid_audio(str(path)):
                    raise RuntimeError(f"Invalid sample: {voice}")
                print(json.dumps({"voice": voice, "language": language,
                                  "bytes": path.stat().st_size,
                                  "duration": round(get_video_duration(str(path)), 3)}), flush=True)
                entries.append({"provider": "edge", "voice": voice, "language": language,
                                "path": path.relative_to(samples).as_posix(),
                                "bytes": path.stat().st_size,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        # Read again after synthesis; another developer task may have added
        # unrelated providers while Edge requests were running.
        manifest = json.loads((samples / "samples.json").read_text(encoding="utf-8"))
        manifest["samples"] = [row for row in manifest["samples"] if row["provider"] != "edge"] + entries
        (samples / "samples.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
