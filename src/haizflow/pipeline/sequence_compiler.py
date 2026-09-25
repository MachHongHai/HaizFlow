from __future__ import annotations

import math
import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import srt

from haizflow.pipeline.process_registry import check_cancellation, communicate_process
from haizflow.pipeline.render import _font_path_details, font_file_fingerprint
from haizflow.pipeline.text_overlay_sprite import render_text_overlay_sprite
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorTextStyle
from haizflow.schemas.video import SubtitleStyle
from haizflow.services import editor_documents
from haizflow.utils.ffmpeg import _binary, get_media_stream_types


def document_signature_payload(document: EditorDocument | None) -> dict:
    return document.model_dump() if document else {}


def _run(command: list[str], *, cwd: str, process_id: str, label: str) -> None:
    check_cancellation(process_id)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _stdout, stderr = communicate_process(process_id, process, label=label)
    check_cancellation(process_id)
    if process.returncode != 0:
        raise RuntimeError(f"{label} failed: {stderr[-1200:]}")


def has_source_edits(document: EditorDocument | None) -> bool:
    if not document or len(document.sequence.edit_decisions) != 1:
        return bool(document and document.sequence.edit_decisions)
    decision = document.sequence.edit_decisions[0]
    return not (
        decision.sequence_start_ms == 0
        and decision.source_start_ms == 0
        and abs(decision.source_end_ms - document.sequence.duration_ms) <= 1
    )


def map_source_intervals(
    document: EditorDocument | None,
    intervals: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not document or not has_source_edits(document):
        return intervals
    mapped: list[tuple[float, float]] = []
    for decision in document.sequence.edit_decisions:
        source_start = decision.source_start_ms / 1000
        source_end = decision.source_end_ms / 1000
        sequence_start = decision.sequence_start_ms / 1000
        for start, end in intervals:
            overlap_start = max(source_start, float(start))
            overlap_end = min(source_end, float(end))
            if overlap_end <= overlap_start:
                continue
            mapped.append(
                (
                    sequence_start + overlap_start - source_start,
                    sequence_start + overlap_end - source_start,
                )
            )
    return mapped


def materialize_source_sequence(
    video_path: str,
    audio_path: str,
    document: EditorDocument | None,
    output_directory: str | Path,
    process_id: str,
) -> tuple[str, str]:
    """Create one video/audio pair following the source edit decision list."""
    if not has_source_edits(document):
        return video_path, audio_path
    decisions = sorted(document.sequence.edit_decisions, key=lambda item: item.sequence_start_ms)
    if not decisions:
        raise RuntimeError("The editor sequence has no source ranges to export.")
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    edited_video = output_dir / "sequence-source.mp4"
    edited_audio = output_dir / "sequence-audio.wav"
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, decision in enumerate(decisions):
        start = decision.source_start_ms / 1000
        end = decision.source_end_ms / 1000
        if end <= start:
            continue
        filters.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]"
        )
        filters.append(
            f"[1:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")
    if not concat_inputs:
        raise RuntimeError("The editor sequence contains only empty source ranges.")
    filters.append(
        f"{''.join(concat_inputs)}concat=n={len(concat_inputs)}:v=1:a=1[sequence_v][sequence_a]"
    )
    command = [
        _binary("ffmpeg"),
        "-y",
        "-i",
        os.path.abspath(video_path),
        "-i",
        os.path.abspath(audio_path),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[sequence_v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(edited_video),
        "-map",
        "[sequence_a]",
        "-vn",
        "-c:a",
        "pcm_s16le",
        str(edited_audio),
    ]
    _run(command, cwd=str(output_dir), process_id=process_id, label="Editor source sequence")
    return str(edited_video), str(edited_audio)


def materialize_source_video(
    video_path: str,
    document: EditorDocument | None,
    output_directory: str | Path,
    process_id: str,
) -> str:
    """Materialize only the source picture edit map.

    The audio mix is composed in sequence time after the source bed has been
    edited.  Re-trimming that finished mix with source timestamps would move
    voice and music twice, so export uses this video-only compiler.
    """
    if not has_source_edits(document):
        return video_path
    decisions = sorted(document.sequence.edit_decisions, key=lambda item: item.sequence_start_ms)
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    edited_video = output_dir / "sequence-source.mp4"
    filters: list[str] = []
    inputs: list[str] = []
    for index, decision in enumerate(decisions):
        start = decision.source_start_ms / 1000
        end = decision.source_end_ms / 1000
        if end <= start:
            continue
        filters.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]"
        )
        inputs.append(f"[v{index}]")
    if not inputs:
        raise RuntimeError("The editor sequence contains only empty source ranges.")
    filters.append(f"{''.join(inputs)}concat=n={len(inputs)}:v=1:a=0[sequence_v]")
    command = [
        _binary("ffmpeg"),
        "-y",
        "-i",
        os.path.abspath(video_path),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[sequence_v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(edited_video),
    ]
    _run(command, cwd=str(output_dir), process_id=process_id, label="Editor source video")
    return str(edited_video)


def write_subtitles(document: EditorDocument | None, destination: str | Path) -> bool:
    if not document:
        return False
    visible = {
        track.track_id
        for track in document.tracks
        if track.visible and track.kind == "subtitle"
    }
    clips = sorted(
        (
            clip
            for clip in document.clips
            if clip.track_id in visible and clip.kind == "subtitle" and clip.enabled and clip.name
        ),
        key=lambda item: (item.start_ms, item.clip_id),
    )
    if not clips:
        return False
    subtitles = [
        srt.Subtitle(
            index=index,
            start=timedelta(milliseconds=clip.start_ms),
            end=timedelta(milliseconds=clip.start_ms + clip.duration_ms),
            content=clip.name,
        )
        for index, clip in enumerate(clips, start=1)
    ]
    Path(destination).write_text(srt.compose(subtitles), encoding="utf-8")
    return True


def resolved_subtitle_style(document: EditorDocument | None, fallback: SubtitleStyle) -> SubtitleStyle:
    if not document:
        return fallback
    style = next(
        (item for item in document.styles if item.style_id == document.default_subtitle_style_id),
        None,
    )
    if style is None:
        return fallback
    payload = fallback.model_dump()
    payload.update(
        font_family=style.font_family,
        font_size=round(style.font_size),
        text_color=style.text_color,
        karaoke_color=style.karaoke_color,
        outline_color=style.outline_color,
        outline=round(style.outline_width),
        bold=style.font_weight >= 600,
        italic=style.italic,
        uppercase=style.uppercase,
        shadow=round(max(abs(style.shadow_offset_x), abs(style.shadow_offset_y))),
        letter_spacing=style.letter_spacing,
        alignment=style.alignment,
        position_x_percent=round(style.position_x_percent),
        position_y_percent=round(style.position_y_percent),
        box_width_percent=round(style.max_width_percent),
        box_height_percent=round(style.box_height_percent),
    )
    return SubtitleStyle(**payload)


def subtitle_style_overrides(document: EditorDocument | None) -> dict[int, dict]:
    """Resolve the exact style for every exported subtitle cue."""
    if not document:
        return {}
    visible = {
        track.track_id
        for track in document.tracks
        if track.visible and track.kind == "subtitle"
    }
    clips = sorted(
        (
            clip for clip in document.clips
            if clip.track_id in visible and clip.kind == "subtitle" and clip.enabled and clip.name
        ),
        key=lambda item: (item.start_ms, item.clip_id),
    )
    return {
        index: editor_documents.resolved_text_style(document, clip).model_dump()
        for index, clip in enumerate(clips, start=1)
    }


def _number(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(round(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _escape_expression(value: str) -> str:
    return value.replace(",", r"\,")


def keyframe_expression(clip: EditorClip, property_name: str, default: float) -> str:
    frames = sorted(
        (frame for frame in clip.keyframes if frame.property_name == property_name),
        key=lambda item: item.time_ms,
    )
    if not frames:
        return _number(float(default))
    absolute = [((clip.start_ms + frame.time_ms) / 1000, frame) for frame in frames]
    expression = _number(float(absolute[-1][1].value))
    for index in range(len(absolute) - 2, -1, -1):
        left_time, left = absolute[index]
        right_time, right = absolute[index + 1]
        span = max(0.001, right_time - left_time)
        progress = f"((t-{_number(left_time)})/{_number(span)})"
        if right.interpolation == "ease_in":
            eased = f"({progress}*{progress})"
        elif right.interpolation == "ease_out":
            eased = f"(1-(1-{progress})*(1-{progress}))"
        elif right.interpolation == "ease_in_out":
            eased = (
                f"if(lt({progress},0.5),2*{progress}*{progress},"
                f"1-pow(-2*{progress}+2,2)/2)"
            )
        else:
            eased = progress
        interpolated = (
            f"({_number(float(left.value))}+"
            f"({_number(float(right.value) - float(left.value))})*{eased})"
        )
        expression = f"if(lt(t,{_number(right_time)}),{interpolated},{expression})"
    first_time, first = absolute[0]
    expression = f"if(lt(t,{_number(first_time)}),{_number(float(first.value))},{expression})"
    return _escape_expression(expression)


def _style_for_clip(document: EditorDocument, clip: EditorClip) -> EditorTextStyle:
    style = next((item for item in document.styles if item.style_id == clip.style_id), None)
    if style is None:
        style = EditorTextStyle(style_id="overlay-fallback", target_type="text_overlay")
    if not clip.style_override:
        return style
    payload = style.model_dump()
    payload.update(clip.style_override)
    return EditorTextStyle.model_validate(payload)


def _active_overlays(document: EditorDocument | None) -> list[EditorClip]:
    if not document:
        return []
    visible = {track.track_id for track in document.tracks if track.visible}
    return sorted(
        (
            clip
            for clip in document.clips
            if clip.track_id == "overlays"
            and clip.track_id in visible
            and clip.enabled
            and clip.clip_id != "watermark-1"
        ),
        key=lambda item: (item.start_ms, item.clip_id),
    )


def export_preflight(
    document: EditorDocument | None,
    source_path: str,
    output_directory: str | Path,
) -> dict:
    """Validate editor resources before a potentially long export starts.

    Missing source/overlay media and insufficient temporary space are fatal.
    Stale voice and font substitutions remain warnings because Manual export
    intentionally permits the user to publish the current partial state.
    """
    issues: list[dict[str, str]] = []
    if document is None:
        issues.append({
            "severity": "error",
            "code": "missing_document",
            "title": "Không đọc được tài liệu chỉnh sửa",
            "detail": "Hãy đóng và mở lại dự án trước khi xuất.",
        })
        return {
            "canExport": False,
            "issues": issues,
            "requiredBytes": 0,
            "availableBytes": 0,
        }

    visible_tracks = {track.track_id for track in document.tracks if track.visible}
    source = Path(str(source_path or ""))
    if not source.is_file() or source.stat().st_size <= 0:
        issues.append({
            "severity": "error",
            "code": "missing_source",
            "title": "Không tìm thấy video nguồn",
            "detail": "Chọn lại video nguồn trước khi xuất.",
        })

    missing_media: list[str] = []
    media_paths: set[Path] = set()
    for clip in document.clips:
        if not clip.enabled or clip.track_id not in visible_tracks:
            continue
        if clip.kind not in {"image", "video", "audio"} or not clip.asset_id:
            continue
        asset = editor_documents.asset_by_id(document, clip.asset_id)
        path = Path(asset.path) if asset and asset.path else None
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            missing_media.append(clip.name or (asset.name if asset else clip.clip_id))
        else:
            media_paths.add(path)
    if missing_media:
        names = ", ".join(dict.fromkeys(missing_media))
        issues.append({
            "severity": "error",
            "code": "missing_media",
            "title": "Thiếu tệp trong timeline",
            "detail": names,
        })

    used_styles: dict[str, EditorTextStyle] = {}
    for clip in document.clips:
        if not clip.enabled or clip.track_id not in visible_tracks:
            continue
        if clip.kind in {"subtitle", "text"}:
            style = editor_documents.resolved_text_style(document, clip)
            used_styles[style.style_id + ":" + style.font_family] = style
    for style in used_styles.values():
        bold = style.font_weight >= 600
        path, exact = _font_path_details(style.font_family, bold, style.italic)
        if not exact:
            issues.append({
                "severity": "warning",
                "code": "missing_font",
                "title": f"Không tìm thấy font {style.font_family}",
                "detail": "HaizFlow sẽ dùng font dự phòng. Chọn font khác để giữ đúng bố cục.",
            })
            continue
        if style.font_fingerprint:
            current = font_file_fingerprint(style.font_family, bold, style.italic)
            if current and current != style.font_fingerprint:
                issues.append({
                    "severity": "warning",
                    "code": "changed_font",
                    "title": f"Font {style.font_family} đã thay đổi",
                    "detail": f"Tệp font hiện tại khác bản đã dùng khi lưu style ({path.name}).",
                })

    voice_track_visible = any(
        track.track_id == "voice" and track.visible and not track.muted
        for track in document.tracks
    )
    stale_voice = [
        clip for clip in document.clips
        if voice_track_visible
        and clip.track_id == "voice"
        and (not clip.enabled or str(clip.metadata.get("state") or "") in {"stale", "error"})
    ]
    if stale_voice:
        issues.append({
            "severity": "warning",
            "code": "stale_voice",
            "title": f"{len(stale_voice)} đoạn giọng đọc chưa khớp",
            "detail": "Video vẫn có thể xuất; các đoạn này sẽ không dùng giọng đọc cũ.",
        })

    source_bytes = source.stat().st_size if source.is_file() else 0
    media_bytes = sum(path.stat().st_size for path in media_paths)
    # The source edit and final overlay passes can coexist temporarily. Keep
    # a fixed floor for FFmpeg muxing overhead and short high-bitrate videos.
    required_bytes = max(512 * 1024**2, source_bytes * 3 + media_bytes)
    output_root = Path(output_directory or source.parent or ".")
    output_root.mkdir(parents=True, exist_ok=True)
    available_bytes = shutil.disk_usage(output_root).free
    if available_bytes < required_bytes:
        issues.append({
            "severity": "error",
            "code": "disk_space",
            "title": "Không đủ dung lượng để xuất",
            "detail": "Giải phóng dung lượng trên ổ lưu đầu ra rồi thử lại.",
        })

    return {
        "canExport": not any(item["severity"] == "error" for item in issues),
        "issues": issues,
        "requiredBytes": int(required_bytes),
        "availableBytes": int(available_bytes),
    }


def apply_overlays(
    input_path: str,
    output_path: str,
    document: EditorDocument | None,
    process_id: str,
) -> str:
    overlays = _active_overlays(document)
    if not overlays:
        if os.path.abspath(input_path) != os.path.abspath(output_path):
            shutil.copy2(input_path, output_path)
        return output_path

    inputs = [_binary("ffmpeg"), "-y", "-i", os.path.abspath(input_path)]
    media_indices: dict[str, int] = {}
    media_with_audio: set[str] = set()
    source_asset = editor_documents.asset_by_id(document, document.sequence.source_asset_id)
    reference_width = max(1, int(source_asset.width if source_asset else 0) or 1920)
    reference_height = max(1, int(source_asset.height if source_asset else 0) or 1080)
    for clip in overlays:
        asset = editor_documents.asset_by_id(document, clip.asset_id)
        index = len(media_indices) + 1
        if clip.kind == "text":
            sprite = render_text_overlay_sprite(
                clip.name,
                _style_for_clip(document, clip),
                reference_width,
                reference_height,
            )
            media_indices[clip.clip_id] = index
            inputs.extend(["-loop", "1", "-i", os.path.abspath(sprite["path"])])
            continue
        if clip.kind not in {"image", "video"} or asset is None or not os.path.isfile(asset.path):
            continue
        media_indices[clip.clip_id] = index
        if clip.kind == "video" and "audio" in get_media_stream_types(asset.path):
            media_with_audio.add(clip.clip_id)
        if clip.kind == "image":
            inputs.extend(["-loop", "1", "-i", os.path.abspath(asset.path)])
        else:
            if clip.loop:
                inputs.extend(["-stream_loop", "-1"])
            inputs.extend(["-i", os.path.abspath(asset.path)])

    filters: list[str] = ["[0:v]setpts=PTS-STARTPTS[base0]"]
    base = "base0"
    stage = 0
    overlay_audio_labels: list[str] = []
    for clip in overlays:
        start = clip.start_ms / 1000
        end = (clip.start_ms + clip.duration_ms) / 1000
        enable = f"between(t,{start:.6f},{end:.6f})"
        x_percent = keyframe_expression(clip, "position_x", clip.transform.position_x_percent)
        y_percent = keyframe_expression(clip, "position_y", clip.transform.position_y_percent)
        opacity = keyframe_expression(clip, "opacity", clip.transform.opacity_percent)
        scale = keyframe_expression(clip, "scale", clip.transform.scale_x_percent)
        scale_y = (
            scale
            if clip.transform.lock_aspect_ratio
            else _number(float(clip.transform.scale_y_percent))
        )
        rotation = keyframe_expression(clip, "rotation", clip.transform.rotation_degrees)
        next_base = f"base{stage + 1}"
        if clip.kind in {"text", "image", "video"}:
            input_index = media_indices.get(clip.clip_id)
            if input_index is None:
                continue
            prepared = f"overlay{stage}"
            base_width = reference_width * (0.20 if clip.kind == "image" else 0.28)
            source_trim = ""
            if clip.kind == "video" and clip.source_in_ms > 0:
                source_trim = f"trim=start={clip.source_in_ms / 1000:.6f},"
            crop_filter = ""
            if clip.kind in {"image", "video"}:
                left = max(0.0, min(95.0, float(clip.transform.crop_left_percent)))
                right = max(0.0, min(95.0 - left, float(clip.transform.crop_right_percent)))
                top = max(0.0, min(95.0, float(clip.transform.crop_top_percent)))
                bottom = max(0.0, min(95.0 - top, float(clip.transform.crop_bottom_percent)))
                if any(value > 0 for value in (left, right, top, bottom)):
                    width_ratio = max(0.05, (100.0 - left - right) / 100.0)
                    height_ratio = max(0.05, (100.0 - top - bottom) / 100.0)
                    crop_filter = (
                        f"crop=w='iw*{_number(width_ratio)}':"
                        f"h='ih*{_number(height_ratio)}':"
                        f"x='iw*{_number(left / 100)}':"
                        f"y='ih*{_number(top / 100)}',"
                    )
            scale_filter = (
                f"scale=w='iw*({scale})/100':h='ih*({scale_y})/100':eval=frame"
                if clip.kind == "text"
                else (
                    f"scale=w='{_number(base_width)}*({scale})/100':"
                    f"h='ih*{_number(base_width)}/iw*({scale_y})/100':eval=frame"
                )
            )
            filters.append(
                f"[{input_index}:v]{source_trim}setpts=PTS-STARTPTS+{start:.6f}/TB,"
                f"{crop_filter}{scale_filter},format=rgba,"
                f"colorchannelmixer=aa='{opacity}/100',"
                f"rotate='{rotation}*PI/180':ow=rotw(iw):oh=roth(ih):c=none[{prepared}]"
            )
            x = f"main_w*({x_percent})/100-overlay_w/2"
            y = f"main_h*({y_percent})/100-overlay_h/2"
            filters.append(
                f"[{base}][{prepared}]overlay=x='{x}':y='{y}':enable='{enable}':"
                f"eof_action=pass[{next_base}]"
            )
            if clip.kind == "video" and clip.clip_id in media_with_audio and not clip.muted:
                audio_label = f"overlayaudio{stage}"
                audio_filters = [
                    f"atrim=start={clip.source_in_ms / 1000:.6f}:duration={clip.duration_ms / 1000:.6f}",
                    "asetpts=PTS-STARTPTS",
                    f"volume={_number(clip.volume_percent / 100)}",
                ]
                if clip.fade_in_ms > 0:
                    audio_filters.append(
                        f"afade=t=in:st=0:d={clip.fade_in_ms / 1000:.6f}"
                    )
                if clip.fade_out_ms > 0:
                    fade_start = max(0, clip.duration_ms - clip.fade_out_ms) / 1000
                    audio_filters.append(
                        f"afade=t=out:st={fade_start:.6f}:d={clip.fade_out_ms / 1000:.6f}"
                    )
                if clip.start_ms > 0:
                    audio_filters.append(f"adelay={clip.start_ms}|{clip.start_ms}")
                filters.append(
                    f"[{input_index}:a]{','.join(audio_filters)}[{audio_label}]"
                )
                overlay_audio_labels.append(f"[{audio_label}]")
        base = next_base
        stage += 1

    if stage == 0:
        shutil.copy2(input_path, output_path)
        return output_path
    output_audio_map = "0:a?"
    audio_codec = "copy"
    if overlay_audio_labels:
        base_has_audio = "audio" in get_media_stream_types(input_path)
        mix_inputs = ("[0:a]" if base_has_audio else "") + "".join(overlay_audio_labels)
        input_count = len(overlay_audio_labels) + (1 if base_has_audio else 0)
        filters.append(
            f"{mix_inputs}amix=inputs={input_count}:duration="
            f"{'first' if base_has_audio else 'longest'}:normalize=0[aout]"
        )
        output_audio_map = "[aout]"
        audio_codec = "aac"
    command = [
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{base}]",
        "-map",
        output_audio_map,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        audio_codec,
        "-movflags",
        "+faststart",
        os.path.abspath(output_path),
    ]
    _run(
        command,
        cwd=str(Path(output_path).resolve().parent),
        process_id=process_id,
        label="Editor overlays",
    )
    return output_path
