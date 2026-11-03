"""Explicit MCP command allowlist; never expose arbitrary QObject methods."""

from __future__ import annotations

import inspect
from functools import lru_cache
from pathlib import Path
from typing import Literal, get_type_hints

from pydantic import TypeAdapter, ValidationError

from haizflow.schemas.video import VideoConfig
from haizflow.core.translation_models import is_cloud_model
from haizflow.services import video_store

EDITABLE_FIELDS = frozenset(
    {
        "target_language",
        "speech_recognition_model",
        "translation_model",
        "gemini_translation_instructions",
        "gemini_translation_glossary",
        "gemini_translation_style",
        "translation_reasoning_effort",
        "translator_provider",
        "tts_provider",
        "tts_voice",
        "speaker_mode",
        "subtitle_style",
        "subtitle_layout_override",
        "remove_original_subtitles",
        "original_subtitle_removal_mode",
        "original_subtitle_region_override",
        "output_format",
        "output_speed",
        "crop",
        "enable_audio_separation",
        "original_video_volume",
        "background_music_volume",
        "background_music_loop",
        "audio_ducking_enabled",
        "audio_ducking_reduction_db",
        "tts_volume",
        "watermark_text",
        "watermark_scale_percent",
        "watermark_opacity_percent",
        "watermark_outline_percent",
        "watermark_font_family",
        "watermark_text_color",
        "watermark_bold",
        "watermark_italic",
        "watermark_moving",
        "watermark_position",
        "watermark_kind",
        "mode",
    }
)
READ_COMMANDS = {
    "status",
    "projects",
    "project",
    "video",
    "subtitles",
    "srt",
    "capabilities",
    "social_status",
    "download_status",
    "editor",
    "batch_settings",
    "resources",
    "options",
    "logs",
    "export_ranges",
    "batch_results",
    "channel_candidates",
    "review",
    "voice_configuration",
    "visual_context",
    "translation_context",
    "observe",
    "read_many",
}
COMMANDS = READ_COMMANDS | {
    "open",
    "create",
    "rename",
    "import_video",
    "configure",
    "import_srt",
    "run",
    "pause",
    "resume",
    "export",
    "edit_subtitle",
    "subtitle_timing",
    "merge_subtitle",
    "delete_subtitle",
    "split_subtitle",
    "undo",
    "redo",
    "clip_properties",
    "track_properties",
    "source_cover",
    "auto_start",
    "batch_configure",
    "batch_start",
    "batch_resume",
    "batch_pause",
    "download_inspect",
    "download_start",
    "download_cancel",
    "channel_scan",
    "channel_select",
    "channel_download",
    "social_add",
    "social_edit",
    "social_select_account",
    "social_settings",
    "social_refresh",
    "social_cancel",
    "prepare_delete",
    "delete",
    "prepare_publish",
    "publish",
    "export_cancel",
    "resource_install",
    "resource_cancel",
    "import_url_inspect",
    "import_url_start",
    "import_url_cancel",
    "voice_reference",
    "watermark_asset",
    "manual_cancel",
    "prepare_restart",
    "restart",
    "background_music",
    "replace_source",
    "replace_url_inspect",
    "replace_url_start",
    "remove_srt",
    "export_srt",
    "export_batch",
    "export_retry",
    "batch_import",
    "review_save",
    "review_approve",
    "subtitle_replace",
    "text_style",
    "clip_trim",
    "clip_move",
    "clip_remove",
    "result_split",
    "background_music_clear",
    "voice_reference_clear",
    "download_clear_queue",
    "download_preview_cancel",
    "channel_retry",
    "social_defaults",
    "social_remove",
    "resource_repair",
    "resource_discard",
    "resource_remove",
    "voice_run",
    "subtitle_layout_apply",
    "translation_patch",
}


def page(values, offset: int, limit: int) -> dict:
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("offset must be >= 0; limit must be between 1 and 200.")
    return {"items": values[offset : offset + limit], "total": len(values), "offset": offset}


@lru_cache(maxsize=256)
def command_signature(function):
    """Cache static validation metadata, never per-user/video values or permissions."""
    annotations = get_type_hints(function)
    signature = inspect.signature(function)
    return signature, {key: TypeAdapter(annotations[key]) for key in signature.parameters if key != "self"}


class McpCommands:
    def __init__(self, host, bridge):
        self.host, self.bridge = host, bridge
        self._replacement_requests = {}

    def dispatch(self, method: str, params: dict) -> dict:
        if method not in COMMANDS:
            raise ValueError("Unknown command. Read capabilities for the supported command schemas.")
        if getattr(self.host, "_shutdown_started", False):
            raise ValueError("HaizFlow is shutting down.")
        if method not in READ_COMMANDS:
            self.bridge.require("write")
        function, bound = self._validated_call(method, params)
        return function(*bound.args, **bound.kwargs)

    def _validated_call(self, method, params):
        function = getattr(self, "_" + method)
        try:
            signature, adapters = command_signature(function.__func__)
            bound = signature.bind(self, **params)
            for key, value in bound.arguments.items():
                if key != "self":
                    bound.arguments[key] = adapters[key].validate_python(value, strict=True)
        except (TypeError, ValidationError):
            raise ValueError("Invalid arguments. Read capabilities for this command's input schema.") from None
        # Use the unbound function because the cached signature includes self.
        return function.__func__, bound

    def _known_project(self, project_id):
        project = self.host._project_summaries_by_key.get(project_id)
        if not project:
            raise ValueError("Unknown project_id. Refresh the project list.")
        if self.host._project_commands.is_deleting(project_id):
            raise ValueError("This project is being deleted.")
        return project

    def _known_video(self, video_id):
        # Never pass an agent-supplied path/ID to disk storage before checking the catalog.
        video = self.host._catalog_videos.get(video_id)
        if not video:
            raise ValueError("Unknown video_id. Read the project first.")
        self._known_project(self.host._video_project_key(video))
        return video_store.get_video(video_id) or video

    def _selected(self, video_id, *, idle=True, manual=False):
        video = self._known_video(video_id)
        if str(self.host._selected_video_id or "") != video_id:
            raise ValueError("Open this exact video in HaizFlow before changing it.")
        if manual and video.project_type != "manual":
            raise ValueError("This command requires a Manual project.")
        if idle and (
            self.host._processing_queue.contains(video_id)
            or self.host._project_import.has_project_work(self.host._video_project_key(video))
            or getattr(self.host, "_device_switching", False)
            or getattr(self.host._resource_packs, "storageMoving", False)
            or any(job.get("videoId") == video_id and job.get("status") not in {"done", "failed", "cancelled"}
                   for job in self.host._video_exports.jobs)
        ):
            raise ValueError("The target is busy. Wait or pause its current job first.")
        if idle:
            self._no_draft()
        return video

    def _no_draft(self):
        model = self.host._manual_subtitles
        if (
            getattr(self.host, "_manual_editing_segment_id", "")
            or any(state in {"saving", "error"} for state in model._states.values())
            or getattr(self.host, "_manual_settings_drafts", {})
        ):
            raise ValueError("Finish or cancel unsaved edits in HaizFlow before an agent changes this workspace.")

    def _current_project(self, project_id, kind=None):
        project = self._known_project(project_id)
        if self.host._selected_project_key != project_id or kind and project["project_type"] != kind:
            raise ValueError("Open the requested project of the correct type first.")
        self._no_draft()
        return project

    def _online(self, video, tool="all"):
        # Auto/resume may reach both translation and voice, not only the current step.
        if (tool in {"translation", "all"} and is_cloud_model(str(video.translation_model))) or (
            tool in {"voice", "all"} and video.tts_provider == "edge"
        ):
            self.bridge.require("online")
        if video.video_id == self.host._selected_video_id:
            config = self.host._build_config()
            if (
                (tool in {"translation", "all"} and is_cloud_model(config.translation_model))
                or tool in {"voice", "all"}
                and config.tts_provider == "edge"
            ):
                self.bridge.require("online")

    @staticmethod
    def _accepted(value=True):
        return {"accepted": value is not False, "message": "Poll status; accepted does not mean completed."}

    @staticmethod
    def _video_data(video):
        fields = EDITABLE_FIELDS | {
            "video_id",
            "original_filename",
            "project_key",
            "project_type",
            "status",
            "progress",
            "step",
            "current_item",
            "total_items",
            "subtitle_language",
            "manual_target_tool",
            "created_at",
            "updated_at",
            "video_width",
            "video_height",
        }
        from haizflow.core.diagnostics import redact_diagnostic_text

        return {**video.model_dump(mode="json", include=fields),
                "error": redact_diagnostic_text(getattr(video, "error", "") or "")}

    def _capabilities(
        self, command_names: list[str] | None = None, area: str = "", include_schemas: bool = True,
    ) -> dict:
        from haizflow.desktop.catalog import POPULAR_TARGET_LANGUAGES
        from haizflow.mcp.efficiency import command_area

        areas = sorted({command_area(name) for name in COMMANDS})
        if area and area not in areas:
            raise ValueError("Unknown area. Read capabilities.areas.")
        if command_names is not None and (not 1 <= len(command_names) <= 20 or set(command_names) - COMMANDS):
            raise ValueError("Choose 1–20 known command names.")
        operations = {}
        for name in sorted(COMMANDS if command_names is None else set(command_names)):
            if area and command_area(name) != area:
                continue
            operations[name] = {"read_only": name in READ_COMMANDS, "area": command_area(name)}
            if not include_schemas:
                continue
            function = getattr(self, "_" + name)
            signature, adapters = command_signature(function.__func__)
            arguments, required = {}, []
            for key, item in signature.parameters.items():
                if key == "self":
                    continue
                schema = adapters[key].json_schema()
                if item.default is inspect.Parameter.empty:
                    required.append(key)
                else:
                    schema["default"] = item.default
                arguments[key] = schema
            operations[name]["input_schema"] = {
                "type": "object",
                "properties": arguments,
                "required": required,
                "additionalProperties": False,
            }
        return {
            "commands": operations,
            "areas": areas,
            "editable_fields": sorted(EDITABLE_FIELDS),
            "target_languages": [code for code, _, _ in POPULAR_TARGET_LANGUAGES],
            "confirmation": (
                "No app-side confirmation. User-authorized commands execute directly under session permissions."
            ),
            "excluded": ["secret/API key access", "arbitrary code/shell", "interactive sign-in automation"],
        }

    def _read_many(self, requests: list[dict]) -> dict:
        """Read up to eight small independent snapshots, without UI selection changes."""
        from haizflow.mcp.efficiency import encoded_size

        if not 1 <= len(requests) <= 8:
            raise ValueError("Choose 1–8 read requests.")
        calls = []
        for request in requests:
            if set(request) != {"command", "arguments"} or not isinstance(request["arguments"], dict):
                raise ValueError("Each read requires command and arguments only.")
            name = request["command"]
            if not isinstance(name, str) or name not in READ_COMMANDS - {"read_many", "visual_context"}:
                raise ValueError("read_many accepts read-only commands, not mutations, recursion or raw media context.")
            calls.append((name, self._validated_call(name, request["arguments"])))
        results = []
        for name, (function, bound) in calls:
            try:
                value = function(*bound.args, **bound.kwargs)
                if encoded_size(value) > 12000:
                    raise ValueError("Read result exceeds 12 KB. Request a smaller page or use its dedicated tool.")
                results.append({"command": name, "result": value})
            except ValueError as exc:
                results.append({"command": name, "error": self._safe_detail(str(exc))})
        return {"results": results, "atomic": False}

    def _observe(
        self, video_ids: list[str] | None = None, since: str = "",
        workflow: Literal["processing", "download", "social"] = "processing", project_id: str = "",
    ) -> dict:
        """Small live progress snapshot, including attention states; safe across project switches."""
        from haizflow.mcp.efficiency import observed, unsettled

        if workflow != "processing":
            if video_ids or not project_id or len(since) > 64:
                raise ValueError("Download/social observation needs project_id, no video IDs, and a valid cursor.")
            if workflow == "social":
                from haizflow.desktop.social_publish_controller import _POLLABLE_POST_STATUSES

                result = self._social_status(project_id, compact=True)
                social = self.host._tiktok_publisher
                active_items = [item for item in social._queue_items()
                                if item.get("status") in _POLLABLE_POST_STATUSES | {"queued_local"}]
                result["busy"] = bool(social.busy or active_items)
                result["active_items"] = [{key: item.get(key) for key in ("id", "status", "upload_progress")}
                                          for item in active_items[:20]]
                result["active_total"] = len(active_items)
            else:
                result = self._download_status(project_id)
                download = self.host._media_downloader
                result["busy"] = bool(download.hasWork or download.videoPreviewBusy or download.audioPreviewBusy)
            return observed({"workflow": workflow, "project_id": project_id,
                             "permissions": self.bridge.permissions, **result}, since)
        if project_id:
            raise ValueError("Processing observation uses video_ids, not project_id.")
        ids = list(dict.fromkeys(video_ids or []))
        if len(ids) > 20 or len(since) > 64:
            raise ValueError("Observe at most 20 videos; cursor must be at most 64 characters.")
        host = self.host
        active = host._processing_queue.active_video_id
        queued = host._processing_queue.pending_ids()
        if not ids:
            ids = list(dict.fromkeys([v for v in [active, host._selected_video_id, *queued] if v]))[:20]
        videos = []
        for video_id in ids:
            video = self._known_video(video_id)
            videos.append({**{key: getattr(video, key, None) for key in
                              ("video_id", "status", "progress", "step", "current_item", "total_items")},
                           "error": self._safe_detail(getattr(video, "error", "") or "")})
        scoped = bool(video_ids)
        jobs = [job for job in host._video_exports.jobs if not scoped or job.get("videoId") in ids]
        value = {
            "permissions": self.bridge.permissions,
            "videos": videos,
            "active_video_id": active if not scoped or active in ids else None,
            "queued_video_ids": [v for v in queued if not scoped or v in ids][:200],
            "queue_total": len([v for v in queued if not scoped or v in ids]),
            "exports": [{**{key: job.get(key) for key in ("videoId", "status", "progress")},
                         "output": job.get("path"), "error": self._safe_detail(job.get("error"))}
                        for job in jobs[-50:]],
            "export_total": len(jobs),
        }
        if not scoped:
            value.update(import_busy=bool(host._media_import_busy),
                         url_import_busy=host._url_importer.state in
                         {"inspecting", "downloading", "importing", "cancelling"})
        # Include all jobs, not just the displayed tail, in the idle decision.
        value["busy"] = unsettled({**value, "exports": jobs})
        return observed(value, since)

    def _status(self) -> dict:
        host = self.host
        return {
            "permissions": self.bridge.permissions,
            "selected_project_id": host._selected_project_key or "",
            "selected_video_id": host._selected_video_id or "",
            "active_video_id": host._processing_queue.active_video_id,
            "queued_video_ids": host._processing_queue.pending_ids(),
            "import_busy": bool(host._media_import_busy),
            "exports": [
                {**{key: job.get(key) for key in ("videoId", "status", "progress")},
                 "output": job.get("path"), "error": self._safe_detail(job.get("error"))}
                for job in host._video_exports.jobs
            ],
            "confirmation": self.bridge.approval,
            "url_import": {"state": host._url_importer.state, "progress": host._url_importer.progress,
                           "detail": self._safe_detail(getattr(host._url_importer, "status", ""))},
        }

    def _projects(self, offset: int = 0, limit: int = 50, query: str = "", kind: str = "") -> dict:
        if len(query) > 200 or kind not in {"", "manual", "single", "batch", "download", "publish"}:
            raise ValueError("Use a short project-name query and a supported project kind.")
        return page(
            [
                {key: item.get(key) for key in ("key", "project_name", "project_type")}
                for item in self.host._project_summaries_by_key.values()
                if (not query or query.casefold() in str(item.get("project_name", "")).casefold())
                and (not kind or item.get("project_type") == kind)
            ],
            offset,
            limit,
        )

    def _project(self, project_id: str, offset: int = 0, limit: int = 50, compact: bool = False) -> dict:
        project = self._known_project(project_id)
        selected = page([video for video in self.host._catalog_videos.values()
                         if self.host._video_project_key(video) == project_id], offset, limit)
        videos = [
            ({key: getattr(video, key, None) for key in ("video_id", "original_filename", "status", "progress", "step")}
             if compact else self._video_data(video))
            for video in selected["items"]
        ]
        return {
            "project_id": project_id,
            "name": project.get("project_name"),
            "kind": project.get("project_type"),
            "videos": videos,
            "total": selected["total"], "offset": offset,
        }

    def _video(self, video_id: str) -> dict:
        return self._video_data(self._known_video(video_id))

    def _subtitles(self, video_id: str, offset: int = 0, limit: int = 100) -> dict:
        self._selected(video_id, idle=False, manual=True)
        model = self.host._manual_subtitles
        if model.video_id != video_id:
            raise ValueError("Wait for the subtitle workspace to load.")
        result = page(
            [
                {key: cue.get(key) for key in ("segment_id", "revision", "start", "end", "text")}
                for cue in model.segments
            ],
            offset,
            limit,
        )
        result["revision"] = model.revision
        return result

    def _srt(self, video_id: str, kind: Literal["source", "result"] = "result") -> dict:
        from haizflow.services import editor_documents, subtitle_export

        video = self._selected(video_id, manual=True)
        document = editor_documents.load(video_id)
        content = (
            subtitle_export.compose_source_srt(video, document)
            if kind == "source"
            else subtitle_export.compose_document_srt(document)
        )
        return {"kind": kind, "content": content}

    def _open(self, project_id: str, video_id: str = "") -> dict:
        self._no_draft()
        project = self._known_project(project_id)
        video = self._known_video(video_id) if video_id else None
        if video and self.host._video_project_key(video) != project_id:
            raise ValueError("Video does not belong to this project.")
        accepted = self.host._select_project_summary(project)
        if accepted and video:
            self.host._select_video(video)
        return self._accepted(accepted)

    def _create(self, name: str, kind: Literal["manual", "single", "batch", "download", "publish"] = "manual") -> dict:
        from haizflow.services import project_store

        self._no_draft()
        project_store.validate_new_project_name(name)
        if not name.strip() or len(name) > 120:
            raise ValueError("Choose a project name between 1 and 120 characters.")
        if kind == "publish" and not self.host._tiktok_publisher.can_switch_project("__new_project__"):
            raise ValueError("Wait for the social publishing job before creating another publishing project.")
        if kind == "download" and not self.host._media_downloader.can_switch_project("__new_download_project__"):
            raise ValueError("Wait for the download job before creating another download project.")
        accepted = self.host._project_import.prepare_project(name, self.host._project_directory, kind)
        return {**self._accepted(accepted), "project_id": self.host._selected_project_key}

    def _rename(self, project_id: str, name: str) -> dict:
        from haizflow.services import project_store

        self._known_project(project_id)
        project_store.validate_new_project_name(name)
        return self._accepted(self.host._project_commands.rename_project(project_id, name))

    def _import_video(self, project_id: str, path: str) -> dict:
        project = self._current_project(project_id)
        if project["project_type"] not in {"manual", "single", "batch"}:
            raise ValueError("Use social_add or download_start for this project type.")
        if project["project_type"] != "batch" and any(
            self.host._video_project_key(v) == project_id for v in self.host._catalog_videos.values()
        ):
            raise ValueError("Source replacement is not implicit. Create a new project instead.")
        source = self._local_file(path, {".mp4", ".mov", ".mkv"})
        return self._accepted(self.host._project_import.import_video(str(source)))

    @staticmethod
    def _local_file(path, extensions):
        source = Path(path)
        if not source.is_absolute() or source.suffix.lower() not in extensions or not source.is_file():
            raise ValueError("Choose an existing local file with a supported extension and absolute path.")
        return source.resolve()

    def _configure(self, video_id: str, settings: dict) -> dict:
        video = self._selected(video_id)
        if not settings or set(settings) - EDITABLE_FIELDS:
            raise ValueError("Unknown/empty settings. Read capabilities.editable_fields.")
        data = {field: getattr(video, field) for field in VideoConfig.model_fields if hasattr(video, field)}
        # A small style/crop edit must not reset all the other appearance fields.
        settings = dict(settings)
        for field in ("subtitle_style", "crop"):
            if isinstance(settings.get(field), dict):
                settings[field] = {**getattr(video, field).model_dump(), **settings[field]}
        data.update(settings)
        from haizflow.core.translation_models import translation_provider

        data["translator_provider"] = translation_provider(str(data.get("translation_model") or "auto"))
        config = VideoConfig.model_validate(data, strict=True)
        from haizflow.desktop.catalog import TARGET_LANGUAGE_CODES

        if config.target_language not in TARGET_LANGUAGE_CODES:
            raise ValueError("Unsupported target language.")
        self.host._apply_config_to_video(video, config)
        self.host._select_video(video_store.get_video(video_id) or video)
        return {"accepted": True, "editable_fields": sorted(EDITABLE_FIELDS)}

    def _import_srt(
        self, video_id: str, path: str, language: Literal["vi", "en", "zh", "ja", "ko", "es"], replace: bool = False
    ) -> dict:
        from haizflow.services import subtitle_import

        video = self._selected(video_id, manual=True)
        source = self._local_file(path, {".srt"})
        if (self.host._manual_subtitles.segments or subtitle_import.has_import(video)) and not replace:
            raise ValueError("Existing subtitles would be replaced. Use replace=true only when requested by the user.")
        return self._accepted(self.host.importSelectedSrt(str(source), language, video_id))

    def _run(
        self, video_id: str, tool: Literal["separation", "translation", "image", "voice", "audio"],
        force_rerun: bool = False,
    ) -> dict:
        video = self._selected(video_id, manual=True)
        self._online(video, tool)
        return self._accepted(self.host.runManualTool(tool, force_rerun, confirm_existing_voice=False))

    def _pause(self, video_id: str) -> dict:
        video = self._selected(video_id, idle=False)
        if video.project_type == "batch":
            raise ValueError("Use batch_pause to pause the owned batch queue.")
        self.host._project_commands.stop_video(confirm=False)
        return self._accepted()

    def _resume(self, video_id: str) -> dict:
        video = self._selected(video_id)
        self._online(video)
        if video.status != "paused":
            raise ValueError("The job is not paused.")
        self.host.resumeSelectedVideo()
        return self._accepted(self.host._processing_queue.contains(video_id))

    def _export(
        self,
        video_id: str,
        destination: str,
        preset: Literal["source", "1080p", "1080p-high", "720p", "2160p"] = "source",
        overwrite: bool = False,
        process: bool = False,
        segment_id: str = "",
    ) -> dict:
        video = self._selected(video_id)
        if not Path(destination).is_absolute():
            raise ValueError("Export destination must be absolute.")
        if Path(destination).exists() and not overwrite:
            raise ValueError(
                "Export target already exists. Use overwrite=true only when the user requests replacement."
            )
        if process:
            if segment_id:
                raise ValueError("A segment export cannot also start a full Auto rerun.")
            if video.project_type not in {"single", "batch"}:
                raise ValueError("Processing and exporting together requires an Auto or Batch video.")
            self._online(video)
            return self._accepted(self.host.processVideoTo(video_id, preset, destination, overwrite))
        if segment_id:
            if video.project_type != "manual":
                raise ValueError("Segment exports require a Manual project.")
            return self._accepted(self.host.exportVideoSegmentTo(video_id, preset, destination, overwrite, segment_id))
        return self._accepted(self.host.exportVideoTo(video_id, preset, destination, overwrite))

    def _export_cancel(self) -> dict:
        self.host.cancelVideoExport()
        return self._accepted()

    def _edit_subtitle(self, video_id: str, segment_id: str, text: str, expected_revision: int) -> dict:
        import uuid

        self._selected(video_id, manual=True)
        if not text.strip() or len(text) > 10000:
            raise ValueError("Subtitle text must contain 1–10000 characters.")
        return self._accepted(self.host.saveManualSubtitleText(segment_id, text, expected_revision, str(uuid.uuid4())))

    def _subtitle_timing(self, video_id: str, segment_id: str, start: float, end: float) -> dict:
        import math

        self._selected(video_id, manual=True)
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("Invalid subtitle start/end seconds.")
        return self._accepted(self.host.saveManualSubtitleTiming(segment_id, start, end))

    def _merge_subtitle(self, video_id: str, segment_id: str) -> dict:
        self._selected(video_id, manual=True)
        return self._accepted(self.host.mergeSubtitleWithNext(segment_id))

    def _delete_subtitle(self, video_id: str, segment_id: str) -> dict:
        self._selected(video_id, manual=True)
        return self._accepted(self.host.deleteSubtitleSegment(segment_id))

    def _split_subtitle(self, video_id: str, segment_id: str, position_ms: int) -> dict:
        self._selected(video_id, manual=True)
        return {"segment_id": self.host.splitSubtitleSegment(segment_id, position_ms)}

    def _editor(self, video_id: str) -> dict:
        from haizflow.services import editor_documents

        self._selected(video_id, idle=False, manual=True)
        document = editor_documents.load(video_id)
        if not document:
            return {"document": None}
        # Asset paths and internal metadata are deliberately not returned.
        return {
            "revision": document.revision,
            "tracks": [t.model_dump(mode="json") for t in document.tracks],
            "clips": [
                {
                    key: c.model_dump(mode="json").get(key)
                    for key in (
                        "clip_id",
                        "track_id",
                        "kind",
                        "start_ms",
                        "duration_ms",
                        "name",
                        "segment_id",
                        "enabled",
                    )
                }
                for c in document.clips
            ],
        }

    def _undo(self, video_id: str) -> dict:
        self._selected(video_id, manual=True)
        self.host.undoManualEdit()
        return self._accepted()

    def _redo(self, video_id: str) -> dict:
        self._selected(video_id, manual=True)
        self.host.redoManualEdit()
        return self._accepted()

    def _clip_properties(self, video_id: str, clip_id: str, settings: dict) -> dict:
        self._selected(video_id, manual=True)
        return self._accepted(self.host.updateClipProperties(clip_id, settings))

    def _track_properties(self, video_id: str, track_id: str, settings: dict) -> dict:
        self._selected(video_id, manual=True)
        if not settings or set(settings) - {"visible", "muted"} or any(type(v) is not bool for v in settings.values()):
            raise ValueError("Track settings accept only visible/muted booleans.")
        return self._accepted(all(self.host.setTrackState(track_id, name, value) for name, value in settings.items()))

    def _source_cover(self, video_id: str, region: dict) -> dict:
        video = self._selected(video_id)
        return self._accepted(
            self.host.saveSourceCoverRegion(
                video_id, self.host._video_project_key(video), self.host._video_source_key(video), region
            )
        )

    def _auto_start(self, video_id: str) -> dict:
        video = self._selected(video_id)
        if video.project_type != "single":
            raise ValueError("Use run for Manual or batch_start for Batch.")
        self._online(video)
        return self._accepted(self.host.startProjectVideo())

    def _batch_settings(self, project_id: str) -> dict:
        self._current_project(project_id, "batch")
        return self.host.batchSettings()

    def _batch_configure(self, project_id: str, settings: dict, replace_overrides: bool = False) -> dict:
        self._current_project(project_id, "batch")
        if set(settings) - EDITABLE_FIELDS:
            raise ValueError("Unsupported batch setting.")
        return self._accepted(self.host.applyBatchSettingsValues(project_id, settings, replace_overrides))

    def _batch_start(self, project_id: str) -> dict:
        self._current_project(project_id, "batch")
        if not any(
            v.status == "pending"
            for v in self.host._catalog_videos.values()
            if self.host._video_project_key(v) == project_id
        ):
            raise ValueError("No pending videos in this batch.")
        for video in self.host._catalog_videos.values():
            if self.host._video_project_key(video) == project_id:
                self._online(video)
        self.host.startBatch()
        return self._accepted()

    def _batch_resume(self, project_id: str) -> dict:
        self._current_project(project_id, "batch")
        for video in self.host._catalog_videos.values():
            if self.host._video_project_key(video) == project_id:
                self._online(video)
        self.host.resumeBatch()
        return self._accepted()

    def _batch_pause(self, project_id: str) -> dict:
        self._current_project(project_id, "batch")
        self.host._project_commands.stop_batch(confirm=False)
        return self._accepted()

    def _resources(self) -> dict:
        return {"packs": self.host.resourcePackageRows}

    def _resource_install(self, pack_ids: list[str]) -> dict:
        self.bridge.require("online")
        if not 1 <= len(pack_ids) <= 20:
            raise ValueError("Choose between 1 and 20 resource packs.")
        return self._accepted(self.host.installResourcePacks(pack_ids))

    def _resource_cancel(self, pack_id: str) -> dict:
        return self._accepted(self.host.cancelResourcePackOperation(pack_id))

    def _manual_cancel(
        self, video_id: str, tool: Literal["separation", "translation", "image", "voice", "audio"]
    ) -> dict:
        video = self._selected(video_id, idle=False, manual=True)
        if video.manual_target_tool != tool:
            raise ValueError("The requested tool does not own the running job.")
        return self._accepted(self.host.cancelManualTool(tool))

    def _restart_snapshot(self, video_id):
        video = self._selected(video_id)
        if video.project_type == "manual":
            raise ValueError("Use an individual Manual tool or confirm the rerun in the app.")
        if video.status not in {"paused", "awaiting_review", "done", "failed", "cancelled"}:
            raise ValueError("This video cannot be restarted in its current state.")
        self._online(video)
        return {
            "video_id": video_id,
            "updated_at": video.updated_at,
            "config": self.host._build_config().model_dump(mode="json"),
        }

    def _prepare_restart(self, video_id: str) -> dict:
        snapshot = self._restart_snapshot(video_id)
        return {"ready": True, "requires_confirmation": False, "video_id": snapshot["video_id"]}

    def _restart(self, video_id: str, confirmation_token: str = "") -> dict:
        # The optional legacy token is ignored; readiness is always rechecked.
        self._restart_snapshot(video_id)
        self.host._project_commands.restart_selected_video(confirm=False)
        return self._accepted(self.host._processing_queue.contains(video_id))

    def _background_music(self, video_id: str, path: str) -> dict:
        self._selected(video_id)
        source = self._local_file(path, {".wav", ".mp3", ".m4a", ".flac", ".ogg"})
        return self._accepted(self.host._project_import.set_background_music(str(source)))

    def _voice_reference(
        self, video_id: str, path: str, transcript: str, provider: Literal["omnivoice", "vieneu"]
    ) -> dict:
        self._selected(video_id)
        source = self._local_file(path, {".wav", ".mp3", ".m4a", ".flac", ".ogg"})
        if not transcript.strip() or len(transcript) > 4000:
            raise ValueError("Provide the reference transcript (1–4000 characters).")
        if not self.host.setVoiceCloneReference(str(source), transcript):
            return self._accepted(False)
        return self._accepted(self.host.applyVoiceCloneReference(video_id, provider))

    def _watermark_asset(self, video_id: str, path: str, kind: Literal["image", "video"]) -> dict:
        self._selected(video_id)
        source = self._local_file(
            path, {".png", ".jpg", ".jpeg", ".webp"} if kind == "image" else {".mp4", ".mov", ".mkv"}
        )
        return self._accepted(
            self.host.setWatermarkImage(str(source)) if kind == "image" else self.host.setWatermarkVideo(str(source))
        )

    def _import_url_inspect(self, project_id: str, url: str) -> dict:
        project = self._current_project(project_id)
        self.bridge.require("online")
        if project["project_type"] not in {"manual", "single", "batch"}:
            raise ValueError("Use download_inspect for a Download project.")
        self.host._url_importer.begin(project["project_type"])
        self.host._url_importer.inspect(url)
        return self._accepted()

    @staticmethod
    def _safe_detail(value):
        from haizflow.core.diagnostics import redact_diagnostic_text

        return redact_diagnostic_text(value if isinstance(value, str) else "")

    def _replace_source(self, video_id: str, path: str) -> dict:
        video = self._selected(video_id)
        if video.project_type not in {"manual", "single", "batch"}:
            raise ValueError("Source replacement requires an Auto, Manual or Batch video.")
        source = self._local_file(path, {".mp4", ".mov", ".mkv"})
        return self._accepted(self.host._project_import.replace_video(video_id, str(source)))

    def _replace_url_inspect(self, video_id: str, url: str) -> dict:
        video = self._selected(video_id)
        self.bridge.require("online")
        project_id = self.host._video_project_key(video)
        if video.project_type not in {"manual", "single"}:
            raise ValueError("URL replacement requires an Auto or Manual video; use local replacement for Batch.")
        importer = self.host._url_importer
        if importer.busy:
            raise ValueError("Wait for the current URL import or cancel it first.")
        self._replacement_requests.pop(project_id, None)
        importer.begin(video.project_type)
        importer.inspect(url)
        self._replacement_requests[project_id] = (
            video_id, self.host._video_source_key(video), importer, importer._generation, importer.url,
        )
        return self._accepted()

    def _replace_url_start(self, video_id: str) -> dict:
        video = self._selected(video_id)
        self.bridge.require("online")
        importer = self.host._url_importer
        expected = (video_id, self.host._video_source_key(video), importer, importer._generation, importer.url)
        project_id = self.host._video_project_key(video)
        if self._replacement_requests.get(project_id) != expected:
            raise ValueError("Inspect this exact replacement URL/video again; the source or inspection changed.")
        if importer.state != "ready":
            raise ValueError("Wait for the replacement URL inspection to become ready.")
        # This normal app workflow snapshots the immutable target before download,
        # releases preview handles, and replaces/invalidate caches only after success.
        self.host.downloadInspectedVideo()
        if importer.busy:
            self._replacement_requests.pop(project_id, None)
        return self._accepted(importer.busy)

    def _remove_srt(self, video_id: str) -> dict:
        self._selected(video_id, manual=True)
        return self._accepted(self.host._project_commands.remove_selected_srt(video_id, confirm=False))

    def _export_srt(
        self, video_id: str, destination: str, kind: Literal["source", "result", "both"] = "result",
        overwrite: bool = False,
    ) -> dict:
        from haizflow.services import editor_documents, subtitle_export

        video = self._selected(video_id, manual=True)
        document = editor_documents.load(video_id)
        source = subtitle_export.compose_source_srt(video, document) if kind != "result" else ""
        result = subtitle_export.compose_document_srt(document) if kind != "source" else ""
        if kind == "both":
            paths = subtitle_export.save_srt_pair(source, result, destination, overwrite=overwrite)
        else:
            paths = [subtitle_export.save_srt(source if kind == "source" else result, destination, overwrite=overwrite)]
        return {"completed": True, "paths": [str(path) for path in paths]}

    def _options(self, video_id: str) -> dict:
        from haizflow.desktop.catalog import POPULAR_TARGET_LANGUAGES
        from haizflow.services.gemini_translation import MODELS
        from haizflow.services.translation_connections import list_connections
        from haizflow.services.translation_model_catalog import presets
        from haizflow.services.translation_api_policy import project_configuration

        video = self._known_video(video_id)
        language = video.subtitle_language or video.target_language
        return {
            "target_languages": [code for code, _, _ in POPULAR_TARGET_LANGUAGES],
            "gemini_models": MODELS,
            "translation_reasoning": project_configuration(video.translation_model,
                str(getattr(video, "translation_reasoning_effort", "") or ""), has_guidance=bool(
                    getattr(video, "gemini_translation_instructions", "")
                    or getattr(video, "gemini_translation_glossary", "")
                    or getattr(video, "gemini_translation_style", "balanced") != "balanced")),
            "translation_api_models": [{"value": "api:" + row["id"] if row["model"] else None,
                                        "provider": row["provider"], "model": row["model"], "label": row["label"],
                                        "value_prefix": "api:" + row["id"] + ":",
                                        "requires_model": not bool(row["model"]),
                                        "models": [{"value": "api:" + row["id"] + ":" + option["value"],
                                                    "model": option["value"], "label": option["label"]}
                                                   for option in presets(row["provider"])]}
                                       for row in list_connections()],
            "tts_providers": self.host.ttsProviderOptionsForLanguage(language),
            "voices": self.host.voiceOptionsForLanguageAndProvider(language, video.tts_provider),
            "export_presets": ["source", "1080p", "1080p-high", "720p", "2160p"],
        }

    def _logs(self, video_id: str, lines: int = 100) -> dict:
        from haizflow.core.diagnostics import _read_tail, redact_diagnostic_text

        self._known_video(video_id)
        if not 1 <= lines <= 500:
            raise ValueError("Choose 1–500 log lines.")
        root = Path(video_store.get_video_dir(video_id)).resolve()
        path = root / "logs.txt"
        if not path.is_file():
            return {"lines": []}
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Logs must belong to the selected video workspace.")
        return {"lines": redact_diagnostic_text(_read_tail(path, max_bytes=128 * 1024)).splitlines()[-lines:]}

    def _export_ranges(self, video_id: str) -> dict:
        from haizflow.services import editor_documents, result_segments

        self._selected(video_id, idle=False, manual=True)
        document = editor_documents.load(video_id)
        return {"items": result_segments.ranges(document) if document else []}

    def _export_batch(
        self, project_id: str, directory: str,
        preset: Literal["source", "1080p", "1080p-high", "720p", "2160p"] = "source",
        overwrite: bool = False, process: bool = False,
    ) -> dict:
        self._current_project(project_id, "batch")
        if not Path(directory).is_absolute() or not Path(directory).is_dir():
            raise ValueError("Choose an existing absolute export directory.")
        identifiers = list(self.host._batch_video_ids)
        if not identifiers:
            raise ValueError("The batch is empty.")
        for identifier in identifiers:
            video = self._known_video(identifier)
            if self.host._video_project_key(video) != project_id:
                raise ValueError("Batch membership changed; reload the project.")
            if process:
                self._online(video)
        return self._accepted(self.host.processBatchTo(project_id, identifiers, preset, directory, overwrite, process))

    def _export_retry(self) -> dict:
        for job in self.host._video_exports.jobs:
            video = self._known_video(job["videoId"])
            self._online(video)
        return self._accepted(self.host._video_exports.retry_failed())

    def _batch_import(self, project_id: str, paths: list[str]) -> dict:
        self._current_project(project_id, "batch")
        if not 1 <= len(paths) <= 100:
            raise ValueError("Import 1–100 videos at a time.")
        sources = [str(self._local_file(path, {".mp4", ".mov", ".mkv"})) for path in paths]
        return self._accepted(self.host._project_import.import_batch_videos(sources))

    def _batch_results(self, project_id: str) -> dict:
        self._current_project(project_id, "batch")
        return self.host.batchResults()

    def _review_save(self, video_id: str, segments: list[dict]) -> dict:
        import json

        self._selected(video_id)
        if not 1 <= len(segments) <= 10000:
            raise ValueError("Supply 1–10000 review segments.")
        return self._accepted(self.host.saveTranslationReviewDraft(json.dumps(segments, ensure_ascii=False)))

    def _review(self, video_id: str, offset: int = 0, limit: int = 100) -> dict:
        self._selected(video_id, idle=False)
        return page([
            {key: item.get(key) for key in ("segment_id", "start", "end", "text", "speaker")}
            for item in self.host.reviewSegments
        ], offset, limit)

    def _translation_snapshot(self, video_id):
        from haizflow.mcp.translation_review import snapshot

        video = self._selected(video_id)
        model = self.host._manual_subtitles
        if video.project_type == "manual" and model.video_id != video_id:
            raise ValueError("Wait for the subtitle workspace to load.")
        return video, snapshot(video, model.segments if video.project_type == "manual" else None)

    def _translation_context(
        self, video_id: str, offset: int = 0, limit: int = 50, query: str = "", cue_ids: list[str] | None = None,
        speaker: str = "",
    ) -> dict:
        from haizflow.mcp.translation_review import context_rows

        video, state = self._translation_snapshot(video_id)
        page([], offset, limit)  # Validate pagination before building time-overlap matches.
        if len(query) > 200 or len(speaker) > 200 or cue_ids is not None and not 1 <= len(cue_ids) <= 200:
            raise ValueError("Use a query/speaker up to 200 characters or 1–200 cue IDs.")
        wanted = set(cue_ids or [])
        if wanted - {f"cue-{index + 1}" for index in range(len(state["segments"]))}:
            raise ValueError("Unknown cue IDs. Read the current translation context.")
        indices = [index for index, cue in enumerate(state["segments"])
                   if (not wanted or f"cue-{index + 1}" in wanted)
                   and (not query or query.casefold() in str(cue["text"]).casefold())
                   and (not speaker or cue.get("speaker_id", cue.get("speaker", "")) == speaker)]
        result = {"items": context_rows(state, offset, limit, indices=indices), "offset": offset, "total": len(indices),
                  "total_cues": len(state["segments"])}
        return {**result, "revision": state["revision"], "target_language": video.target_language,
                "instructions": video.gemini_translation_instructions, "glossary": video.gemini_translation_glossary,
                "limitations": "Source matches use time overlap, not a guaranteed one-to-one sentence alignment. "
                               "Speaker labels are fallible. Inspect frames/dialogue before changing address terms."}

    def _translation_patch(self, video_id: str, edits: list[dict], expected_revision: str) -> dict:
        import json

        from haizflow.mcp.translation_review import patch

        video, state = self._translation_snapshot(video_id)
        updated, changed = patch(state, edits, expected_revision)
        if not changed:
            return {"accepted": True, "changed": [], "processing_started": False}
        if video.project_type == "manual":
            replacements = {old.get("segment_id"): new["text"] for old, new in zip(state["segments"], updated)
                            if old["text"] != new["text"]}
            if not all(replacements):
                raise ValueError("Manual cue IDs are not ready. Reload subtitles before editing.")

            def mutate(document):
                for clip in document.clips:
                    if clip.segment_id not in replacements:
                        continue
                    if clip.track_id == "subtitles":
                        clip.name = replacements[clip.segment_id]
                    elif clip.track_id == "voice":
                        clip.name = replacements[clip.segment_id]
                        clip.enabled = False
                        clip.metadata.update(state="stale", text_revision=0)

            accepted = self.host._apply_editor_mutation("edit_translation_text", mutate)
        else:
            accepted = self.host._project_commands.approve_translation_review(
                json.dumps(updated, ensure_ascii=False), continue_processing=False,
            )
        return {"accepted": bool(accepted), "changed": changed if accepted else [],
                "processing_started": False, "downstream_rebuild_required": bool(accepted)}

    def _voice_configuration(self, video_id: str, segment_id: str = "") -> dict:
        self._selected(video_id, idle=False, manual=True)
        return self.host.manualVoiceConfiguration(segment_id)

    def _visual_context(self, video_id: str) -> dict:
        import srt

        from haizflow.mcp.visuals import revision
        from haizflow.pipeline.manual_tools import _ocr_region
        from haizflow.pipeline.sequence_compiler import resolved_subtitle_style
        from haizflow.services import editor_documents, subtitle_export, video_export

        video = self._selected(video_id)
        root = Path(video_store.get_video_dir(video_id)).resolve()

        def owned_path(value):
            path = Path(value or "")
            if not path.is_file() or not path.resolve().is_relative_to(root):
                raise ValueError("Preview media must belong to this video's workspace.")
            return str(path.resolve())

        source = owned_path((video.files or {}).get("video_input"))
        document = editor_documents.load(video_id) if video.project_type == "manual" else None
        if document:
            cues = [{"start": c.start.total_seconds(), "end": c.end.total_seconds(), "text": c.content}
                    for c in srt.parse(subtitle_export.compose_document_srt(document))]
        else:
            cues = [{k: c.get(k) for k in ("start", "end", "text")} for c in self.host.reviewSegments]
        if len(cues) > 2000 or sum(len(c.get("text", "")) for c in cues) > 200000:
            raise ValueError("Visual preview subtitle budget exceeded; use a shorter project/segment.")
        record = video_export.current_render(video, verify=False)
        rendered = owned_path(record["resolved_outputs"]["video"]) if record else ""
        context = {
            "video_id": video_id, "source_key": self.host._video_source_key(video),
            "source_path": source, "render_path": rendered,
            "source_identity": [Path(source).stat().st_size, Path(source).stat().st_mtime_ns],
            "width": video.video_width, "height": video.video_height,
            "style": resolved_subtitle_style(document, video.subtitle_style).model_dump(),
            "language": str(getattr(video, "subtitle_language", "") or getattr(video, "target_language", "")),
            "crop": video.crop.model_dump(),
            "output_format": video.output_format, "output_speed": video.output_speed,
            "cover_region": _ocr_region(video), "cues": cues,
            "document_revision": document.revision if document else video.updated_at,
        }
        context["revision"] = revision(context)
        return context

    def _subtitle_layout_apply(self, video_id: str, style_patch: dict, expected_revision: str) -> dict:
        from haizflow.mcp.visuals import layout_report

        context = self._visual_context(video_id)
        if not expected_revision or context["revision"] != expected_revision:
            raise ValueError("Source/subtitles/settings changed. Preview the layout again before applying.")
        if not style_patch or set(style_patch) - set(context["style"]):
            raise ValueError("Supply only known subtitle style fields.")
        # Detailed font/phrase analysis runs in the MCP worker, not Qt's GUI
        # thread. Applying only needs bounded geometry and revision checks.
        report = layout_report({**context, "cues": []}, style_patch)
        if any("outside" in issue for issue in report["issues"]):
            raise ValueError("The proposed subtitle box extends outside the output frame.")
        result = self._configure(video_id, {"subtitle_style": style_patch, "subtitle_layout_override": True})
        return {**result, "report": report}

    def _voice_run(
        self, video_id: str,
        provider: Literal["edge", "omnivoice", "omnivoice-gpu", "vieneu", "vieneu-gpu"],
        voice: str, speaker_mode: Literal["single", "multiple"] = "single", segment_id: str = "",
    ) -> dict:
        self._selected(video_id, manual=True)
        if provider == "edge":
            self.bridge.require("online")
        if not voice.strip() or len(voice) > 200:
            raise ValueError("Choose a voice ID returned by options or voice_configuration.")
        return self._accepted(self.host.configureAndRunManualVoice(
            provider, voice, "segment" if segment_id else "all", segment_id, speaker_mode,
        ))

    def _review_approve(self, video_id: str, segments: list[dict]) -> dict:
        import json

        video = self._selected(video_id)
        self._online(video)
        if not 1 <= len(segments) <= 10000:
            raise ValueError("Supply 1–10000 review segments.")
        return self._accepted(self.host.approveTranslationReview(json.dumps(segments, ensure_ascii=False)))

    def _subtitle_replace(
        self, video_id: str, search: str, replacement: str, case_sensitive: bool = False,
        replace_all: bool = False, segment_id: str = "",
    ) -> dict:
        self._selected(video_id, manual=True)
        if not search or len(search) > 10000 or len(replacement) > 10000 or not replace_all and not segment_id:
            raise ValueError("Supply bounded text and an exact segment_id or replace_all=true.")
        return {"changed": self.host.replaceSubtitleText(search, replacement, case_sensitive, replace_all, segment_id)}

    def _text_style(self, video_id: str, clip_ids: list[str], style: dict) -> dict:
        from haizflow.schemas.editor import EditorTextStyle

        self._selected(video_id, manual=True)
        if not 1 <= len(clip_ids) <= 200 or not style or set(style) - set(EditorTextStyle.model_fields):
            raise ValueError("Choose 1–200 subtitle clips and known style fields.")
        return self._accepted(self.host.applyTextStyle(clip_ids, style, "selected"))

    def _clip_trim(self, video_id: str, clip_id: str, edge: Literal["left", "right"], time_ms: int) -> dict:
        self._selected(video_id, manual=True)
        if time_ms < 0:
            raise ValueError("Timeline position must be non-negative.")
        return self._accepted(self.host.trimClip(clip_id, edge, time_ms))

    def _clip_move(self, video_id: str, clip_id: str, start_ms: int) -> dict:
        self._selected(video_id, manual=True)
        if start_ms < 0:
            raise ValueError("Timeline position must be non-negative.")
        return self._accepted(self.host.moveClip(clip_id, start_ms, ""))

    def _clip_remove(self, video_id: str, clip_ids: list[str]) -> dict:
        self._selected(video_id, manual=True)
        if not 1 <= len(clip_ids) <= 200:
            raise ValueError("Choose 1–200 clip IDs.")
        return self._accepted(self.host.removeClips(clip_ids, False))

    def _result_split(self, video_id: str, clip_id: str, time_ms: int) -> dict:
        self._selected(video_id, manual=True)
        if time_ms < 0:
            raise ValueError("Timeline position must be non-negative.")
        return self._accepted(self.host.splitResultClip(clip_id, time_ms))

    def _background_music_clear(self, video_id: str) -> dict:
        self._selected(video_id)
        return self._accepted(self.host.clearBackgroundMusic())

    def _voice_reference_clear(self, video_id: str) -> dict:
        self._selected(video_id)
        return self._accepted(self.host.clearVoiceCloneReference())

    def _download_clear_queue(self, project_id: str) -> dict:
        self._current_project(project_id, "download")
        self.host._media_downloader.clearQueuedDownloads()
        return self._accepted()

    def _download_preview_cancel(self, project_id: str, kind: Literal["video", "audio"] = "video") -> dict:
        self._current_project(project_id, "download")
        download = self.host._media_downloader
        if kind == "video":
            download.cancelVideoPreview()
        else:
            download.cancelAudioPreview()
        return self._accepted()

    def _channel_candidates(self, project_id: str, offset: int = 0, limit: int = 100) -> dict:
        self._current_project(project_id, "download")
        items = self.host._media_downloader.channelCandidateModel.candidates()
        return page([{"candidate_id": item.remote_video_id, "title": item.title, "selected": item.selected,
                      "status": item.status, "progress": item.progress, "duplicate": item.duplicate,
                      "error": self._safe_detail(item.error)} for item in items], offset, limit)

    def _channel_retry(self, project_id: str, candidate_id: str) -> dict:
        self._current_project(project_id, "download")
        self.bridge.require("online")
        download = self.host._media_downloader
        items = download.channelCandidateModel.candidates()
        row = next((i for i, item in enumerate(items) if item.remote_video_id == candidate_id), -1)
        if row < 0:
            raise ValueError("Unknown channel candidate_id. Refresh channel_candidates.")
        download.retryChannelVideo(row)
        return self._accepted()

    def _social_defaults(self, project_id: str, caption: str, hashtags: str, apply_to_existing: bool = False) -> dict:
        self._current_project(project_id, "publish")
        if len(caption) > 10000 or len(hashtags) > 4000:
            raise ValueError("Caption/hashtags too long.")
        return self._accepted(self.host._tiktok_publisher.save_defaults(caption, hashtags, apply_to_existing))

    def _social_remove(self, project_id: str, item_id: str) -> dict:
        self._current_project(project_id, "publish")
        self.bridge.require("delete")
        social = self.host._tiktok_publisher
        row = next((i for i, item in enumerate(social._queue_items()) if item["id"] == item_id), -1)
        if row < 0:
            raise ValueError("Unknown social queue item_id.")
        # Removes only the queue row; never deletes the video file or remote post.
        return self._accepted(social.remove_item(row, confirm=False))

    def _resource_repair(self, pack_id: str) -> dict:
        self.bridge.require("online")
        if pack_id not in {row["packId"] for row in self.host.resourcePackageRows}:
            raise ValueError("Unknown resource pack ID.")
        self.host.repairResourcePack(pack_id)
        return self._accepted()

    def _resource_discard(self, pack_id: str) -> dict:
        self.bridge.require("delete")
        if pack_id not in {row["packId"] for row in self.host.resourcePackageRows}:
            raise ValueError("Unknown resource pack ID.")
        self.host.discardResourcePackDownload(pack_id)
        return self._accepted()

    def _resource_remove(self, pack_id: str) -> dict:
        self.bridge.require("delete")
        if pack_id not in {row["packId"] for row in self.host.resourcePackageRows}:
            raise ValueError("Unknown resource pack ID.")
        return self._accepted(self.host.removeResourcePack(pack_id))

    def _import_url_start(self, project_id: str) -> dict:
        project = self._current_project(project_id)
        self.bridge.require("online")
        if project["project_type"] != "batch" and any(
            self.host._video_project_key(v) == project_id for v in self.host._catalog_videos.values()
        ):
            raise ValueError("This would replace an existing source. Use a new project.")
        if self.host._url_importer.state != "ready":
            raise ValueError("Inspect the video URL and wait for its ready state first.")
        self.host.downloadInspectedVideo()
        return self._accepted(self.host._url_importer.busy)

    def _import_url_cancel(self, project_id: str) -> dict:
        self._current_project(project_id)
        self.host._url_importer.cancel()
        return self._accepted()

    def _download_status(self, project_id: str) -> dict:
        self._current_project(project_id, "download")
        download = self.host._media_downloader
        return {
            "state": download.state,
            "detail": self._safe_detail(download.status),
            "progress": download.progress,
            "queue_count": download.queueCount,
            "channel_state": download.channelState,
            "channel_detail": self._safe_detail(download.channelStatus),
            "channel_progress": download.channelProgress,
            "channel_count": download.channelCandidateCount,
            "channel_selected": download.channelSelectedCount,
            "video_preview_ready": download.videoPreviewReady,
            "audio_preview_ready": download.audioPreviewReady,
        }

    def _download_inspect(self, project_id: str, url: str, kind: Literal["video", "audio"] = "video") -> dict:
        self._current_project(project_id, "download")
        self.bridge.require("online")
        if kind == "video":
            self.host._media_downloader.inspectVideo(url)
        else:
            self.host._media_downloader.inspectAudio(url)
        return self._accepted()

    def _download_start(self, project_id: str, url: str, kind: Literal["video", "audio"] = "video") -> dict:
        self._current_project(project_id, "download")
        self.bridge.require("online")
        if kind == "video":
            self.host._media_downloader.downloadVideo(url)
        else:
            self.host._media_downloader.downloadAudio(url)
        return self._accepted()

    def _download_cancel(self, project_id: str, channel: bool = False) -> dict:
        self._current_project(project_id, "download")
        if channel:
            self.host._media_downloader.cancelChannel()
        else:
            self.host._media_downloader.cancel()
        return self._accepted()

    def _channel_scan(
        self,
        project_id: str,
        url: str,
        platform: str,
        ranking: str = "newest",
        limit: int = 50,
        duration_filter: str = "all",
        scan_scope: int = 300,
    ) -> dict:
        self._current_project(project_id, "download")
        self.bridge.require("online")
        if not 1 <= limit <= 100 or not 0 <= scan_scope <= 10000:
            raise ValueError("Invalid channel scan limits.")
        self.host._media_downloader.inspectChannel(url, platform, ranking, limit, duration_filter, scan_scope)
        return self._accepted()

    def _channel_select(self, project_id: str, row: int = -1, selected: bool = True) -> dict:
        self._current_project(project_id, "download")
        if row == -1:
            self.host._media_downloader.selectAllChannel(selected)
        else:
            self.host._media_downloader.setChannelSelected(row, selected)
        return self._accepted()

    def _channel_download(self, project_id: str) -> dict:
        self._current_project(project_id, "download")
        self.bridge.require("online")
        self.host._media_downloader.downloadSelectedChannel()
        return self._accepted()

    def _social_status(
        self, project_id: str, offset: int = 0, limit: int = 50, compact: bool = False,
        item_ids: list[str] | None = None,
    ) -> dict:
        from collections import Counter

        self._current_project(project_id, "publish")
        social = self.host._tiktok_publisher
        if item_ids is not None and not 1 <= len(item_ids) <= 200:
            raise ValueError("Choose 1–200 publishing item IDs.")
        items = social._queue_items()
        if item_ids is not None:
            if set(item_ids) - {item["id"] for item in items}:
                raise ValueError("Unknown publishing item IDs.")
            items = [item for item in items if item["id"] in item_ids]
        fields = (("id", "status", "upload_progress") if compact else
                  ("id", "file_name", "caption", "hashtags", "status", "upload_progress"))
        result = {
            "busy": social.busy,
            "platform": social.selected_platform,
            "selected_account_id": social._state.get("selected_account_id"),
            "total": len(items), "offset": offset,
            "status_counts": dict(Counter(str(item.get("status") or "unknown") for item in items)),
            "items": [
                {**{key: item.get(key) for key in fields}, "error": self._safe_detail(item.get("error")),
                 "post_url": social._model_item(item).get("platform_post_url", "")}
                for item in page(items, offset, limit)["items"]
            ],
        }
        if not compact:
            result.update(accounts=[
                {"id": social._object_id(a), "name": social._account_label(a), "platform": social._account_platform(a)}
                for a in social._accounts
            ], settings=social._publish_settings_snapshot())
        return result

    def _social_add(self, project_id: str, paths: list[str]) -> dict:
        self._current_project(project_id, "publish")
        if not 1 <= len(paths) <= 100:
            raise ValueError("Import between 1 and 100 local videos.")
        sources = [str(self._local_file(path, {".mp4", ".mov", ".mkv", ".webm"})) for path in paths]
        return self._accepted(self.host._tiktok_publisher.add_videos(sources))

    def _social_edit(self, project_id: str, item_id: str, caption: str, hashtags: str) -> dict:
        self._current_project(project_id, "publish")
        if len(caption) > 10000 or len(hashtags) > 4000:
            raise ValueError("Caption/hashtags too long.")
        return self._accepted(
            self.host._tiktok_publisher.update_item_token(f"{project_id}:{item_id}", caption, hashtags)
        )

    def _social_select_account(self, project_id: str, account_id: str) -> dict:
        self._current_project(project_id, "publish")
        self.bridge.require("online")
        social = self.host._tiktok_publisher
        index = next((i for i, account in enumerate(social._accounts) if social._object_id(account) == account_id), -1)
        if index < 0:
            raise ValueError("Unknown connected account.")
        return self._accepted(social.select_account(index))

    def _social_settings(
        self,
        project_id: str,
        privacy_level: str,
        publish_now: bool = True,
        allow_comment: bool = True,
        allow_duet: bool = False,
        allow_stitch: bool = False,
        share_to_feed: bool = True,
        ai_generated: bool = False,
        first_comment: str = "",
    ) -> dict:
        self._current_project(project_id, "publish")
        return self._accepted(
            self.host._tiktok_publisher.set_publish_settings(
                privacy_level,
                publish_now,
                allow_comment,
                allow_duet,
                allow_stitch,
                share_to_feed,
                ai_generated,
                first_comment,
            )
        )

    def _social_refresh(self, project_id: str) -> dict:
        self._current_project(project_id, "publish")
        self.bridge.require("online")
        return self._accepted(self.host._tiktok_publisher.refresh_post_statuses())

    def _social_cancel(self, project_id: str) -> dict:
        self._current_project(project_id, "publish")
        self.host._tiktok_publisher.cancel()
        return self._accepted()

    def _delete_snapshot(self, project_id):
        from haizflow.services import project_store

        project = self._known_project(project_id)
        project = project_store.get_project(project_id) or project
        videos = [
            video_store.get_video(v.video_id) or v
            for v in self.host._catalog_videos.values()
            if self.host._video_project_key(v) == project_id
        ]
        if (
            any(self.host._processing_queue.contains(v.video_id) for v in videos)
            or self.host._project_import.has_project_work(project_id)
            or self.host._media_downloader.has_project_work(project_id)
            or self.host._tiktok_publisher.has_project_work(project_id)
            or self.host._video_exports.busy
        ):
            raise ValueError("Wait for or pause/cancel project work before deleting it.")
        return (
            project,
            videos,
            {
                "project_id": project_id,
                "name": project.get("project_name"),
                "root": project.get("project_root"),
                "videos": sorted((v.video_id, v.updated_at) for v in videos),
            },
        )

    def _prepare_delete(self, project_id: str) -> dict:
        self.bridge.require("delete")
        self._no_draft()
        project, videos, _ = self._delete_snapshot(project_id)
        return {
            "ready": True,
            "requires_confirmation": False,
            "project_id": project_id,
            "name": project["project_name"],
            "video_count": len(videos),
        }

    def _delete(self, project_id: str, confirmation_token: str = "") -> dict:
        self.bridge.require("delete")
        self._no_draft()
        project, videos, _ = self._delete_snapshot(project_id)
        return self._accepted(self.host._project_commands._delete_confirmed_project(project, videos))

    def _publish_snapshot(self, project_id, item_ids):
        self._current_project(project_id, "publish")
        social = self.host._tiktok_publisher
        if not item_ids or len(item_ids) > 100 or len(set(item_ids)) != len(item_ids):
            raise ValueError("Choose 1–100 distinct item IDs.")
        items = {item["id"]: item for item in social._queue_items()}
        if any(item_id not in items or not social._waiting_to_publish(items[item_id]) for item_id in item_ids):
            raise ValueError("Some items are missing, already published or in flight.")
        snapshot = {
            "project_id": project_id,
            "account_id": social._state.get("selected_account_id"),
            "platform": social.selected_platform,
            "settings": social._publish_settings_snapshot(),
            "items": [
                {key: items[i].get(key) for key in ("id", "file_path", "caption", "hashtags", "status")}
                for i in item_ids
            ],
        }
        if not snapshot["account_id"]:
            raise ValueError("Choose a connected publishing account before publishing.")
        for item in snapshot["items"]:
            path = Path(item["file_path"])
            if not path.is_file():
                raise ValueError("A selected publishing video is missing. Import it again before publishing.")
            stat = path.stat()
            item["file_identity"] = [stat.st_size, stat.st_mtime_ns]
        return snapshot

    def _prepare_publish(self, project_id: str, item_ids: list[str]) -> dict:
        self.bridge.require("publish")
        self.bridge.require("online")
        snapshot = self._publish_snapshot(project_id, item_ids)
        return {
            "ready": True,
            "requires_confirmation": False,
            "project_id": project_id,
            "item_ids": item_ids,
            "account_id": snapshot["account_id"],
            "settings": snapshot["settings"],
        }

    def _publish(self, project_id: str, item_ids: list[str], confirmation_token: str = "") -> dict:
        self.bridge.require("publish")
        self.bridge.require("online")
        self._publish_snapshot(project_id, item_ids)
        social = self.host._tiktok_publisher
        accepted = []
        previous = social._consent_confirmed
        try:
            social.set_consent_confirmed(True)
            for item_id in item_ids:
                if not social.publish_token(f"{project_id}:{item_id}"):
                    break
                accepted.append(item_id)
        finally:
            social.set_consent_confirmed(previous)
        return {
            "accepted_item_ids": accepted,
            "requested_item_ids": item_ids,
            "message": "Only these exact items were submitted/queued; poll social_status.",
        }
