"""Voice synthesis shared by automatic and manual workflows."""

import json
import os
import re
import unicodedata
import tempfile
from pathlib import Path

from haizflow.services.video_store import get_video, log_to_video


def resolve_tts_provider(provider: str, target_language: str) -> str:
    """Resolve explicit backends without changing a user's provider choice."""
    normalized = str(provider or "omnivoice").strip().lower()
    if normalized == "edge":
        return "edge"
    if normalized in {"vieneu", "vieneu-gpu"}:
        from haizflow.core.vieneu_voices import unsupported_language_notice

        notice = unsupported_language_notice(normalized, target_language)
        if notice:
            raise ValueError(notice[1])
        return "vieneu"
    if normalized in {"omnivoice", "omnivoice-gpu", "auto"}:
        return "omnivoice"
    raise ValueError(f"Unsupported TTS provider: {provider}")


def normalize_voice(voice: str) -> str:
    """Map an old Edge voice to a local preset when opening an older project."""
    selected = str(voice or "").strip()
    if selected.startswith("omnivoice:"):
        return selected
    if selected in {"vi-VN-NamMinhNeural", "en-US-GuyNeural", "zh-CN-YunxiNeural"}:
        return "omnivoice:male"
    return "omnivoice:female"


def voice_selection_identity(voice: str, speaker_mode: str) -> str:
    """Keep the single-narrator UI preset out of multi-speaker cache keys."""
    return "per-speaker" if speaker_mode == "multiple" else str(voice or "")


def preprocess_text_for_tts(text: str) -> str:
    """Normalize invisible and punctuation characters without changing words."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(
        str.maketrans({
            "\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
            "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2013": ",", "\u2014": ",", "\u2026": "...",
        })
    )
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[-1] not in ".!?,;:。！？；：":
        text += "."
    return text


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _is_valid_mp3(path: str) -> bool:
    """Reject zero-byte and partial synthesis results before timeline assembly."""
    try:
        if os.path.getsize(path) < 512:
            return False
        with open(path, "rb") as file:
            header = file.read(3)
    except OSError:
        return False
    if header == b"ID3":
        return True
    return len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0


def _speaker_utterance_plan(segment: dict, source: dict) -> list[dict]:
    """Keep edited subtitle identity matching time-based, including sub-turns."""
    turns = source.get('speaker_turns') or []
    if not turns:
        return [{"text":str(segment['text']),"voice":source.get('speaker_voice'),"speaker_id":source.get('speaker_id'),
                 "offset_ms":0,"duration_ms":max(1,round((float(segment.get('end',0))-float(segment.get('start',0)))*1000))}]
    clauses = [part.strip() for part in re.split(r"(?<=[!?。！？])\s*|(?<=\.)\s+(?=[A-ZÀ-Ỹ])",str(segment['text'])) if part.strip()]
    if len(clauses) != len(turns):
        raise ValueError("Câu nguồn có nhiều người nói nhưng phụ đề đã mất ranh giới giữa các câu. "
                         "Hãy tách các câu bằng dấu chấm, chấm hỏi hoặc chấm than trước khi tạo giọng.")
    duration = max(1,round((float(segment['end'])-float(segment['start']))*1000))
    source_start,source_end = float(source['start']),float(source['end'])
    span = max(.001,source_end-source_start)
    plan = []
    for text,turn in zip(clauses,turns):
        left = round((float(turn['start'])-source_start)/span*duration)
        right = round((float(turn['end'])-source_start)/span*duration)
        plan.append({'text':text,'voice':turn['speaker_voice'],'speaker_id':turn['speaker_id'],
                     'offset_ms':max(0,left),'duration_ms':max(1,right-left),
                     'source_start':turn['start'],'source_end':turn['end'],'source_text':turn['text']})
    return plan


def _compose_speaker_utterances(parts, output_path, video_id):
    from haizflow.pipeline.audio_timeline import trim_silence,compress_to_fit
    from haizflow.pipeline.omnivoice_tts import _encode_mp3
    from haizflow.utils.audio import AudioSegment
    length = max(item['offset_ms']+item['duration_ms'] for item in parts)
    result = AudioSegment.silent(duration=length,frame_rate=24000).set_channels(1)
    for item in parts:
        audio = trim_silence(AudioSegment.from_file(item['output_path'])).set_frame_rate(24000).set_channels(1)
        if len(audio) > item['duration_ms']:
            audio = compress_to_fit(audio,item['duration_ms'],str(Path(output_path).parent),video_id)
        result = result.overlay(audio,position=item['offset_ms'])
    with tempfile.TemporaryDirectory(prefix='speaker-mix-',dir=Path(output_path).parent) as work:
        wav = Path(work)/'voice.wav'
        result.export(wav,format='wav').close()
        _encode_mp3(wav,Path(output_path),video_id)


def _level_voice_peers(peers, requested, video_id, language):
    """Level only requested clips against bounded, same-speaker dialogue.

    Existing cache inputs are read-only; atomic path replacement never modifies
    a hard-linked immutable artifact. No inference/tensors or whole-video decode.
    """
    import numpy as np
    import subprocess
    from haizflow.pipeline.process_registry import check_cancellation,communicate_process
    from haizflow.utils.float_pcm import FloatPcmReader
    from haizflow.utils.ffmpeg import _binary
    from haizflow.pipeline.tts_quality import (
        active_speech_rms, is_level_reference_text, match_quiet_speech_level, peer_speech_target,
    )
    from haizflow.pipeline.omnivoice_tts import _encode_mp3

    def key(item):
        return (item.get('voice'), item.get('speaker_id') or 'narrator')

    groups = {}
    for item in peers:
        group = groups.setdefault(key(item),[])
        if (len(group) < 12 and is_level_reference_text(item['text'],language)
                and _is_valid_mp3(item['output_path'])):
            group.append(item)
    groups = {identity:items for identity,items in groups.items() if len(items) >= 3}
    if not groups:
        return set()
    changed = set()
    measurements = {}
    def decode(path):
        check_cancellation(video_id)
        process = subprocess.Popen(
            [_binary('ffmpeg'),'-v','error','-i',str(path),'-t','30','-ac','1','-ar','24000','-f','f32le','-'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        stdout,stderr = communicate_process(video_id,process,label='Voice peer loudness')
        if process.returncode:
            raise RuntimeError(f'Could not measure generated speech: {stderr[-500:]}')
        return np.frombuffer(stdout,dtype='<f4'),24000
    for identity,items in groups.items():
        levels = []
        for item in items:
            path = item['output_path']
            if path not in measurements:
                wave,rate = decode(path)
                measurements[path] = active_speech_rms(wave,rate)
            levels.append(measurements[path])
        groups[identity] = peer_speech_target(levels)
    for item in requested:
        target = groups.get(key(item),0)
        if not target:
            continue
        path = Path(item['output_path'])
        wave,rate = decode(path)
        corrected = match_quiet_speech_level(wave,rate,target,tolerance_db=1.0)
        if np.array_equal(wave,corrected):
            continue
        # Decoding measurement is bounded; adjust the complete clip with the
        # same constant gain, without trimming or rewriting any phonemes.
        gain = float(np.max(abs(corrected)) / max(float(np.max(abs(wave))),1e-20))
        with tempfile.TemporaryDirectory(prefix='voice-level-',dir=path.parent) as work:
            pcm = Path(work)/'voice.pcm'
            process = subprocess.Popen(
                [_binary('ffmpeg'),'-y','-v','error','-i',str(path),'-ac','1','-ar','24000','-f','f32le',str(pcm)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            _,stderr = communicate_process(video_id,process,label='Voice level peak validation')
            if process.returncode:
                raise RuntimeError(f'Could not decode generated speech: {stderr[-500:]}')
            full_peak = 0.0
            with FloatPcmReader(pcm,24000) as source:
                while True:
                    block = source.read(24000)
                    if not block.size:
                        break
                    check_cancellation(video_id)
                    full_peak = max(full_peak,float(np.max(abs(block))))
            gain = min(gain,10**(-1/20)/max(full_peak,1e-20))
            if gain <= 1:
                continue
            wav = Path(work)/'voice.wav'
            process = subprocess.Popen(
                [_binary('ffmpeg'),'-y','-v','error','-f','f32le','-ar','24000','-ac','1','-i',str(pcm),
                 '-af',f'volume={gain:.9f}','-c:a','pcm_f32le',str(wav)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            _,stderr = communicate_process(video_id,process,label='Voice peer level adjustment')
            if process.returncode:
                raise RuntimeError(f'Could not level generated speech: {stderr[-500:]}')
            check_cancellation(video_id)
            _encode_mp3(wav,path,video_id)
        log_to_video(video_id,f"[TTS][LEVEL] speaker={item.get('speaker_id') or 'narrator'} "
                     f"voice={item.get('voice')} gain_db={20*np.log10(gain):.2f}")
        changed.add(str(path))
    return changed


def generate_voice_parts(
    segments_json_path: str,
    voice_parts_dir: str,
    voice: str,
    video_id: str,
    progress_callback=None,
    *,
    provider: str = "omnivoice",
    target_language: str = "vi",
    process_registry_id: str | None = None,
    keep_worker_warm: bool = False,
    segment_indices: list[int] | None = None,
    narrator_anchor_text: str = "",
    status_callback=None,
    level_peer_indices: list[int] | None = None,
):
    backend = resolve_tts_provider(provider, target_language)
    device = "gpu" if provider.endswith("-gpu") else "cpu"

    with open(segments_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("Voice generation requires at least one translated subtitle segment.")
    requested_indices = (
        list(range(1, len(segments) + 1))
        if segment_indices is None
        else list(dict.fromkeys(segment_indices))
    )
    if any(index < 1 or index > len(segments) for index in requested_indices):
        raise ValueError("TTS segment index is outside the subtitle document.")
    requested_segments = [(index, segments[index - 1]) for index in requested_indices]
    if not requested_segments:
        return
    if backend == "vieneu":
        from haizflow.core.vieneu_voices import han_text_notice

        notice = han_text_notice([{**segment, "index": index} if isinstance(segment, dict) else {}
                                  for index, segment in requested_segments])
        if notice:
            raise ValueError(notice[1])
    total = len(requested_segments)
    document_total = len(segments)
    os.makedirs(voice_parts_dir, exist_ok=True)
    if backend == "edge":
        from haizflow.core.edge_voices import edge_voice
        from haizflow.pipeline.edge_tts_backend import synthesize_many_to_mp3

        edge_voice(voice, target_language)
        log_to_video(video_id, "[TTS][SESSION_START] provider=edge backend=online concurrency=2 adaptive=true")

        def requests():
            for index, segment in requested_segments:
                text = str((segment or {}).get("text") or "").strip() if isinstance(segment, dict) else ""
                if not text:
                    raise RuntimeError(f"Translated subtitle segment {index} is missing text.")
                yield preprocess_text_for_tts(text), os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")

        def report_completed(completed):
            if status_callback:
                status_callback("completed", completed, total)
            if progress_callback:
                progress_callback(completed, total)

        synthesize_many_to_mp3(requests(), voice, video_id, language_id=target_language,
                              process_registry_id=process_registry_id, on_completed=report_completed)
        log_to_video(video_id, "Edge TTS generated and verified every requested voice segment.")
        return
    current_video = get_video(video_id)
    current_files = dict((current_video.files if current_video else {}) or {})
    speaker_mode = str(getattr(current_video, "speaker_mode", "single") or "single")
    if backend == "vieneu":
        from haizflow.core.vieneu_voices import native_voice, speaker_voice
        from haizflow.pipeline.vieneu_tts import synthesize_batch_to_mp3

        if speaker_mode != "multiple":
            voice = "vieneu:" + native_voice(voice) if voice != "vieneu:clone" else voice
    else:
        voice = normalize_voice(voice)
        from haizflow.pipeline.omnivoice_tts import synthesize_batch_to_mp3
    pending = []
    pending_by_segment = {}
    composite_segments = {}
    composition_work = None
    session_voice = "per-speaker" if speaker_mode == "multiple" else voice
    log_to_video(video_id, f"[TTS][SESSION_START] provider={backend} backend=local device={device} "
                 f"speaker_mode={speaker_mode} voice={session_voice}")
    if speaker_mode == "multiple" and voice in {"omnivoice:clone", "vieneu:clone"}:
        raise ValueError("Hãy chọn Giọng nhân bản hoặc Nhận diện nhiều người nói, không dùng cả hai cùng lúc.")
    clone_reference = str(current_files.get("voice_reference") or "")
    clone_transcript = str(current_files.get("voice_reference_transcript") or "")
    source_segments = []
    source_audio_path = ""
    if speaker_mode == "multiple" and current_video is not None:
        video_input = str(current_files.get("video_input") or "")
        video_root = os.path.dirname(os.path.dirname(video_input)) if video_input else ""
        source_segments_path = str(current_files.get("source_segments") or "")
        if not source_segments_path and video_root:
            source_segments_path = os.path.join(video_root, "temp", "source_segments.json")
        source_audio_path = str(current_files.get("speech_audio") or "")
        if not source_audio_path and video_root:
            source_audio_path = os.path.join(video_root, "temp", "audio.wav")
        if source_segments_path and os.path.isfile(source_segments_path):
            with open(source_segments_path, "r", encoding="utf-8") as source_file:
                loaded_source_segments = json.load(source_file)
            if isinstance(loaded_source_segments, list):
                source_segments = loaded_source_segments
        if not source_segments or not os.path.isfile(source_audio_path):
            raise RuntimeError(
                "Multiple-speaker mode requires the current source speech and timestamped source transcript."
            )
        from haizflow.pipeline.speaker_identity import IDENTITY_VERSION, _valid_map, prepare_speakers

        speaker_runtime_state = None

        def report_speakers(status):
            nonlocal speaker_runtime_state
            state = (status.get("device"), status.get("fallback_reason"))
            if state[0] and state != speaker_runtime_state:
                speaker_runtime_state = state
                log_to_video(video_id, f"[SPEAKERS][RUNTIME] device={state[0]}"
                             + (f" · Chuyển sang CPU: {state[1]}" if state[1] else ""))
            current = int(status.get("current") or 0)
            total_sources = int(status.get("total") or len(source_segments))
            if status_callback is not None:
                status_callback("identifying_speakers", current, total_sources)

        identified = prepare_speakers(source_audio_path, source_segments,
                                      process_registry_id or video_id, report_speakers)
        # Do not silently fill an incomplete/old engine result with the UI's
        # narrator preset. Validate before queuing or synthesizing any clip.
        if not _valid_map(identified, source_segments):
            raise RuntimeError("Không xác định được giọng từng người nói. Hãy chạy lại nhận diện người nói.")
        source_segments = identified
        if backend == "vieneu":
            # Copy mappings in memory only: the source-identity cache and
            # existing OmniVoice target assignments remain unmodified.
            source_segments = [{**entry, "speaker_voice": speaker_voice(entry["speaker_voice"]),
                                **({"speaker_turns": [{**turn, "speaker_voice": speaker_voice(turn["speaker_voice"])}
                                                       for turn in entry["speaker_turns"]]}
                                   if entry.get("speaker_turns") else {})}
                               for entry in source_segments]
        diagnostic_turns = [turn for source in source_segments for turn in (source.get('speaker_turns') or [source])]
        log_to_video(video_id, f"[SPEAKERS][POLICY] version={IDENTITY_VERSION}")
        voice_map = dict((s["speaker_id"], s["speaker_voice"]) for s in diagnostic_turns)
        log_to_video(video_id, "[SPEAKERS][VOICE_MAP] " + " ".join(f"{key}={value}" for key, value in voice_map.items()))
        profiles = {s["speaker_id"]: (s.get("speaker_pitch_hz"), bool(s.get("speaker_voice_uncertain")))
                    for s in diagnostic_turns}
        log_to_video(video_id, "[SPEAKERS][VOICE_PROFILE] " + " ".join(
            f"{speaker}:f0_hz={pitch},uncertain={uncertain}" for speaker, (pitch, uncertain) in profiles.items()
        ))
        backends = sorted({str(s.get("speaker_profile_backend") or "legacy") for s in diagnostic_turns})
        fallback_count = sum(bool(s.get("speaker_voice_fallback")) for s in diagnostic_turns)
        fallback_voice = "vieneu:Trúc Ly" if backend == "vieneu" else "omnivoice:female_gentle"
        log_to_video(video_id, f"[SPEAKERS][TIMBRE] backend={','.join(backends)} "
                     f"fallback_turns={fallback_count} fallback_voice={fallback_voice}")
        log_to_video(video_id,f"[SPEAKERS][SUBTURNS] source_clips={len(source_segments)} turns={len(diagnostic_turns)} "
                     f"mixed_clips={sum(bool(s.get('speaker_turns')) for s in source_segments)} "
                     f"childlike_turns={sum(s.get('speaker_timbre_style')=='child-like' for s in diagnostic_turns)}")
        log_to_video(video_id, f"Identified {len({s['speaker_id'] for s in diagnostic_turns})} speaker candidates; "
                     "using stable target-language voices, not per-sentence source clones.")
        uncertain = sum(bool(s.get("speaker_uncertain")) for s in diagnostic_turns)
        if uncertain:
            log_to_video(video_id, f"[SPEAKERS][LOW_CONFIDENCE] {uncertain}/{len(diagnostic_turns)} turns are ambiguous; "
                         "short, overlapping or distorted source speech may require manual voice correction.")
    if voice in {"omnivoice:clone", "vieneu:clone"} and (
        not clone_reference or not os.path.isfile(clone_reference)
    ):
        raise RuntimeError("Voice cloning requires an authorised reference sample.")

    exact_source_windows = {}
    for source in source_segments:
        if isinstance(source,dict):
            left = float(source.get('start') or 0)
            right = max(left,float(source.get('end') or left))
            exact_source_windows.setdefault((left,right),source)

    def source_reference_for(segment: dict) -> dict:
        """Match edited subtitles to source speech by time, never by list position."""
        if speaker_mode != "multiple" or not source_segments:
            return {}
        start = float(segment.get("start") or 0.0)
        end = max(start, float(segment.get("end") or start))
        if (start,end) in exact_source_windows:
            return exact_source_windows[(start,end)]
        midpoint = (start + end) / 2.0

        def match_score(source: dict) -> tuple[float, float]:
            source_start = float((source or {}).get("start") or 0.0)
            source_end = max(source_start, float((source or {}).get("end") or source_start))
            overlap = max(0.0, min(end, source_end) - max(start, source_start))
            distance = abs(midpoint - ((source_start + source_end) / 2.0))
            return overlap, -distance

        return max((item for item in source_segments if isinstance(item, dict)), key=match_score, default={})

    prepared_plans = {}
    for index, segment in requested_segments:
        if not isinstance(segment,dict) or not str(segment.get('text') or '').strip():
            raise RuntimeError(f"Translated subtitle segment {index} is missing text.")
        source = source_reference_for(segment)
        prepared_plans[index] = (_speaker_utterance_plan(segment,source) if speaker_mode == 'multiple'
                                 else [{'text':segment['text'],'voice':voice}])

    peer_indices = list(range(1,len(segments)+1)) if level_peer_indices is None else level_peer_indices
    if any(index < 1 or index > len(segments) for index in peer_indices):
        raise ValueError('Voice loudness peer index is outside the subtitle document.')
    peer_items = []
    for index in peer_indices:
        segment = segments[index-1]
        source = source_reference_for(segment) if speaker_mode == 'multiple' else {}
        if source.get('speaker_turns'):
            continue  # Never measure different actors as one speaker.
        peer_items.append({'text':str(segment.get('text') or ''),
                           'voice':source.get('speaker_voice') if speaker_mode == 'multiple' else voice,
                           'speaker_id':source.get('speaker_id') if speaker_mode == 'multiple' else 'narrator',
                           'output_path':os.path.join(voice_parts_dir,f'voice_{index:04d}.mp3')})

    def level_finished_parts():
        requested_items = []
        for index,_segment in requested_segments:
            if index in pending_by_segment:
                requested_items.extend(pending_by_segment[index])
            elif len(prepared_plans[index]) == 1:
                requested_items.append({**prepared_plans[index][0],
                                        'output_path':os.path.join(voice_parts_dir,f'voice_{index:04d}.mp3')})
        if status_callback:
            status_callback('leveling_voice',total,total)
        changed = _level_voice_peers(peer_items,requested_items,process_registry_id or video_id,target_language)
        for index,destination in composite_segments.items():
            if any(part['output_path'] in changed for part in pending_by_segment[index]):
                _compose_speaker_utterances(pending_by_segment[index],destination,process_registry_id or video_id)

    for index, segment in requested_segments:
        text = str((segment or {}).get("text") or "").strip() if isinstance(segment, dict) else ""
        if not text:
            raise RuntimeError(f"Translated subtitle segment {index} is missing text.")
        part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
        if not _is_valid_mp3(part_path):
            _remove_file(part_path)
            source_reference = source_reference_for(segment)
            segment_voice = str(source_reference["speaker_voice"]) if speaker_mode == "multiple" else voice
            log_to_video(
                video_id,
                f"[TTS][QUEUED] provider={backend} segment={index}/{document_total} voice={segment_voice} "
                f"speaker={source_reference.get('speaker_id') or 'narrator'}",
            )
            plan = prepared_plans[index]
            if len(plan) > 1 and composition_work is None:
                composition_work = tempfile.TemporaryDirectory(prefix='speaker-phrases-',dir=voice_parts_dir)
            pieces = []
            for number,utterance in enumerate(plan):
                if len(plan)>1:
                    log_to_video(video_id,f"[TTS][SUBTURN] segment={index}/{document_total} part={number+1}/{len(plan)} "
                                 f"voice={utterance['voice']} speaker={utterance['speaker_id']} "
                                 f"offset_ms={utterance['offset_ms']} duration_ms={utterance['duration_ms']}")
                piece_path = str(Path(composition_work.name)/f'{index}-{number}.mp3') if len(plan)>1 else part_path
                pending.append({
                    "text": preprocess_text_for_tts(utterance['text']),
                    "voice": str(utterance['voice']),
                    "output_path": piece_path,
                    "index": str(index),
                    "reference_path": clone_reference if voice in {"omnivoice:clone", "vieneu:clone"} else "",
                    "reference_text": clone_transcript if voice == "omnivoice:clone" else "",
                    # Identity came from source, pronunciation from the target
                    # preset. Never leak source dialogue via cross-language cloning.
                    "source_audio_path": "",
                    "speaker_id": str(utterance.get('speaker_id') or source_reference.get("speaker_id") or ""),
                    "source_start": str(utterance.get('source_start',source_reference.get("start", ""))),
                    "source_end": str(utterance.get('source_end',source_reference.get("end", ""))),
                    "source_text": str(utterance.get('source_text',source_reference.get("text")
                                                                 or segment.get("source_text") or "")),
                })
                pieces.append({**utterance,'output_path':piece_path})
            pending_by_segment[index] = pieces
            if len(plan)>1:
                composite_segments[index] = part_path
    completed_before_worker = total - len(pending_by_segment)
    if progress_callback and completed_before_worker:
        progress_callback(completed_before_worker, total)
    if pending:
        observed_completed = 0
        completed_pieces = {}
        ready_indices = set()
        def report_omnivoice_progress(completed, _pending_total, stage):
            nonlocal observed_completed
            while observed_completed < min(completed,len(pending)):
                entry = pending[observed_completed]
                if not _is_valid_mp3(entry['output_path']):
                    break
                observed_completed += 1
                index = int(entry['index'])
                completed_pieces[index] = completed_pieces.get(index,0)+1
                if completed_pieces[index] == len(pending_by_segment[index]):
                    if index in composite_segments:
                        _compose_speaker_utterances(pending_by_segment[index],composite_segments[index],process_registry_id or video_id)
                    ready_indices.add(index)
            verified = min(completed_before_worker + len(ready_indices), total)
            if status_callback is not None:
                status_callback(stage, verified, total)
            elif progress_callback is not None:
                progress_callback(verified, total)

        worker_options = {"device": device}
        if process_registry_id:
            worker_options["process_registry_id"] = process_registry_id
        if keep_worker_warm:
            worker_options["keep_worker_warm"] = True
        if narrator_anchor_text and speaker_mode != "multiple":
            worker_options["narrator_anchor_text"] = narrator_anchor_text
        try:
            synthesize_batch_to_mp3(
                pending,
                video_id,
                language_id=target_language,
                speaker_mode=speaker_mode,
                progress_callback=report_omnivoice_progress,
                **worker_options,
            )
            level_finished_parts()
            report_omnivoice_progress(len(pending),len(pending),'completed')
        finally:
            if composition_work:
                composition_work.cleanup()
    else:
        level_finished_parts()
    for index, _segment in requested_segments:
        part_path = os.path.join(voice_parts_dir, f"voice_{index:04d}.mp3")
        if not _is_valid_mp3(part_path):
            raise RuntimeError(f"{backend} produced invalid audio for subtitle segment {index}.")
    if progress_callback:
        progress_callback(total, total)
    log_to_video(video_id, f"{backend} generated and verified every voice segment locally.")


def generate_single_voice(
    text: str,
    output_path: str,
    voice: str,
    video_id: str,
    *,
    provider: str = "omnivoice",
    target_language: str = "vi",
):
    """Create and verify a complete narration file with the selected provider."""
    backend = resolve_tts_provider(provider, target_language)
    if backend == "edge":
        from haizflow.pipeline.edge_tts_backend import synthesize_to_mp3

        return synthesize_to_mp3(preprocess_text_for_tts(text), voice, output_path, video_id,
                                 language_id=target_language)
    if backend == "vieneu":
        from haizflow.pipeline.vieneu_tts import synthesize_to_mp3

        video = get_video(video_id) if voice == "vieneu:clone" else None
        reference = str(((video.files if video else {}) or {}).get("voice_reference") or "")
        return synthesize_to_mp3(preprocess_text_for_tts(text), voice, output_path, video_id,
                                 language_id=target_language,
                                 reference_path=reference,
                                 device="gpu" if provider.endswith("-gpu") else "cpu")
    device = "gpu" if provider.endswith("-gpu") else "cpu"
    voice = normalize_voice(voice)
    from haizflow.pipeline.omnivoice_tts import synthesize_to_mp3

    current_video = get_video(video_id)
    current_files = dict((current_video.files if current_video else {}) or {})
    reference_path = str(current_files.get("voice_reference") or "")
    reference_text = str(current_files.get("voice_reference_transcript") or "")
    if voice == "omnivoice:clone" and (not reference_path or not os.path.isfile(reference_path)):
        raise RuntimeError("OmniVoice voice cloning requires an authorised reference sample.")
    synthesize_to_mp3(
        preprocess_text_for_tts(text),
        voice,
        output_path,
        video_id,
        language_id=target_language,
        device=device,
        reference_path=reference_path if voice == "omnivoice:clone" else "",
        reference_text=reference_text if voice == "omnivoice:clone" else "",
    )
    if not _is_valid_mp3(output_path):
        raise RuntimeError("OmniVoice produced invalid narration audio.")
    log_to_video(video_id, f"Successfully created narration file: {output_path}")
