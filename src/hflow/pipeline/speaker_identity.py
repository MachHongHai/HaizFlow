"""Offline speaker identities; no source-language audio is passed to TTS."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from hflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, MODELS_DIR, TMP_DIR
from hflow.pipeline.process_registry import check_cancellation, communicate_process
from hflow.utils.ffmpeg import _binary
from hflow.utils.atomic_file import atomic_json

from hflow.core.bundled_models import MODEL_FILE, MODEL_SIZE, MODEL_SHA256, MODEL_REVISION, MODEL_URL as MODEL_URL
IDENTITY_VERSION = "wespeaker-stable-target-voices-v9-float-subturn-childstyle"
FALLBACK_VOICE = "omnivoice:female_gentle"


def _pitch_samples(audio, *, preserve_gaps=False):
    """Reliable F0 frames at 16 kHz, using YIN's normalized difference.

    Unlike windowed autocorrelation peaks, the first periodic minimum is
    less prone to selecting a strong second harmonic as the fundamental.
    Mathematical reference: de Cheveigne & Kawahara, JASA 111 (2002).
    Work is bounded by the eight-second turn supplied by the caller.
    """
    import numpy as np

    audio = np.asarray(audio, dtype=np.float64)
    if len(audio) < 1024 or not np.isfinite(audio).all():
        return []
    frames = np.lib.stride_tricks.sliding_window_view(audio, 1024)[::800].copy()
    frames -= frames.mean(axis=1, keepdims=True)
    voiced = np.sqrt(np.mean(frames ** 2, axis=1)) >= 20
    if not voiced.any():
        return []
    if not preserve_gaps:
        frames = frames[voiced]
    max_lag = 229
    correlation = np.fft.irfft(np.abs(np.fft.rfft(frames, n=2048)) ** 2, n=2048)[:, :max_lag + 1]
    energy = np.concatenate((np.zeros((len(frames), 1)), np.cumsum(frames ** 2, axis=1)), axis=1)
    lags = np.arange(1, max_lag + 1)
    difference = np.maximum(0, energy[:, 1024 - lags] + energy[:, -1, None]
                            - energy[:, lags] - 2 * correlation[:, 1:])
    difference /= 1024 - lags
    normalized = difference * lags / np.maximum(np.cumsum(difference, axis=1), 1e-12)
    estimates = []
    for frame_index, curve in enumerate(normalized):
        if preserve_gaps and not voiced[frame_index]:
            estimates.append(float("nan"))
            continue
        count = len(estimates)
        # Only accept clearly periodic frames; noise/silence is not evidence
        # of either a male or female voice.
        for index in range(39, max_lag - 1):
            if curve[index] < 0.18 and curve[index] <= curve[index - 1] and curve[index] < curve[index + 1]:
                denominator = curve[index - 1] - 2 * curve[index] + curve[index + 1]
                offset = (0.5 * (curve[index - 1] - curve[index + 1]) / denominator
                          if denominator > 1e-12 else 0.0)
                estimates.append(16000 / (index + 1 + float(np.clip(offset, -.5, .5))))
                break
        if preserve_gaps and len(estimates) == count:
            estimates.append(float("nan"))
    return estimates


def _voice_pitch_profile(samples):
    """Choose a preset family, not a person's gender, from voiced evidence.

    A raised/shouted phrase should not change the whole speaker to a female
    preset. Retain their lower, habitual register across reliable frames.
    Overlapping registers and sparse evidence are explicitly uncertain.
    """
    import numpy as np

    values = np.asarray(samples, dtype=np.float64)
    values = values[np.isfinite(values) & (values >= 70) & (values <= 400)]
    if len(values) < 8:
        return "male", True, None
    lower, median, upper = np.percentile(values, [25, 50, 75])
    kind = "male" if lower < 175 else "female"
    uncertain = len(values) < 20 or (160 <= lower <= 200) or upper - lower > 85
    return kind, bool(uncertain), round(float(median), 1)


def _speaker_voice_profile(turn_samples):
    """Retain sustained low-register evidence even when shouting dominates.

    Pooling every frame weights long/high phrases too heavily. A habitual
    register must be sustained within one turn, not assembled from isolated
    subharmonic errors or from the ends of several unrelated turns. This
    chooses an acoustic preset family, not a person's gender identity.
    """
    import numpy as np

    turns = [np.asarray(samples, dtype=np.float64) for samples in turn_samples]
    kind, uncertain, pitch = _voice_pitch_profile([value for turn in turns for value in turn])
    if _has_sustained_low_register(turns):
        return "male", uncertain or kind != "male", pitch
    return kind, uncertain, pitch


def _has_sustained_low_register(turns):
    import numpy as np

    for turn in turns:
        turn = np.asarray(turn, dtype=np.float64)
        if len(turn) < 8:
            continue
        # Require 400 ms of periodic evidence within at most one second.
        # Normal speech has unvoiced consonants: allow gaps under 200 ms,
        # but never bridge a higher-register sample or a long silent gap.
        for start in range(len(turn) - 7):
            window = turn[start:start + 20]
            higher_or_invalid = np.flatnonzero(np.isfinite(window) & ((window < 70) | (window >= 160)))
            if len(higher_or_invalid):
                window = window[:higher_or_invalid[0]]
            positions = np.flatnonzero(np.isfinite(window))
            if len(positions) < 8:
                continue
            values = window[positions]
            gaps = ~np.isfinite(window[positions[0]:positions[-1] + 1])
            long_gap = len(gaps) >= 4 and np.lib.stride_tricks.sliding_window_view(gaps, 4).all(axis=1).any()
            if not long_gap and np.all((values >= 70) & (values < 160)) and np.ptp(values) <= 45:
                return True
    return False


def verify_model(root: Path) -> Path:
    from hflow.core.model_integrity import _verify

    if root.resolve() == bundled_model_root().resolve():
        from hflow.core.bundled_models import verify_speaker
        return verify_speaker(root)
    _verify(
        root, kind="speaker identification", revision=MODEL_REVISION, expected={MODEL_FILE: (MODEL_SIZE, MODEL_SHA256)}
    )
    return root / MODEL_FILE


def bundled_model_root() -> Path:
    from hflow.core.paths import bundle_root, project_root
    import sys

    base = bundle_root() / "models" if getattr(sys, "frozen", False) else project_root() / "build" / "bundled-models"
    return base / "speaker-identification"


def model_root() -> Path:
    """Prefer the immutable Core asset; retain existing development storage."""
    bundled = bundled_model_root()
    return bundled if (bundled / MODEL_FILE).is_file() else Path(MODELS_DIR) / "speaker-identification"


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


def _reconcile_expressive_groups(vectors, labels):
    """Reconcile style-split identities using independent turn exemplars.

    Complete-link anchor clustering can split quiet and shouted speech.
    Merge only strongly matching aggregate identities with corroborating
    turns on BOTH sides, and a margin over competing identities. Never use
    pitch or adjacency as evidence that two turns belong to the same person.
    Representatives are bounded so long videos cannot produce an N² matrix.
    """
    import numpy as np

    identities = sorted(set(labels))
    if len(identities) < 2:
        return labels
    members = [np.flatnonzero(np.asarray(labels) == identity) for identity in identities]
    centers = np.asarray([vectors[group].mean(axis=0) for group in members])
    centers /= np.maximum(np.linalg.norm(centers, axis=1, keepdims=True), 1e-8)
    similarity = centers @ centers.T
    np.fill_diagonal(similarity, -np.inf)
    allowed = np.eye(len(identities), dtype=bool)
    candidates = []
    for left in range(len(identities)):
        for right in range(left + 1, len(identities)):
            score = float(similarity[left, right])
            if score < .70 or min(len(members[left]), len(members[right])) < 2:
                continue
            others = [i for i in range(len(identities)) if i not in (left, right)]
            competing = max((max(similarity[left, i], similarity[right, i]) for i in others), default=-1)
            if score - competing < .12:
                continue
            examples = [vectors[group[np.linspace(0, len(group) - 1, min(24, len(group)), dtype=int)]]
                        for group in (members[left], members[right])]
            matches = examples[0] @ examples[1].T >= .52
            if np.count_nonzero(matches.any(axis=0)) < 2 or np.count_nonzero(matches.any(axis=1)) < 2:
                continue
            allowed[left, right] = allowed[right, left] = True
            candidates.append((score, left, right))
    groups = [{i} for i in range(len(identities))]
    for _score, left, right in sorted(candidates, reverse=True):
        left_group = next(group for group in groups if left in group)
        right_group = next(group for group in groups if right in group)
        if left_group is right_group:
            continue
        # Do not chain A≈B≈C into A=C when A/C have no direct evidence.
        if all(allowed[a, b] for a in left_group for b in right_group):
            left_group.update(right_group)
            groups.remove(right_group)
    remap = {identities[old]: new for new, group in enumerate(sorted(groups, key=min)) for old in group}
    return [remap[label] for label in labels]


def _label_turns(vectors, valid_indices, segments):
    import numpy as np

    # Prefer full turns so phonetic variation in tiny fragments does not
    # create extra people; do not collapse a dialogue with only short turns.
    anchors = [i for i, index in enumerate(valid_indices)
               if float(segments[index]["end"]) - float(segments[index]["start"]) >= 1.8]
    if not anchors:
        anchors = list(range(len(valid_indices)))
    if len(anchors) > 192:
        anchors = [anchors[i] for i in np.linspace(0, len(anchors) - 1, 192, dtype=int)]
    anchor_labels = _cluster(vectors[anchors])
    labels, scores = _assign_identities(vectors, anchors, anchor_labels)
    reconciled = _reconcile_expressive_groups(vectors, labels)
    if reconciled != labels:
        anchor_labels = [reconciled[anchor] for anchor in anchors]
        _assignments, scores = _assign_identities(vectors, anchors, anchor_labels)
        labels = reconciled
    # Long anchors may represent only ONE person. Never force every short
    # stranger into that person's identity just because no other anchor exists.
    unsupported = [i for i, index in enumerate(valid_indices) if i not in anchors
                   and float(segments[index]["end"]) - float(segments[index]["start"]) >= .50
                   and float(scores[i].max()) < (.40 if float(segments[index]["end"]) - float(segments[index]["start"]) >= .75 else .30)]
    if unsupported and len(anchors) < 192:
        unsupported.sort(key=lambda i: (float(scores[i].max()), i))
        additions = unsupported[:192 - len(anchors)]
        new_labels = _cluster(vectors[additions])
        original_labels, supported = labels[:], scores.max(axis=1) >= .40
        next_label = max(anchor_labels) + 1
        anchors += additions
        anchor_labels += [next_label + label for label in new_labels]
        labels, scores = _assign_identities(vectors, anchors, anchor_labels)
        # Adding previously unrepresented people must not redistribute already
        # reliable memberships or discard the habitual register of an actor.
        labels = [original_labels[i] if supported[i] else label for i, label in enumerate(labels)]
    return labels, scores


def _acoustic_voice_profile(turns, probabilities):
    """Use learned timbre consensus, not a pitch cutoff, when available.

    Abstain on contradictory/weak evidence; deterministic gentle-female
    fallback does not read the single-narrator UI selection.
    """
    import numpy as np

    kind, uncertain, pitch = _speaker_voice_profile(turns)
    evidence = [(float(probability), min(40, sum(np.isfinite(turn))))
                for turn, probability in zip(turns, probabilities)
                if probability is not None and np.isfinite(probability)
                and (sum(np.isfinite(turn)) >= 3 or (len(turn) >= 8 and max(probability, 1 - probability) >= .98))]
    if not evidence:
        return (kind if not uncertain else "unknown"), uncertain, pitch, None
    values, _weights = np.asarray(evidence).T
    # Weak/shouted/noisy turns should inherit the family's clear evidence,
    # not pull its posterior towards an arbitrary 50/50 pitch-based choice.
    clear = (values >= .70) | (values <= .30)
    # One long excited phrase must not outweigh several independent quiet
    # turns. A robust per-turn vote also tolerates one classifier outlier.
    probability = float(np.median(values[clear])) if clear.any() else float(np.median(values))
    # Stylized/animated voices are outside this human-speech model's domain.
    # Keep the independently sustained habitual register that already fixed
    # expressive male dialogue; the model must not undo that evidence.
    if _has_sustained_low_register(turns):
        return "male", False, pitch, round(probability, 3)
    opposing = min(np.count_nonzero(values[clear] >= .70), np.count_nonzero(values[clear] <= .30)) / max(1, np.count_nonzero(clear))
    if opposing >= .35:
        return "unknown", True, pitch, round(probability, 3)
    if probability >= .80:
        return "male", False, pitch, round(probability, 3)
    if probability <= .20:
        return "female", False, pitch, round(probability, 3)
    if probability >= .70 and np.count_nonzero(values >= .70) >= 2 and opposing < .35:
        return "male", True, pitch, round(probability, 3)
    if probability <= .30 and np.count_nonzero(values <= .30) >= 2 and opposing < .35:
        return "female", True, pitch, round(probability, 3)
    # Sustained habitual low register is independent supporting evidence,
    # but do not override a confidently opposing learned profile.
    if kind == "male" and not uncertain and probability >= .40:
        return "male", False, pitch, round(probability, 3)
    return "unknown", True, pitch, round(probability, 3)


def _resolve_voice_families(vectors, labels, profiles):
    """Corroborate uncertain timbre from similar, independently sampled groups.

    Style-split identities remain distinct. Require several acoustic matches
    on both sides and a margin over the opposite family; never infer from
    dialogue order, subtitle meaning, the UI default, or gender alone.
    Newly resolved groups cannot become anchors (no transitive propagation).
    """
    import numpy as np

    members = {label: np.flatnonzero(np.asarray(labels) == label) for label in profiles}
    centers = {label: vectors[group].mean(axis=0) for label, group in members.items()}
    centers = {label: center / max(float(np.linalg.norm(center)), 1e-8) for label, center in centers.items()}
    resolved = dict(profiles)
    for label, profile in profiles.items():
        if profile[0] != "unknown":
            continue
        candidates = []
        for anchor, known in profiles.items():
            if known[0] == "unknown" or len(members[anchor]) < 2:
                continue
            similarity = float(centers[label] @ centers[anchor])
            short_single = len(members[label]) == 1
            if similarity < (.40 if short_single else .62):
                continue
            target = vectors[members[label][np.linspace(0, len(members[label]) - 1, min(24, len(members[label])), dtype=int)]]
            reference = vectors[members[anchor][np.linspace(0, len(members[anchor]) - 1, min(24, len(members[anchor])), dtype=int)]]
            matches = target @ reference.T >= .50
            if (np.count_nonzero(matches.any(axis=0)) >= 2
                    and np.count_nonzero(matches.any(axis=1)) >= (1 if short_single else 2)):
                candidates.append((similarity, known[0]))
        if not candidates:
            continue
        score, kind = max(candidates)
        opposite = max((float(centers[label] @ centers[anchor]) for anchor, known in profiles.items()
                        if known[0] not in {"unknown", kind}), default=-1)
        if score - opposite >= .12:
            resolved[label] = (kind, True, profile[2], profile[3])
    return resolved


def _clause_candidates(segment, audio):
    """Suggest phrase boundaries at actual quiet gaps, never equal time slices.

    This is only a hypothesis; identify() accepts it only when independent
    timbre AND speaker-embedding evidence corroborate a speaker change.
    """
    import numpy as np
    text = str(segment.get("text") or "")
    clauses = [part.strip() for part in re.split(r"(?<=[!?。！？])\s*|(?<=\.)\s+(?=[A-Z])", text) if part.strip()]
    if not 1 < len(clauses) <= 6:
        return []
    start, end = float(segment['start']), float(segment['end'])
    if not .55 <= end - start <= 8 or len(audio) < 3200 * len(clauses):
        return []
    weights = [max(1, len(re.findall(r"[^\W_]+", clause))) for clause in clauses]
    edges = [0]
    frame = 320
    rms = np.sqrt(np.mean(audio[:len(audio)//frame*frame].reshape(-1,frame)**2,axis=1))
    for fraction in np.cumsum(weights)[:-1] / sum(weights):
        expected = int(fraction * len(audio))
        radius = min(int(.3 * 16000), int(len(audio) * .22))
        low = max(edges[-1] + 3200, expected - radius)
        high = min(len(audio) - 3200 * (len(clauses) - len(edges)), expected + radius)
        choices = np.arange((low + frame - 1)//frame, high//frame + 1)
        choices = choices[(choices > 0) & (choices + 1 < len(rms))]
        if not len(choices):
            return []
        smooth = (rms[choices-1] + rms[choices] + rms[choices+1]) / 3
        best = choices[int(np.argmin(smooth))]
        if rms[best] > np.median(rms) * .5:
            return []  # Do not manufacture a change inside uninterrupted speech.
        edges.append(int(best * frame))
    edges.append(len(audio))
    return [{**segment, 'start': start + edges[i]/16000, 'end': start + edges[i+1]/16000,
             'text': clause} for i, clause in enumerate(clauses)]


def _embedding_input(audio):
    """Very short turns are evidence, not automatically the female fallback.

    Repeat ONLY the existing fbank for <500ms input (no adjacent speaker audio).
    This bounds the convolution/pooling input in the same way as WeSpeaker's
    official subsegment extractor; repetition does not add confidence/evidence.
    """
    import numpy as np
    features = _features(audio)
    return np.resize(features, (150, 80)) if len(audio) < 8000 else features


def _style_reference_bank(session, segments, video_id):
    """Coarse target-timbre evidence, not reference-person identification.

    Adult gender classifiers systematically treat high childlike voices as
    female. Compare against several LOCAL same-language child/adult presets
    before assigning an adult preset. No download, Torch, GPU, or face inference.
    """
    import numpy as np
    from collections import Counter
    from hflow.pipeline.omnivoice_tts import _preset_reference
    language = Counter(str(item.get('language') or item.get('source_language') or 'en') for item in segments).most_common(1)[0][0]
    groups = {'adult': ['male','deep','male_high','male_soft','female','female_low','bright','female_gentle'],
              'child': ['child','cartoon','child_soft','child_bright']}
    bank = {}
    for kind,names in groups.items():
        vectors = []
        for name in names:
            path,_ = _preset_reference('omnivoice:'+name,language)
            if not path:
                continue
            check_cancellation(video_id)
            process = subprocess.Popen([_binary('ffmpeg'),'-v','error','-i',path,'-t','8','-ac','1','-ar','16000',
                                        '-f','f32le','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            raw,_ = communicate_process(video_id,process,label='speaker style reference',timeout_seconds=MEDIA_PROCESS_TIMEOUT_SECONDS)
            if process.returncode:
                continue
            audio = np.frombuffer(raw,dtype='<f4') * 32768
            if len(audio) < 8000:
                continue
            vector = session.run(_features(audio)[None])[0].reshape(-1)
            vectors.append(vector / max(np.linalg.norm(vector),1e-8))
        if len(vectors) >= 2:
            bank[kind] = np.array(vectors)
    return bank


def _childlike_evidence(vectors, bank):
    import numpy as np
    if not all(kind in bank for kind in ('adult','child')):
        return np.zeros(len(vectors),dtype=bool)
    child = np.sort(vectors @ bank['child'].T,axis=1)[:,-2:]
    adult = np.sort(vectors @ bank['adult'].T,axis=1)[:,-2:]
    return (child[:,-1] >= .25) & (child.mean(axis=1) >= .20) & (child.mean(axis=1)-adult.mean(axis=1) >= .08)


def _separate_turn_constraints(vectors, labels, valid_indices, cannot_link, childlike):
    """Don't merge corroborated speaker changes or clear child/adult styles.

    Existing memberships are otherwise retained. Rebuild scores from bounded
    exemplars; do not use copied/rotating voice labels as acoustic evidence.
    """
    import numpy as np
    keys = [(label, bool(childlike[i])) for i,label in enumerate(labels)]
    positions = {index:position for position,index in enumerate(valid_indices)}
    collisions = []
    for left,right in cannot_link:
        a,b = positions.get(left),positions.get(right)
        if a is not None and b is not None and keys[a] == keys[b]:
            keys[b] = ('pending-change',b)
            collisions.append(b)
    if collisions:
        # Cluster new change exemplars acoustically, not by dialogue order.
        # At most 192 anchors and 576 resulting families for a long source.
        subset = vectors[collisions]
        anchors = np.linspace(0,len(collisions)-1,min(192,len(collisions)),dtype=int).tolist()
        additional = _cluster(subset[anchors])
        assigned,_ = _assign_identities(subset,anchors,additional)
        for position,label in zip(collisions,assigned):
            keys[position] = ('change',label)
    unique = list(dict.fromkeys(keys))
    refined = [unique.index(key) for key in keys]
    if refined == labels:
        return labels,None
    anchors = []
    for label in range(len(unique)):
        members = np.flatnonzero(np.array(refined)==label)
        anchors.extend(members[np.linspace(0,len(members)-1,min(16,len(members)),dtype=int)].tolist())
    _,scores = _assign_identities(vectors,anchors,[refined[i] for i in anchors])
    return refined,scores


def identify(audio_path: str, segments: list[dict], video_id: str, progress=None, *,
             model_directory: str = "", runtime_callback=None) -> list[dict]:
    """Use the built-in CPU backend in an isolated worker; release before TTS."""
    import numpy as np
    from hflow.utils.float_pcm import FloatPcmReader
    from hflow.pipeline.speaker_runtime import SpeakerSession, VoiceProfileSession
    from hflow.core.voice_profile_model import MODEL_FILE as PROFILE_FILE, verify_voice_profile

    model = verify_model(Path(model_directory) if model_directory else model_root())
    session = SpeakerSession(model, runtime_callback)
    profile_session = VoiceProfileSession(verify_voice_profile(model.parent)) if (model.parent / PROFILE_FILE).is_file() else None
    embeddings, valid_indices, pitches, voice_probabilities = [], [], {}, []
    source_segments = segments
    parent_groups = []
    cannot_link = []
    with tempfile.TemporaryDirectory(prefix="speaker-audio-", dir=TMP_DIR) as directory:
        decoded = Path(directory) / "speech.pcm"
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
                "pcm_f32le",
                "-f",
                "f32le",
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
        with FloatPcmReader(decoded) as stream:
            expanded = []
            for segment in source_segments:
                check_cancellation(video_id)
                start = max(0, int(float(segment.get("start") or 0) * 16000))
                end = min(stream.frames, int(float(segment.get("end") or 0) * 16000), start + 8 * 16000)
                stream.seek(min(start,stream.frames))
                audio = stream.read(max(0,end-start),dtype='float32') * 32768
                candidates = _clause_candidates(segment,audio) if profile_session else []
                accepted = False
                changes = []
                if candidates:
                    probabilities, vectors = [], []
                    for candidate in candidates:
                        left = max(0, round((candidate['start']-float(segment['start']))*16000))
                        right = round((candidate['end']-float(segment['start']))*16000)
                        chunk = audio[left:right]
                        probabilities.append(profile_session.male_probability(chunk))
                        embedding = session.run(_embedding_input(chunk)[None])[0].reshape(-1)
                        vectors.append(embedding / max(np.linalg.norm(embedding),1e-8))
                    changes = [i for i,(a,b) in enumerate(zip(probabilities,probabilities[1:]))
                               if abs(a-b) >= .55 and min(a,b) <= .20 and max(a,b) >= .70
                                   and float(vectors[i] @ vectors[i+1]) < .45
                               ]
                    accepted = bool(changes)
                group = list(range(len(expanded),len(expanded)+(len(candidates) if accepted else 1)))
                if accepted:
                    cannot_link.extend((group[i],group[i+1]) for i in changes)
                expanded.extend(candidates if accepted else [segment])
                parent_groups.append(group)
            segments = expanded
            for index, segment in enumerate(segments):
                check_cancellation(video_id)
                start = max(0, int(float(segment.get("start") or 0) * 16000))
                end = min(stream.frames, int(float(segment.get("end") or 0) * 16000), start + 8 * 16000)
                if end - start < 2880:
                    continue
                stream.seek(min(start, stream.frames))
                audio = stream.read(end - start,dtype='float32') * 32768
                if np.sqrt(np.mean(audio**2)) < 20:
                    continue
                embedding = session.run(_embedding_input(audio)[None, :, :])[0].reshape(-1)
                if not np.isfinite(embedding).all():
                    raise RuntimeError("Speaker model returned invalid embeddings.")
                embeddings.append(embedding)
                valid_indices.append(index)
                # Pitch is used only to choose a natural target-language preset,
                # never as the identity classifier.
                pitches[index] = _pitch_samples(audio, preserve_gaps=True)
                voice_probabilities.append(profile_session.male_probability(audio) if profile_session else None)
                if progress:
                    progress(index + 1, len(segments))
    if not embeddings:
        return [{**segment, "speaker_id": f"unresolved-{index + 1}", "speaker_voice": FALLBACK_VOICE,
                 "speaker_voice_uncertain": True, "speaker_pitch_hz": None, "speaker_male_probability": None,
                 "speaker_profile_backend": "ecapa-q8" if profile_session else "pitch-fallback",
                 "speaker_profile_inherited": False, "speaker_voice_fallback": True,
                 "speaker_confidence": 0.0, "speaker_uncertain": True}
                for index, segment in enumerate(source_segments)]
    vectors = np.asarray(embeddings, dtype=np.float32)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-8)
    labels, scores = _label_turns(vectors, valid_indices, segments)
    bank = _style_reference_bank(session,segments,video_id) if profile_session else {}
    childlike = _childlike_evidence(vectors,bank)
    labels,new_scores = _separate_turn_constraints(vectors,labels,valid_indices,cannot_link,childlike)
    if new_scores is not None:
        scores = new_scores
    label_by_index = dict(zip(valid_indices, labels))
    male = [
        "omnivoice:male",
        "omnivoice:deep",
        "omnivoice:male_soft",
        "omnivoice:male_high",
    ]
    female = [
        "omnivoice:female",
        "omnivoice:female_low",
        "omnivoice:bright",
        "omnivoice:female_gentle",
    ]
    voices, pitch_profiles, counts, acoustic_profiles = {}, {}, {"male": 0, "female": 0,"child":0}, {}
    positions = {index: position for position, index in enumerate(valid_indices)}
    for label in sorted(set(labels)):
        members = [index for index, identity in label_by_index.items() if identity == label]
        reliable = [index for index in members if float(scores[positions[index],label]) >= .40
                    and float(segments[index]['end']) - float(segments[index]['start']) >= .5]
        members = reliable or members
        turns = [pitches[index] for index in members]
        probabilities = [voice_probabilities[positions[index]] for index in members]
        profile = _acoustic_voice_profile(turns, probabilities)
        child_profile = bool(np.all(childlike[[positions[index] for index in members]]))
        if child_profile:
            profile = ('child',True,profile[2],profile[3])
        if not child_profile and len(turns) == 1 and len(turns[0]) < 20 and not _has_sustained_low_register(turns):
            finite = np.asarray(turns[0])[np.isfinite(turns[0])]
            corroborated_low = (len(finite) >= 3 and float(np.median(finite)) < 160
                                and profile[3] is not None and profile[3] >= .80)
            if not corroborated_low and (profile[3] is None or max(profile[3], 1 - profile[3]) < .95):
                profile = ("unknown", True, profile[2], profile[3])
        acoustic_profiles[label] = profile
    resolved_profiles = _resolve_voice_families(vectors, labels, acoustic_profiles)
    profile_members = {label: labels.count(label) for label in resolved_profiles}
    for label, (kind, uncertain, pitch, probability) in resolved_profiles.items():
        pitch_profiles[label] = (uncertain, pitch, probability)
        if kind == "unknown":
            voices[label] = FALLBACK_VOICE
            continue
        choices = ['omnivoice:child_soft','omnivoice:child_bright','omnivoice:child'] if kind == 'child' else female if kind == "female" else male
        voices[label] = choices[counts[kind] % len(choices)]
        counts[kind] += 1
    result = []
    for index, segment in enumerate(segments):
        label = label_by_index.get(index)
        if label is None:
            # A nearest turn is used only for diagnostics. With no embedding,
            # this fragment is explicitly unresolved and uses gentle fallback.
            nearest = min(valid_indices, key=lambda i: abs(float(segments[i]["start"]) - float(segment["start"])))
            label = label_by_index[nearest]
        position = positions.get(index)
        confidence = round(max(0.0, float(scores[position, label])), 3) if position is not None else 0.0
        margin = (float(scores[position, label] - np.max(np.delete(scores[position], label)))
                  if position is not None and scores.shape[1] > 1 else confidence)
        kind = resolved_profiles[label][0]
        opposing_score = max((float(scores[position, other]) for other, other_profile in resolved_profiles.items()
                              if other_profile[0] not in {kind, "unknown"}
                              and (profile_members[other] >= 2 or float(scores[position, other]) >= .40)),
                             default=-1) if position is not None else 1
        # Sub-500ms fragments need a clear margin over the opposite family;
        # padding is not permission to create a confident new identity.
        short = float(segment['end']) - float(segment['start']) < .5
        finite = np.asarray(pitches.get(index, [])); finite = finite[np.isfinite(finite)]
        stable_low_short = short and len(finite) >= 4 and np.median(finite) < 150 and np.ptp(finite) < 40
        family_supported = kind != "unknown" and (confidence >= .40 or
            (confidence >= (.25 if stable_low_short and kind == 'male' else .30)
             and confidence - opposing_score >= (.08 if stable_low_short and kind == 'male' else .12)))
        result.append(
            {
                **segment,
                "speaker_id": f"speaker-{label + 1}" if family_supported else f"unresolved-{index + 1}",
                "speaker_voice": voices[label] if family_supported else FALLBACK_VOICE,
                "speaker_voice_uncertain": pitch_profiles[label][0] or not family_supported,
                "speaker_pitch_hz": pitch_profiles[label][1],
                "speaker_male_probability": pitch_profiles[label][2],
                "speaker_profile_backend": "ecapa-q8" if profile_session else "pitch-fallback",
                "speaker_timbre_style": 'child-like' if kind == 'child' else kind,
                "speaker_profile_inherited": resolved_profiles[label] != acoustic_profiles[label],
                "speaker_voice_fallback": not family_supported,
                "speaker_confidence": confidence,
                "speaker_uncertain": confidence < 0.55 or margin < 0.10
                or float(segment["end"]) - float(segment["start"]) < 1.8,
            }
        )
    folded = []
    for source, group in zip(source_segments,parent_groups):
        turns = [result[i] for i in group]
        parent = {**source, **{key:value for key,value in turns[0].items() if key.startswith('speaker_')}}
        if len(turns) > 1:
            parent['speaker_turns'] = turns
        folded.append(parent)
    return folded


def _valid_map(value, segments) -> bool:
    from hflow.pipeline.omnivoice_tts import OMNIVOICE_VOICE_INSTRUCTIONS

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
        turns = item.get('speaker_turns') or []
        if turns:
            if not isinstance(turns,list) or not 2 <= len(turns) <= 6:
                return False
            import math
            try:
                previous, parent_end = float(item['start']),float(item['end'])
                if not math.isfinite(previous) or not math.isfinite(parent_end):
                    return False
            except (TypeError,ValueError,KeyError):
                return False
            for turn in turns:
                if (not isinstance(turn,dict) or not isinstance(turn.get('speaker_id'),str)
                        or not turn['speaker_id'] or turn.get('speaker_voice') not in OMNIVOICE_VOICE_INSTRUCTIONS
                        or not isinstance(turn.get('text'),str) or not turn['text'].strip()):
                    return False
                try:
                    start,end = float(turn['start']),float(turn['end'])
                    if (not math.isfinite(start) or not math.isfinite(end) or abs(start-previous) > .025
                            or end <= start or end > parent_end+.025):
                        return False
                    previous = end
                except (TypeError,ValueError,KeyError):
                    return False
            if abs(previous-parent_end) > .025:
                return False
        for turn in [item,*turns]:
            speaker = turn["speaker_id"]
            voice = turn["speaker_voice"]
            if speaker in voices and voices[speaker] != voice:
                return False
            voices[speaker] = voice
    return True


def prepare_speakers(audio_path: str, segments: list[dict], video_id: str, progress=None) -> list[dict]:
    """Persist a source-bound map, independent of translated text and edits."""
    from hflow.services.external_tasks import run_external_task
    from hflow.services.external_engine import shared_external_engine_pool
    # CPU has a lower cold-load cost and turn latency on real speech.
    selected_device = "cpu"
    from hflow.core.voice_profile_model import MODEL_FILE as PROFILE_FILE
    directory = model_root()
    profile_backend = "ecapa-q8" if (directory / PROFILE_FILE).is_file() else "pitch-fallback"
    stat = Path(audio_path).stat()
    key = hashlib.sha256(
        json.dumps(
            [IDENTITY_VERSION, profile_backend, str(Path(audio_path).resolve()), stat.st_size, stat.st_mtime_ns, segments],
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
    # A validated source-bound map is sufficient for subtitle-only edits.
    # Do not re-verify/load the model when only regenerated speech needs it.
    verify_model(directory)
    try:
        result = run_external_task(
            "speaker",
            "speaker_identification",
            {"audio_path": audio_path, "segments": segments, "video_id": video_id,
             "model_directory": str(directory), "device": selected_device},
            video_id,
            context={"device": selected_device},
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
    atomic_json(path, identified)
    return identified
