"""Exercise extraction, stereo mixing and final encoding without changing projects."""

import json
import subprocess
import tempfile
from pathlib import Path

from haizflow.config import TMP_DIR
from haizflow.pipeline.audio_timeline import build_audio_timeline
from haizflow.pipeline.extract_audio import extract_audio
from haizflow.pipeline.render import render_video
from haizflow.schemas.video import CropSettings, SubtitleStyle
from haizflow.utils.ffmpeg import _binary


def main():
    with tempfile.TemporaryDirectory(prefix="audio-export-check-", dir=TMP_DIR) as directory:
        root = Path(directory)
        video = root / "input.mp4"
        subprocess.run(
            [
                _binary("ffmpeg"),
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=640x360:d=2",
                "-f",
                "lavfi",
                "-i",
                "aevalsrc=0.1*sin(2*PI*440*t)|0.1*sin(2*PI*880*t):s=48000:d=2",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-shortest",
                str(video),
            ],
            check=True,
        )
        master = root / "source.wav"
        mix = root / "mix.wav"
        extract_audio(str(video), str(master), "audio-export-check")
        segments = root / "segments.json"
        segments.write_text("[]", encoding="utf-8")
        build_audio_timeline(
            str(segments),
            str(root / "voices"),
            str(video),
            str(mix),
            "audio-export-check",
            background_audio_path=str(master),
            original_video_volume=100,
            require_voice_parts=False,
        )
        subtitles = root / "subtitles.srt"
        subtitles.write_text("1\n00:00:00,000 --> 00:00:01,500\nHaizFlow audio check\n", encoding="utf-8")
        output = root / "output.mp4"
        render_video(
            str(video),
            str(mix),
            str(subtitles),
            str(output),
            "keep_ratio",
            SubtitleStyle(),
            CropSettings(),
            "audio-export-check",
        )
        for path in (master, mix, output):
            result = subprocess.run(
                [
                    _binary("ffprobe"),
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_name,sample_rate,channels,bit_rate",
                    "-of",
                    "json",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            stream = json.loads(result.stdout)["streams"][0]
            assert stream["sample_rate"] == "48000" and stream["channels"] == 2, stream
            print(path.name, stream, flush=True)


if __name__ == "__main__":
    main()
