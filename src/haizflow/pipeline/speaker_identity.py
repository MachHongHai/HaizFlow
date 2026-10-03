"""Offline speaker identities; no source-language audio is passed to TTS."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR, TMP_DIR
from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.utils.ffmpeg import _binary

MODEL_FILE = "wespeaker_en_voxceleb_resnet34.onnx"
MODEL_SIZE = 26_534_127
MODEL_SHA256 = "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
MODEL_REVISION = "ff1ac5bca8ef11e90662b879aa923979e0bd277b"
MODEL_URL = (
    "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34/resolve/" + MODEL_REVISION + "/voxceleb_resnet34.onnx"
)
IDENTITY_VERSION = "wespeaker-stable-target-voices-v2-prototypes"


def verify_model(root: Path) -> Path:
    from haizflow.core.model_integrity import _verify

    _verify(
        root, kind="speaker identification", revision=MODEL_REVISION, expected={MODEL_FILE: (MODEL_SIZE, MODEL_SHA256)}
    )
    return root / MODEL_FILE


def _features(audio):
    """Kaldi-compatible 80-bin, 25/10 ms, Hamming filterbank + CMN."""
    import numpy as np

    audio = np.asarray(audio, dtype=np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(audio, 400)[::160].copy()
    frames -= frames.mean(axis=1, keepdims=True)
    frames[:, 1:] -= 0.97 * frames[:, :-1].copy()
    frames[:, 0] *= 0.03
    frames *= np.hamming(400).astype(np.float32)
    power = np.abs(np.fft.rfft(frames, n=512)) ** 2
    mel = 1127 * np.log1p(np.arange(257) * (16000 / 512) / 700)
    edges = np.linspace(1127 * np.log1p(20 / 700), 1127 * np.log1p(8000 / 700), 82)
    weights = np.maximum(
        0,
        np.minimum(
            (mel[None, :] - edges[:-2, None]) / (edges[1:-1] - edges[:-2])[:, None],
            (edges[2:, None] - mel[None, :]) / (edges[2:] - edges[1:-1])[:, None],
        ),
    )
    features = np.log(np.maximum(power @ weights.T, np.finfo(np.float32).eps)).astype(np.float32)
    return features - features.mean(axis=0, keepdims=True)


def _cluster(embeddings, threshold=0.50):
    """Complete-link clustering avoids chaining unrelated speakers together."""
    import numpy as np

    if not len(embeddings):
        return []
    vectors = np.array(embeddings, dtype=np.float32, copy=True)
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise ValueError("Invalid speaker embeddings.")
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-8)
    similarities = vectors @ vectors.T
    np.fill_diagonal(similarities, -np.inf)
    groups = [[i] for i in range(len(vectors))]
    while len(groups) > 1:
        i, j = np.unravel_index(np.argmax(similarities), similarities.shape)
        if similarities[i, j] < threshold:
            break
        i, j = sorted((int(i), int(j)))
        groups[i].extend(groups.pop(j))
        merged = np.minimum(similarities[i], similarities[j])
        similarities[i, :] = merged
        similarities[:, i] = merged
        similarities = np.delete(np.delete(similarities, j, axis=0), j, axis=1)
        np.fill_diagonal(similarities, -np.inf)
    labels = [0] * len(vectors)
    for identity, group in enumerate(sorted(groups, key=min)):
        for index in group:
            labels[index] = identity
    return labels


def _assign_identities(vectors, anchors, anchor_labels):
    """Retain reliable cluster members; use exemplars for expressive short turns.

    A single average loses the range of an identity (quiet speech vs shouting).
    Combine it with the best matching anchor examples, without allowing one
    outlier to replace the centroid or moving anchors into another cluster.
    """
    import numpy as np

    centers, scores = [], []
    for label in sorted(set(anchor_labels)):
        members = vectors[[anchors[i] for i, identity in enumerate(anchor_labels) if identity == label]]
        center = members.mean(axis=0)
        center /= max(float(np.linalg.norm(center)), 1e-8)
        centers.append(center)
        similarities = np.sort(vectors @ members.T, axis=1)
        examples = similarities[:, -min(3, len(members)):].mean(axis=1)
        scores.append(0.65 * (vectors @ center) + 0.35 * examples)
    scores = np.asarray(scores).T
    labels = list(np.argmax(scores, axis=1).astype(int))
    for anchor, label in zip(anchors, anchor_labels):
        labels[anchor] = label
    return labels, scores


def identify(audio_path: str, segments: list[dict], video_id: str, progress=None) -> list[dict]:
    """Run on CPU in the ONNX engine, then discard its weights before TTS."""
    import numpy as np
    import onnxruntime as ort

    model = verify_model(Path(MODELS_DIR) / "speaker-identification")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
    embeddings, valid_indices, pitches = [], [], {}
    with tempfile.TemporaryDirectory(prefix="speaker-audio-", dir=TMP_DIR) as directory:
        decoded = Path(directory) / "speech.wav"
        process = subprocess.Popen(
            [
                _binary("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-i",
                audio_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(decoded),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _, errors = communicate_process(
            video_id, process, label="speaker audio", timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS
        )
        if process.returncode:
            raise RuntimeError(errors[-500:])
        with wave.open(str(decoded), "rb") as stream:
            for index, segment in enumerate(segments):
                check_cancellation(video_id)
                start = max(0, int(float(segment.get("start") or 0) * 16000))
                end = min(stream.getnframes(), int(float(segment.get("end") or 0) * 16000), start + 8 * 16000)
                if end - start < 8000:
                    continue
                stream.setpos(min(start, stream.getnframes()))
                audio = np.frombuffer(stream.readframes(end - start), dtype="<i2").astype(np.float32)
                if np.sqrt(np.mean(audio**2)) < 20:
                    continue
                embedding = session.run(None, {"feats": _features(audio)[None, :, :]})[0].reshape(-1)
                if not np.isfinite(embedding).all():
                    raise RuntimeError("Speaker model returned invalid embeddings.")
                embeddings.append(embedding)
                valid_indices.append(index)
                # Pitch is used only to choose a natural target-language preset,
                # never as the identity classifier.
                estimates = []
                for offset in range(0, len(audio) - 640, 1600):
                    frame = audio[offset : offset + 640]
                    frame = (frame - frame.mean()) * np.hanning(640)
                    correlation = np.correlate(frame, frame, mode="full")[639:]
                    lag = 40 + int(np.argmax(correlation[40:229]))
                    if correlation[0] > 0 and correlation[lag] / correlation[0] > 0.65:
                        estimates.append(16000 / lag)
                pitches[index] = float(np.median(estimates)) if estimates else 150.0
                if progress:
                    progress(index + 1, len(segments))
    if not embeddings:
        raise RuntimeError("Không đủ lời nói rõ để nhận diện người nói. Hãy chọn một giọng đọc.")
    vectors = np.asarray(embeddings, dtype=np.float32)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-8)
    # Very short turns are useful for assignment, not for creating speakers:
    # their phonetic content dominates the embedding and fragments identities.
    anchors = [
        i
        for i, index in enumerate(valid_indices)
        if float(segments[index]["end"]) - float(segments[index]["start"]) >= 1.8
    ]
    if not anchors:
        anchors = [int(np.argmax([float(segments[i]["end"]) - float(segments[i]["start"]) for i in valid_indices]))]
    if len(anchors) > 192:
        anchors = [anchors[i] for i in np.linspace(0, len(anchors) - 1, 192, dtype=int)]
    anchor_labels = _cluster(vectors[anchors])
    labels, scores = _assign_identities(vectors, anchors, anchor_labels)
    label_by_index = dict(zip(valid_indices, labels))
    male = [
        "omnivoice:male",
        "omnivoice:deep",
        "omnivoice:male_mature",
        "omnivoice:male_high",
        "omnivoice:male_tenor",
        "omnivoice:male_narrator",
        "omnivoice:male_elder_high",
        "omnivoice:male_soft",
        "omnivoice:male_broadcast",
        "omnivoice:tech_presenter",
        "omnivoice:trailer_deep",
        "omnivoice:documentary",
    ]
    female = [
        "omnivoice:female",
        "omnivoice:female_low",
        "omnivoice:bright",
        "omnivoice:female_mature",
        "omnivoice:female_soprano",
        "omnivoice:female_narrator",
        "omnivoice:female_elder_high",
        "omnivoice:female_gentle",
        "omnivoice:female_confident",
        "omnivoice:show_host",
        "omnivoice:radio_warm",
    ]
    voices, counts = {}, {"male": 0, "female": 0}
    for label in sorted(set(labels)):
        pitch = np.median([pitches[index] for index, identity in label_by_index.items() if identity == label])
        kind = "female" if pitch >= 175 else "male"
        choices = female if kind == "female" else male
        voices[label] = choices[counts[kind] % len(choices)]
        counts[kind] += 1
    positions = {index: position for position, index in enumerate(valid_indices)}
    result = []
    for index, segment in enumerate(segments):
        label = label_by_index.get(index)
        if label is None:
            # Only unvoiced/very short fragments inherit the nearest reliable
            # turn. No new random identity is introduced for "Go!" etc.
            nearest = min(valid_indices, key=lambda i: abs(float(segments[i]["start"]) - float(segment["start"])))
            label = label_by_index[nearest]
        position = positions.get(index)
        confidence = round(max(0.0, float(scores[position, label])), 3) if position is not None else 0.0
        margin = (float(scores[position, label] - np.max(np.delete(scores[position], label)))
                  if position is not None and scores.shape[1] > 1 else confidence)
        result.append(
            {
                **segment,
                "speaker_id": f"speaker-{label + 1}",
                "speaker_voice": voices[label],
                "speaker_confidence": confidence,
                "speaker_uncertain": confidence < 0.55 or margin < 0.10,
            }
        )
    return result


def _valid_map(value, segments) -> bool:
    from haizflow.pipeline.omnivoice_tts import OMNIVOICE_VOICE_INSTRUCTIONS

    valid = (
        isinstance(value, list)
        and len(value) == len(segments)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("speaker_id"), str)
            and bool(item["speaker_id"])
            and item.get("speaker_voice") in OMNIVOICE_VOICE_INSTRUCTIONS
            and item.get("start") == source.get("start")
            and item.get("end") == source.get("end")
            and item.get("text") == source.get("text")
            for item, source in zip(value, segments)
        )
    )
    if not valid:
        return False
    voices = {}
    for item in value:
        speaker = item["speaker_id"]
        voice = item["speaker_voice"]
        if speaker in voices and voices[speaker] != voice:
            return False
        voices[speaker] = voice
    return True


def prepare_speakers(audio_path: str, segments: list[dict], video_id: str, progress=None) -> list[dict]:
    """Persist a source-bound map, independent of translated text and edits."""
    from haizflow.services.external_tasks import run_external_task
    from haizflow.services.external_engine import shared_external_engine_pool

    verify_model(Path(MODELS_DIR) / "speaker-identification")
    stat = Path(audio_path).stat()
    key = hashlib.sha256(
        json.dumps(
            [IDENTITY_VERSION, str(Path(audio_path).resolve()), stat.st_size, stat.st_mtime_ns, segments],
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    path = Path(audio_path).parent / f"speaker-map-{key}.json"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if _valid_map(cached, segments):
            return cached
    except (OSError, ValueError, TypeError):
        pass
    try:
        result = run_external_task(
            "speaker",
            "speaker_identification",
            {"audio_path": audio_path, "segments": segments, "video_id": video_id},
            video_id,
            progress_callback=progress,
            isolate_source=True,
        )
        if result is None:
            raise RuntimeError("Cần cài bộ xử lý ONNX để nhận diện người nói.")
        identified = result.get("segments")
        if not _valid_map(identified, segments):
            raise RuntimeError("Speaker engine returned an invalid identity map.")
    finally:
        shared_external_engine_pool().release({"speaker"})
    descriptor, name = tempfile.mkstemp(prefix=".speaker-map-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(identified, stream, ensure_ascii=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return identified
