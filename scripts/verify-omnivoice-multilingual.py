"""Opt-in installed-model check. Reads a source project; writes only a separate evidence directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--stage", choices=("synthesis", "render", "recognition"), default="synthesis")
    parser.add_argument("--asr-model", choices=("small", "large-v3-turbo"), default="small")
    args = parser.parse_args()
    source = args.source_workspace.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        parser.error("Evidence must be outside, and must not contain, the source workspace.")
    output.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        HAIZFLOW_SMOKE_TEST="1",
        RUNTIME_DATA_DIR=str(output / "runtime"),
        CACHE_DIR=str(output / "cache"),
        TMP_DIR=str(output / "tmp"),
        MODELS_DIR=str(args.models.resolve()),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DEACTIVATE_ASYNC_LOAD="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    report_path = output / "report.json"
    report = json.loads(report_path.read_text("utf-8")) if report_path.exists() else {"results": {}}

    def save():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    from haizflow.core.memory import GIB, memory_snapshot
    from haizflow.pipeline import omnivoice_tts as voice
    from haizflow.pipeline import tts_quality
    from haizflow.utils.ffmpeg import _binary, get_video_duration

    def run(command):
        return subprocess.run(command, check=True, capture_output=True, timeout=300)

    if args.stage == "synthesis":
        memory = memory_snapshot()
        report["memory_before_import"] = memory.diagnostic()
        save()
        if memory.available_bytes is None or memory.available_bytes < 3 * GIB:
            raise RuntimeError("Native inference needs at least 3 GiB free RAM before imports. No model was loaded.")
        sdk = args.models / "omnivoice/sdk/site-packages"
        if not (sdk / "omnivoice").is_dir():
            raise RuntimeError("Installed OmniVoice SDK is unavailable; this check never downloads resources.")
        os.environ.update(voice._worker_environment())
        sys.path.insert(0, str(sdk))
        import numpy as np
        import soundfile as sf
        import torch

        memory = memory_snapshot()
        report["memory_before_model"] = memory.diagnostic()
        save()
        if (
            memory.available_bytes is None
            or memory.available_bytes < 2 * GIB
            or (memory.commit_available_bytes is not None and memory.commit_available_bytes < 6 * GIB)
        ):
            raise RuntimeError("Insufficient memory headroom after imports. No model was loaded.")
        if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * GIB:
            raise RuntimeError("Native check needs at least 4 GiB free VRAM.")
        runtime = {}
        report["device"] = torch.cuda.get_device_name(0)
        report["inference_steps"] = 32
        original_validate = tts_quality.validate_speech_waveform
        active_group = ""
        observed = []

        def observe(waveform, rate):
            wave = np.asarray(waveform, dtype=np.float32).reshape(-1)
            record = {"seconds": round(len(wave) / rate, 4), "samples": len(wave), "sample_rate": rate}
            try:
                original_validate(wave, rate)
                record["waveform_valid"] = True
            except Exception as exc:
                record.update(waveform_valid=False, error=str(exc))
                path = output / active_group / f"invalid-attempt-{len(observed) + 1:03d}.wav"
                sf.write(str(path), wave, rate, subtype="FLOAT")
                record["invalid_audio"] = str(path)
                raise
            finally:
                observed.append(record)

        tts_quality.validate_speech_waveform = observe

        def synthesize(name, language, items, *, references=True):
            nonlocal active_group, observed
            active_group, observed = name, []
            folder = output / name
            folder.mkdir(exist_ok=True)
            prepared = []
            for index, item in enumerate(items, 1):
                preset, transcript = voice._preset_reference(item["voice"], language) if references else ("", "")
                if references and not (preset and transcript):
                    raise RuntimeError(f"Missing {language}/{item['voice']} reference.")
                prepared.append(
                    {
                        **item,
                        "wav_path": str(folder / f"voice_{index:04d}.wav"),
                        "preset_reference_path": preset,
                        "preset_reference_text": transcript,
                    }
                )
            request = {
                "model_root": str(args.models / "omnivoice"),
                "site_packages": str(sdk),
                "device": "cuda:0",
                "language": language,
                "speaker_mode": "multiple",
                "inference_steps": 32,
                "voice_seed": int(hashlib.sha256(items[0]["voice"].encode()).hexdigest()[:8], 16) & 0x7FFFFFFF,
                "status_path": str(folder / "status.json"),
                "items": prepared,
            }
            request_path = folder / "request.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            started = time.perf_counter()
            try:
                voice._worker_main(str(request_path), runtime)
                result = {"passed": True, "generated": len(prepared)}
            except Exception as exc:
                result = {"passed": False, "error": str(exc), "generated": len(list(folder.glob("voice_[0-9]*.wav")))}
            result.update(
                seconds=round(time.perf_counter() - started, 3),
                language=language,
                measurements=observed,
                peak_vram_mib=round(torch.cuda.max_memory_allocated() / 1024**2, 1),
            )
            report["results"][name] = result
            save()
            print(json.dumps({name: result}, ensure_ascii=False), flush=True)
            return result["passed"]

        # Same seed/text/preset as the failed sentence, without references: a
        # bounded baseline only, never a production fallback or a cache write.
        synthesize(
            "ja-unconditioned-baseline",
            "ja",
            [{"text": "逃げただと？", "voice": "omnivoice:female_gentle"}],
            references=False,
        )
        synthesize("ja-fixed-short", "ja", [{"text": "逃げただと？", "voice": "omnivoice:female_gentle"}])
        probes = {
            "ko": [
                "네.",
                "고마워요.",
                "도망쳤다고?",
                "안녕하세요. 오늘은 날씨가 좋습니다.",
                "우리는 함께 새로운 이야기를 시작합니다.",
                "다음에 다시 만나요.",
            ],
            "es": [
                "Sí.",
                "Gracias.",
                "¿Has huido?",
                "Hola, hoy hace muy buen tiempo.",
                "Vamos a comenzar una nueva historia juntos.",
                "Muchas gracias y hasta la próxima.",
            ],
        }
        for language, texts in probes.items():
            items = [
                {
                    "text": text,
                    "voice": ["omnivoice:female_gentle", "omnivoice:male", "omnivoice:deep"][i % 3],
                    "speaker_id": str(i % 3),
                }
                for i, text in enumerate(texts)
            ]
            synthesize(language + "-fixed", language, items)
        segments = json.loads((source / "temp/vi_segments.json").read_text("utf-8"))
        logs = (source / "logs.txt").read_text("utf-8").rsplit("Restart prepared.", 1)[-1]
        mapping = {
            int(index): (preset, speaker)
            for index, preset, speaker in re.findall(
                r"\[TTS\]\[QUEUED\] provider=omnivoice segment=(\d+)/\d+ voice=(\S+) speaker=(\S+)", logs
            )
        }
        if len(segments) != 30 or set(mapping) != set(range(1, 31)):
            raise RuntimeError("Expected the exact 30-sentence source run and its complete preset mapping.")
        items = [
            {"text": item["text"], "voice": mapping[i][0], "speaker_id": mapping[i][1]}
            for i, item in enumerate(segments, 1)
        ]
        synthesize("ja-full-video", "ja", items)
        report["results"]["ja-full-video"]["source_segments"] = segments
        report["results"]["ja-full-video"]["source_video"] = str(source / "input/video.mp4")
        release = output / "release.json"
        release.write_text('{"operation":"release_model"}', encoding="utf-8")
        voice._worker_main(str(release), runtime)
        report["released_vram_mib"] = round(torch.cuda.memory_allocated() / 1024**2, 1)
        save()
    elif args.stage == "render":
        from haizflow.pipeline import audio_timeline, render, subtitle
        from haizflow.schemas.video import CropSettings, SubtitleStyle

        for module in (audio_timeline, render, subtitle):
            module.log_to_video = lambda video_id, message, **kwargs: print(message, flush=True)
        import srt

        for name, language in (("ja-full-video", "ja"), ("ko-fixed", "ko"), ("es-fixed", "es")):
            result = report["results"][name]
            if not result["passed"]:
                raise RuntimeError(f"Complete {language} synthesis must pass before render.")
            folder = output / name
            parts = folder / "voice_parts"
            parts.mkdir(exist_ok=True)
            for wav in sorted(folder.glob("voice_[0-9]*.wav")):
                run(
                    [
                        _binary("ffmpeg"),
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(wav),
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        "128k",
                        str(parts / wav.with_suffix(".mp3").name),
                    ]
                )
            source_copy = folder / "source.mp4"
            if language == "ja":
                shutil.copy2(result["source_video"], source_copy)
                segments = result["source_segments"]
            else:
                items = json.loads((folder / "request.json").read_text("utf-8"))["items"]
                segments, cursor = [], 0.5
                for item in items:
                    duration = get_video_duration(item["wav_path"])
                    segments.append({"start": cursor, "end": cursor + duration, "text": item["text"]})
                    cursor += duration + 0.4
                run(
                    [
                        _binary("ffmpeg"),
                        "-v",
                        "error",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c=0x202020:s=720x1280:r=25:d={cursor + 2}",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-pix_fmt",
                        "yuv420p",
                        str(source_copy),
                    ]
                )
            transcript = folder / "segments.json"
            transcript.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
            audio = folder / "dubbed.wav"
            background = source / "temp/separation/955717e8/audio/no_vocals.wav" if language == "ja" else None
            audio_timeline.build_audio_timeline(
                str(transcript),
                str(parts),
                str(source_copy),
                str(audio),
                "native-" + language,
                background_audio_path=str(background) if background else None,
                original_video_volume=60 if background else 0,
                require_background_audio=bool(background),
            )
            captions = folder / "captions.srt"
            subtitle.generate_srt(
                str(transcript),
                str(captions),
                32,
                "native-" + language,
                preserve_segment_boundaries=True,
                voice_parts_dir=str(parts),
            )
            destination = folder / (language + "-fixed.mp4")
            render.render_video(
                str(source_copy),
                str(audio),
                str(captions),
                str(destination),
                "keep_ratio",
                SubtitleStyle(),
                CropSettings(),
                "native-" + language,
                original_subtitle_region=None,
            )
            run([_binary("ffmpeg"), "-v", "error", "-i", str(destination), "-f", "null", "-"])
            cues = list(srt.parse(captions.read_text("utf-8")))
            if len(cues) != len(segments):
                raise RuntimeError("Subtitle cue count changed during render.")
            for cue, segment in zip(cues, segments):
                if (
                    abs(cue.start.total_seconds() - segment["start"]) > 0.002
                    or cue.end.total_seconds() > segment["end"] + 0.002
                ):
                    raise RuntimeError("Subtitle timeline drifted beyond its source window.")
            result["render"] = {
                "path": str(destination),
                "seconds": get_video_duration(str(destination)),
                "bytes": destination.stat().st_size,
                "full_decode_passed": True,
                "subtitle_cues": len(cues),
                "subtitle_timeline_checked": True,
            }
            save()
            print(json.dumps(result["render"], ensure_ascii=False), flush=True)
    else:
        # Run in a fresh interpreter after OmniVoice exits: avoid mixing its
        # isolated Transformers 5 runtime with the app's recognition runtime.
        import torch
        from faster_whisper import WhisperModel

        torch.set_num_threads(2)

        model = WhisperModel(
            str(args.models / "whisper" / args.asr_model),
            device="cuda",
            compute_type="float16",
            cpu_threads=2,
            num_workers=1,
            local_files_only=True,
        )
        paths = [("ja-fixed-short", "ja"), ("ko-fixed", "ko"), ("es-fixed", "es"), ("ja-full-video", "ja")]
        for name, language in paths:
            folder = output / name
            wavs = sorted(folder.glob("voice_[0-9]*.wav"))
            concat = folder / "concat.txt"
            concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in wavs), encoding="utf-8")
            joined = folder / "joined.wav"
            run(
                [
                    _binary("ffmpeg"),
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(joined),
                ]
            )
            detected, detection = model.transcribe(
                str(joined), beam_size=3, vad_filter=False, condition_on_previous_text=False
            )
            detected_text = " ".join(segment.text for segment in detected)
            segments, info = model.transcribe(
                str(joined), language=language, beam_size=3, vad_filter=False, condition_on_previous_text=False
            )
            transcript = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
            report["results"][name]["asr"] = {
                "language": info.language,
                "segments": transcript,
                "model": args.asr_model,
                "auto_detected_language": detection.language,
                "auto_detected_text": detected_text,
                "auto_language_probability": detection.language_probability,
            }
            save()
            print(json.dumps({name: report["results"][name]["asr"]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
