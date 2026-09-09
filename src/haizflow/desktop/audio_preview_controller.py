"""Model-free audio previews for voice selection and mix controls."""

from __future__ import annotations

import os
import re
from pathlib import Path

from haizflow.services import video_store


class AudioPreviewController:
    """Expose existing media tracks without invoking translation or TTS.

    Voice rows use only packaged, sentence-locked samples.  Mix preview may
    reuse a verified voice part from the *selected* video so it represents the
    current edit, but it never searches another project. No model is loaded by
    this class.
    """

    _PACKAGED_SAMPLE_DIR = Path(__file__).resolve().parent / "assets" / "voice_samples"

    def __init__(self, host):
        self._host = host

    def invalidate(self) -> None:
        """Clear the current player sources when project context changes."""
        host = self._host
        host._audio_preview_source = ""
        host._audio_preview_original_source = ""
        host._audio_preview_background_music_source = ""
        host._audio_preview_state = "idle"
        host.audioPreviewChanged.emit()

    def start(
        self,
        *,
        video_id: str | None = None,
        enable_audio_separation: bool | None = None,
        background_music_path: str | None = None,
        original_volume: int | None = None,
        background_music_volume: int | None = None,
        tts_volume: int | None = None,
        voice: str | None = None,
        provider: str | None = None,
        target_language: str | None = None,
        voice_only: bool = False,
    ) -> bool:
        """Publish existing sample/track URLs immediately, without synthesis."""
        del original_volume, background_music_volume, tts_volume
        host = self._host
        selected_video_id = video_id if video_id is not None else getattr(host, "_selected_video_id", None)
        video = video_store.get_video(selected_video_id) if selected_video_id else None
        files = dict((video.files if video else {}) or {})
        effective_voice = str(getattr(host, "_tts_voice", "") if voice is None else voice)
        effective_provider = str(getattr(host, "_tts_provider", "omnivoice") if provider is None else provider)
        effective_language = str(
            getattr(host, "_target_language", "en") if target_language is None else target_language
        )

        packaged_voice_path = self.voice_sample_path(
            effective_provider,
            effective_voice,
            effective_language,
            selected_video_id=str(selected_video_id or ""),
        )
        if voice_only:
            return self._publish_sources(voice_path=packaged_voice_path, voice_only=True)

        voice_path = self._sample_from_video(video, effective_provider, effective_voice) or packaged_voice_path

        use_audio_separation = (
            bool(getattr(host, "_enable_audio_separation", False))
            if enable_audio_separation is None
            else bool(enable_audio_separation)
        )
        video_input = str(files.get("video_input") or getattr(host, "_video_path", "") or "")
        separated_background = str(files.get("background_audio") or "")
        if use_audio_separation:
            # Never use the complete source track here: it would reintroduce
            # the original speaker while the replacement voice is previewed.
            source_path = separated_background if self._valid_media(separated_background) else ""
        else:
            source_path = video_input if self._valid_media(video_input) else ""
        requested_music = str(
            getattr(host, "_background_music_path", "") if background_music_path is None else background_music_path
        )
        music_path = requested_music if self._valid_media(requested_music) else ""
        return self._publish_sources(
            voice_path=voice_path,
            source_path=source_path,
            music_path=music_path,
            voice_only=False,
        )

    def has_voice_sample(
        self,
        provider: str,
        voice: str,
        target_language: str,
        *,
        selected_video_id: str = "",
    ) -> bool:
        return bool(
            self.voice_sample_path(
                provider,
                voice,
                target_language,
                selected_video_id=selected_video_id,
            )
        )

    def voice_sample_path(
        self,
        provider: str,
        voice: str,
        target_language: str,
        *,
        selected_video_id: str = "",
    ) -> str:
        """Resolve an exact prerecorded sample; never synthesize a fallback."""
        provider = str(provider or "").strip().lower()
        voice = str(voice or "").strip()
        language = str(target_language or "").strip().lower()
        if not voice:
            return ""

        packaged = self._packaged_sample_path(provider, voice, language)
        if packaged:
            return packaged

        selected = video_store.get_video(selected_video_id) if selected_video_id else None
        if voice == "omnivoice:clone":
            reference = str(((selected.files if selected else {}) or {}).get("voice_reference") or "")
            return reference if self._valid_media(reference) else ""

        return ""

    def _publish_sources(
        self,
        *,
        voice_path: str = "",
        source_path: str = "",
        music_path: str = "",
        voice_only: bool,
    ) -> bool:
        host = self._host
        if not any(self._valid_media(path) for path in (voice_path, source_path, music_path)):
            host._audio_preview_source = ""
            host._audio_preview_original_source = ""
            host._audio_preview_background_music_source = ""
            host._audio_preview_state = "failed"
            host._status_message = (
                "No prerecorded sample is available for this voice."
                if voice_only
                else "No existing audio is available for this preview."
            )
            host.statusMessageChanged.emit()
            host.audioPreviewChanged.emit()
            return False

        host._audio_preview_source = self._media_url(voice_path)
        host._audio_preview_original_source = self._media_url(source_path)
        host._audio_preview_background_music_source = self._media_url(music_path)
        host._audio_preview_state = "ready"
        host._status_message = "Voice preview is ready." if voice_only else "Audio mix preview is ready."
        host.statusMessageChanged.emit()
        host.audioPreviewChanged.emit()
        return True

    @classmethod
    def _sample_from_video(cls, video, provider: str, voice: str) -> str:
        if video is None:
            return ""
        if str(getattr(video, "tts_provider", "") or "").strip().lower() != provider:
            return ""
        if str(getattr(video, "tts_voice", "") or "").strip() != voice:
            return ""
        checkpoints = dict(getattr(video, "checkpoints", {}) or {})
        if not checkpoints.get("voice"):
            return ""
        parts_dir = Path(video_store.get_video_dir(video.video_id)) / "temp" / "voice_parts"
        for candidate in sorted(parts_dir.glob("voice_*.mp3")):
            if cls._valid_media(str(candidate)):
                return str(candidate)
        return ""

    @classmethod
    def _packaged_sample_path(cls, provider: str, voice: str, language: str) -> str:
        safe_voice = re.sub(r"[^a-zA-Z0-9._-]+", "_", voice).strip("_")
        candidates = (
            cls._PACKAGED_SAMPLE_DIR / provider / safe_voice / f"{language}.mp3",
            cls._PACKAGED_SAMPLE_DIR / provider / safe_voice / "default.mp3",
            cls._PACKAGED_SAMPLE_DIR / provider / f"{safe_voice}.mp3",
        )
        for candidate in candidates:
            if cls._valid_media(str(candidate)):
                return str(candidate)
        return ""

    @staticmethod
    def _valid_media(path: str) -> bool:
        return bool(path and os.path.isfile(path) and os.path.getsize(path) > 0)

    @staticmethod
    def _remove_stale_preview_files(preview_dir: Path, keep: set[Path]) -> None:
        """Remove only legacy controller-owned preview tracks.

        The current controller does not generate preview media.  This narrow
        cleanup remains for projects upgraded from releases that wrote
        ``voice-*`` and ``source-*`` files into their preview directory.
        """
        preview_dir = Path(preview_dir)
        if not preview_dir.is_dir():
            return
        kept = {Path(path).resolve() for path in keep}
        for pattern in ("voice-*", "source-*", "music-*", "background-*"):
            for candidate in preview_dir.glob(pattern):
                if not candidate.is_file() or candidate.resolve() in kept:
                    continue
                try:
                    candidate.unlink()
                except OSError:
                    continue

    @classmethod
    def _media_url(cls, path: str) -> str:
        return Path(path).resolve().as_uri() if cls._valid_media(path) else ""

    def drain_events(self) -> None:
        """Compatibility no-op: model-free previews complete synchronously."""
