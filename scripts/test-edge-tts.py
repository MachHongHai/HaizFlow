"""Opt-in real service smoke test, isolated from installed HFlow projects."""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send generic test text to Microsoft")
    parser.add_argument("--long", action="store_true", help="Also verify a multi-request narration")
    parser.add_argument("--batch", action="store_true", help="Measure generic subtitle synthesis and cache reuse")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to explicitly enable network synthesis")
    sys.path.insert(0, str(ROOT / "src"))
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="edge-live-", dir=ROOT / "build") as temporary:
        os.environ["HFLOW_HOME"] = temporary
        os.environ["RUNTIME_DATA_DIR"] = str(Path(temporary) / "data")
        from hflow.core.edge_voices import EDGE_VOICES
        from hflow.pipeline.edge_tts_backend import synthesize_to_mp3, valid_audio
        from hflow.utils.ffmpeg import get_video_duration

        texts = {"vi": "Xin chào. Đây là kiểm tra giọng đọc HFlow.",
                 "en": "Hello. This is a HFlow voice test.",
                 "zh": "你好。这是语音测试。"}
        if args.batch:
            from hflow.pipeline.tts import generate_voice_parts

            subtitles = Path(temporary) / "segments.json"
            subtitles.write_text(json.dumps([{"text": text} for text in (
                "Xin chào, chúc bạn một ngày tốt lành.",
                "Chúng ta sẽ bắt đầu chuyến đi vào sáng mai.",
                "Hãy kiểm tra lại hành lý trước khi lên xe.",
                "Mọi người đang đợi ở trước cửa nhà.",
                "Thời tiết hôm nay rất đẹp và dễ chịu.",
                "Tôi đã chuẩn bị nước uống cho cả nhóm.",
                "Chuyến đi này sẽ có nhiều điều thú vị.",
                "Cảm ơn bạn đã cùng tham gia với chúng tôi.",
            )]), encoding="utf-8")
            parts = Path(temporary) / "parts"
            for case in ("subtitle-batch", "cached-batch"):
                start = time.monotonic()
                generate_voice_parts(str(subtitles), str(parts), "vi-VN-HoaiMyNeural",
                                     "edge-live-fixture", provider="edge")
                elapsed = time.monotonic() - start
                paths = list(parts.glob("voice_*.mp3"))
                assert len(paths) == 8 and all(valid_audio(str(path)) for path in paths)
                print(json.dumps({"case": case, "passed": True, "count": len(paths),
                                  "seconds": round(elapsed, 3),
                                  "duration": round(sum(get_video_duration(str(path)) for path in paths), 3)}), flush=True)
            return
        for language, voices in EDGE_VOICES.items():
            for voice, *_labels in voices:
                path = Path(temporary) / f"{voice}.mp3"
                start = time.monotonic()
                synthesize_to_mp3(texts[language], voice, str(path), "edge-live-fixture", language_id=language)
                if not valid_audio(str(path)):
                    raise RuntimeError("Live sample failed verification")
                print(json.dumps({"voice": voice, "passed": True, "bytes": path.stat().st_size,
                                  "duration": get_video_duration(str(path)),
                                  "seconds": round(time.monotonic() - start, 2)}), flush=True)
        if args.long:
            path = Path(temporary) / "long.mp3"
            synthesize_to_mp3(texts["vi"] * 45, "vi-VN-HoaiMyNeural", str(path), "edge-live-fixture")
            if not valid_audio(str(path)):
                raise RuntimeError("Long live sample failed verification")
            print(json.dumps({"case": "multi-chunk", "passed": True,
                              "bytes": path.stat().st_size, "duration": get_video_duration(str(path))}), flush=True)


if __name__ == "__main__":
    main()
