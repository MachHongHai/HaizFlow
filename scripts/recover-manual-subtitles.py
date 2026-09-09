"""Restore a verified Manual subtitle revision without changing visual/audio settings."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from haizflow.pipeline.manual_tools import publish_edited_subtitles
from haizflow.services import manual_artifacts, video_store


def recover(video_id: str, signature: str, expected_current: str, apply: bool = False):
    video = video_store.get_video(video_id)
    if not video or video.project_type != "manual":
        raise ValueError("Manual video not found")
    if video.status in {"pending", "processing"} and video.manual_target_tool:
        raise ValueError("Stop the video task before restoring subtitles")
    if video.active_artifacts.get("subtitle_document") != expected_current:
        raise ValueError("The active subtitle revision changed; recovery was not applied")
    artifact = manual_artifacts.resolve(video_id, "subtitle_document", signature)
    if not artifact:
        raise ValueError("The requested revision failed artifact validation")
    source = Path(artifact["resolved_outputs"]["segments"])
    segments = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(segments, list) or not segments:
        raise ValueError("The requested document is empty")
    print(json.dumps({"video_id": video_id, "revision": signature,
                      "segments": len(segments), "characters": sum(len(s["text"]) for s in segments)},
                     ensure_ascii=False))
    if not apply:
        return
    backup = manual_artifacts.cache_root(video_id) / "recovery" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(video_store.get_video_json_path(video_id), backup / "video.json")
    active = manual_artifacts.resolve(video_id, "subtitle_document", expected_current)
    if active:
        shutil.copy2(active["resolved_outputs"]["segments"], backup / "segments.json")
    record = publish_edited_subtitles(video_id, segments)
    print(json.dumps({"restored": record["signature"], "backup": str(backup)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    parser.add_argument("signature")
    parser.add_argument("--expected-current", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    recover(args.video_id, args.signature, args.expected_current, args.apply)
