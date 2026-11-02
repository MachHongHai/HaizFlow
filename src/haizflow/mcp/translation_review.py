"""Revisioned, text-only translation review; no model/API calls."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import srt

from haizflow.services import editor_documents, subtitle_export, video_store


def snapshot(video, manual_segments=None):
    root = Path(video_store.get_video_dir(video.video_id)).resolve()
    document = editor_documents.load(video.video_id) if video.project_type == "manual" else None
    if manual_segments is not None:
        translated = copy.deepcopy(manual_segments)
    else:
        path = Path((video.files or {}).get("translation_review_draft") or
                    (video.files or {}).get("transcript_json") or "")
        if not path.is_file() or not path.resolve().is_relative_to(root) or path.stat().st_size > 1024 * 1024:
            raise ValueError("No bounded translation document belongs to this video yet.")
        translated = json.loads(path.read_text("utf-8"))
    if not isinstance(translated, list) or not 1 <= len(translated) <= 10000:
        raise ValueError("No valid translation cues are ready for review.")
    source = [{"start": cue.start.total_seconds(), "end": cue.end.total_seconds(), "text": cue.content}
              for cue in srt.parse(subtitle_export.compose_source_srt(video, document))]
    if not source and video.project_type != "manual":
        # Auto's original ASR text is preserved separately from translated/voice units.
        path = root / "temp" / "source_segments.json"
        if path.is_file() and path.resolve().is_relative_to(root) and path.stat().st_size <= 1024 * 1024:
            payload = json.loads(path.read_text("utf-8"))
            source = payload if isinstance(payload, list) else []
    signature = {"video_id": video.video_id,
                 "source_generation": dict(getattr(video, "manual_tool_generations", {}) or {}).get("source", 0),
                 "translated": translated, "source": source,
                 "target_language": video.target_language,
                 "instructions": video.gemini_translation_instructions,
                 "glossary": video.gemini_translation_glossary,
                 "document_revision": document.revision if document else None}
    revision = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"revision": revision, "segments": translated, "source": source}


def context_rows(state, offset=0, limit=50, *, indices=None):
    rows = []
    selected = list(range(len(state["segments"]))) if indices is None else indices
    for index in selected[offset:offset + limit]:
        cue = state["segments"][index]
        start, end = float(cue["start"]), float(cue["end"])
        matches = [original for original in state["source"]
                   if min(end, float(original.get("end", 0))) > max(start, float(original.get("start", 0)))]
        rows.append({"cue_id": f"cue-{index + 1}", "segment_id": cue.get("segment_id", ""),
                     "start": start, "end": end, "text": cue["text"],
                     "speaker": cue.get("speaker_id", cue.get("speaker", "")),
                     "speaker_gender": cue.get("speaker_gender", cue.get("gender", "")),
                     "speaker_uncertain": bool(cue.get("speaker_voice_uncertain", True)),
                     "source_matches": [{k: c.get(k) for k in ("start", "end", "text")} for c in matches[:5]]})
    return rows


def patch(state, edits, expected_revision):
    if expected_revision != state["revision"]:
        raise ValueError("Translation/source changed. Read translation_context again before editing.")
    if not 1 <= len(edits) <= 200:
        raise ValueError("Choose 1–200 exact cue edits.")
    updated = copy.deepcopy(state["segments"])
    seen, changed = set(), []
    for edit in edits:
        if set(edit) - {"cue_id", "expected_text", "text"} or not {"cue_id", "expected_text", "text"} <= set(edit):
            raise ValueError("Each edit requires cue_id, expected_text and replacement text only.")
        identifier = edit["cue_id"]
        if not isinstance(identifier, str) or identifier in seen or not identifier.startswith("cue-"):
            raise ValueError("Choose distinct known cue IDs.")
        try:
            index = int(identifier[4:]) - 1
        except ValueError:
            raise ValueError("Unknown cue ID.") from None
        if not 0 <= index < len(updated) or identifier != f"cue-{index + 1}":
            raise ValueError("Unknown cue ID.")
        seen.add(identifier)
        if updated[index]["text"] != edit["expected_text"]:
            raise ValueError("Cue text changed; refresh the translation context.")
        text = edit["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError("Replacement text must contain 1–10000 characters.")
        if text != updated[index]["text"]:
            updated[index]["text"] = text
            changed.append(identifier)
    return updated, changed
