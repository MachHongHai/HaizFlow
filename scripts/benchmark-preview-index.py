"""Synthetic CPU-only preview scaling check. No app, models or project writes."""
from statistics import median
from time import perf_counter
import argparse
from pathlib import Path

import numpy as np

from haizflow.desktop.manual_preview_audio_controller import IndexedAudioTracks, mix_frames
from haizflow.schemas.editor import EditorClip, EditorKeyframe
from haizflow.services.editor_documents import evaluate_keyframes, keyframe_index


def timed(callback):
    samples = []
    for _ in range(20):
        start = perf_counter()
        callback()
        samples.append((perf_counter() - start) * 1000)
    return round(median(samples), 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, help="Optional read-only editor snapshot; never reconciled or saved")
    parser.add_argument("--caption-count", type=int, default=0, help="Synthetic subtitle projection sample")
    args = parser.parse_args()
    pcm = np.full((480, 2), 1000, dtype=np.int16)
    for count in (100, 1000, 10000):
        tracks = [{"id": str(i), "kind": "voice", "start": i * 960, "samples": pcm} for i in range(count)]
        indexed = IndexedAudioTracks(tracks)
        cursor = (count - 1) * 960
        volumes = {"voice": 1}
        original = lambda: mix_frames(tracks, cursor, 480, volumes)
        optimized = lambda: mix_frames(indexed, cursor, 480, volumes)
        assert original() == optimized()
        print(f"audio tracks={count}: linear={timed(original)}ms indexed={timed(optimized)}ms")
        names = ("position_x", "position_y", "scale", "rotation", "opacity")
        clip = EditorClip(clip_id="bench", track_id="overlays", kind="image", duration_ms=100000,
                          keyframes=[EditorKeyframe(keyframe_id=str(i), time_ms=i, value=i % 100,
                              property_name=names[i % len(names)]) for i in range(count)])
        prepared = keyframe_index(clip)
        original_keys = lambda: [evaluate_keyframes(clip, name, count - 10, 50) for name in names]
        optimized_keys = lambda: [evaluate_keyframes(clip, name, count - 10, 50, index=prepared) for name in names]
        assert original_keys() == optimized_keys()
        print(f"keyframes count={count}: unprepared={timed(original_keys)}ms indexed={timed(optimized_keys)}ms")
    if args.document or args.caption_count:
        from PySide6.QtGui import QGuiApplication
        from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
        from haizflow.schemas.editor import EditorDocument

        app = QGuiApplication.instance() or QGuiApplication([])
        document = (EditorDocument.model_validate_json(args.document.read_text("utf-8")) if args.document else
                    EditorDocument(video_id="benchmark", clips=[EditorClip(clip_id=f"subtitle-{i}",
                        segment_id=str(i), track_id="subtitles", kind="subtitle", name="Một câu phụ đề thử nghiệm.",
                        start_ms=i * 2000, duration_ms=1500) for i in range(max(0, min(10000, args.caption_count)))]))
        model = ManualEditorDocumentModel()
        # Read-only benchmark: bypass load/ensure/migrations/waveform scheduling.
        model._document = document
        try:
            def uncached():
                model._subtitle_payloads = None
                return model.subtitleSegments
            captions = uncached()
            original_ms = timed(uncached)
            assert captions == model.subtitleSegments
            optimized_ms = timed(lambda: model.subtitleSegments)
            print(f"caption projection cues={len(captions)}: uncached={original_ms}ms cached={optimized_ms}ms")
        finally:
            model.close()
        assert app is not None


if __name__ == "__main__":
    main()
