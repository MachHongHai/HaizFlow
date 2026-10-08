"""Download supported social videos into a project-owned staging directory."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from haizflow.config import BIN_DIR, MEDIA_PROCESS_TIMEOUT_SECONDS
from haizflow.utils.ffmpeg import get_media_stream_types

SUPPORTED_VIDEO_HOSTS = {
    "b23.tv": "Bilibili",
    "bilibili.com": "Bilibili",
    "douyin.com": "Douyin",
    "iesdouyin.com": "Douyin",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "instagram.com": "Instagram",
    "redd.it": "Reddit",
    "reddit.com": "Reddit",
    "streamable.com": "Streamable",
    "tiktok.com": "TikTok",
    "x.com": "X",
    "twitter.com": "X",
    "youtu.be": "YouTube",
    "youtube.com": "YouTube",
}
SUPPORTED_DOWNLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv"}
SUPPORTED_AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".mp4", ".ogg", ".opus", ".wav", ".webm"}
_TIKTOK_TRANSIENT_ERROR_MARKERS = (
    "failed to parse json",
    "unexpected response from webpage request",
    "unable to extract universal data for rehydration",
    "unable to extract webpage video data",
    "unable to download api page",
    "http error 429",
    "http error 502",
    "http error 503",
    "http error 504",
    "timed out",
    "timeout",
)
_FORMAT_REFRESH_ERROR_MARKERS = (
    "requested format is not available",
    "no video formats found",
    "no formats found",
    "unable to download video data",
    "video data is empty",
    "postprocessing:",
    "unable to obtain file audio codec with ffprobe",
    "invalid data found when processing input",
    "moov atom not found",
)
_NETWORK_RETRY_ERROR_MARKERS = (
    "http error 403",
    "http error 429",
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "cloudflare",
    "tls fingerprint",
    "timed out",
    "timeout",
    "connection reset",
    "remote end closed connection",
    "temporary failure in name resolution",
    "name or service not known",
    "getaddrinfo failed",
    "failed to resolve",
    "network is unreachable",
    "connection aborted",
    "connection refused",
    "connection timed out",
    "read timed out",
    "read operation timed out",
    "incompleteread",
    "broken pipe",
    "winerror 10054",
    "winerror 10060",
    "unable to download webpage",
    "unable to download json metadata",
    "certificate verify failed",
    "eof occurred in violation",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "too many requests",
    "try again",
)
_NON_RETRYABLE_ERROR_MARKERS = (
    "video is private",
    "private video",
    "channel is private",
    "account is private",
    "login required",
    "sign in to confirm",
    "members-only",
    "premium-only",
    "age-restricted",
    "age restricted",
    "not available in your country",
    "not available in your region",
    "geo-restricted",
    "copyright",
    "has been removed",
    "video unavailable",
    "unsupported url",
)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class DownloadCancelled(RuntimeError):
    """Raised when the caller cancels metadata extraction or download."""


class _QuietLogger:
    """Keep downloader diagnostics inside the app's own error surface."""

    @staticmethod
    def debug(_message):
        pass

    @staticmethod
    def info(_message):
        pass

    @staticmethod
    def warning(_message):
        pass

    @staticmethod
    def error(_message):
        pass


@dataclass(frozen=True)
class VideoMetadata:
    url: str
    title: str
    platform: str
    duration_seconds: int
    thumbnail_url: str
    uploader: str

    def to_dict(self) -> dict:
        return asdict(self)


def _matching_platform(hostname: str) -> str:
    hostname = hostname.lower().rstrip(".")
    for domain, platform in SUPPORTED_VIDEO_HOSTS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return ""


def validate_video_url(value: str) -> tuple[str, str]:
    """Return a normalized supported URL and its platform label."""
    url = str(value or "").replace("\u200b", "").replace("\ufeff", "").strip()
    if not url:
        raise ValueError("Paste a video link first.")
    # Mobile share sheets often copy a sentence followed by the URL. Select
    # the first supported HTTP link instead of treating the entire sentence as
    # a hostname.
    embedded = re.findall(r"https?://[^\s<>\"']+", url, flags=re.IGNORECASE)
    if embedded:
        supported = []
        for candidate in embedded:
            candidate = candidate.rstrip(".,;:!?)]}")
            hostname = urlparse(candidate).hostname or ""
            if _matching_platform(hostname):
                supported.append(candidate)
        url = supported[0] if supported else embedded[0].rstrip(".,;:!?)]}")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = f"https://{url}"

    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS video link.")
    if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        raise ValueError("Enter a valid HTTP or HTTPS video link.")
    platform = _matching_platform(parsed.hostname)
    if platform == "Reddit":
        raise ValueError("Reddit downloads are temporarily unavailable.")
    if not platform:
        raise ValueError(
            "This link is not from a supported source. Use YouTube, TikTok, Douyin, Bilibili, "
            "Instagram, Facebook, X, or Streamable."
        )
    if platform == "Douyin":
        modal_ids = parse_qs(parsed.query).get("modal_id", [])
        if modal_ids:
            if len(modal_ids) != 1 or not re.fullmatch(r"[0-9]{10,25}", modal_ids[0]):
                raise ValueError("The Douyin link contains an invalid video ID.")
            url = f"https://www.douyin.com/video/{modal_ids[0]}"
        else:
            video = re.fullmatch(r"/(?:share/)?video/([0-9]{10,25})/?", parsed.path)
            if video:
                url = f"https://www.douyin.com/video/{video[1]}"
    return url, platform


def _youtube_dl_options(auth: dict | None = None, *, impersonate: bool = False) -> dict:
    ffmpeg_location = BIN_DIR if os.path.isdir(BIN_DIR) else None
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "windowsfilenames": True,
        "logger": _QuietLogger(),
        # TikTok's webpage markup is intermittently unavailable. Supplying an
        # empty app profile makes yt-dlp try its supported app API first, then
        # fall back to the webpage extractor when that API is unavailable.
        "extractor_args": {"tiktok": {"app_info": [""]}},
    }
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    # Some supported services reject Python's TLS fingerprint. yt-dlp uses
    # curl_cffi for a real browser request profile; enable it only on a retry
    # because forcing impersonation can make otherwise healthy extractors less
    # reliable.
    if impersonate and importlib.util.find_spec("curl_cffi") is not None:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        # The Python API expects a target object, unlike yt-dlp's CLI string.
        options["impersonate"] = ImpersonateTarget.from_str("chrome")
    auth = auth or {}
    cookie_file = str(auth.get("cookie_file") or "").strip()
    cookie_browser = str(auth.get("cookie_browser") or "").strip().lower()
    if cookie_file:
        options["cookiefile"] = cookie_file
    elif cookie_browser in {"chrome", "edge"}:
        options["cookiesfrombrowser"] = (cookie_browser,)
    return options


def _load_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("The video downloader is not installed in this app environment.") from exc
    return yt_dlp


def _extract_video_info(downloader, url: str, *, download: bool, cancel_event=None, auth=None):
    if _matching_platform(urlparse(url).hostname or "") == "Douyin":
        from haizflow.services.douyin_adapter import get_douyin_adapter
        from haizflow.services.douyin_video import HaizFlowDouyinIE
        adapter = get_douyin_adapter(auth)
        downloader.add_info_extractor(HaizFlowDouyinIE(adapter=adapter, cancel_event=cancel_event))
        return downloader.extract_info(url, download=download, ie_key=HaizFlowDouyinIE.ie_key())
    return downloader.extract_info(url, download=download)


def _ytdlp_auth_for_url(auth, url):
    # YoutubeDL may read cookies while constructing its request handlers, before
    # our extractor runs. Douyin alone owns its explicitly-scoped cookie jar.
    return None if _matching_platform(urlparse(url).hostname or "") == "Douyin" else auth


def _downloaded_audio_path(directory: Path, info: dict, downloader) -> Path:
    """Resolve the media file written by yt-dlp without trusting a remote filename."""
    directory = directory.resolve()
    candidates = [info.get("filepath"), info.get("_filename")]
    for item in info.get("requested_downloads") or []:
        if isinstance(item, dict):
            candidates.extend([item.get("filepath"), item.get("filename")])
    try:
        candidates.append(downloader.prepare_filename(info))
    except Exception:
        pass

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).resolve()
        try:
            inside_directory = path.is_relative_to(directory)
        except (OSError, ValueError):
            inside_directory = False
        if inside_directory and path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
            return path

    discovered = [
        path for path in directory.glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ]
    if not discovered:
        raise RuntimeError("The link did not produce a playable audio file.")
    return max(discovered, key=lambda path: path.stat().st_mtime)


def _ffmpeg_binary() -> str:
    bundled = Path(BIN_DIR) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if bundled.is_file():
        return str(bundled)
    resolved = shutil.which("ffmpeg")
    if resolved:
        return resolved
    raise RuntimeError("FFmpeg is not available to prepare the downloaded audio.")


def _normalize_downloaded_audio(
    source: Path,
    target: Path,
    cancel_event: threading.Event | None,
) -> None:
    """Create a predictable M4A independently of yt-dlp's FFprobe postprocessor."""
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Audio download cancelled.")
    if "audio" not in get_media_stream_types(str(source)):
        raise RuntimeError("The downloaded media does not contain an audio track.")
    temporary = target.with_name(f"{target.stem}.converting.m4a")
    temporary.unlink(missing_ok=True)
    command = [
        _ffmpeg_binary(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(temporary),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stderr = ""
    deadline = time.monotonic() + MEDIA_PROCESS_TIMEOUT_SECONDS
    try:
        while True:
            try:
                _stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel_event and cancel_event.is_set():
                    process.kill()
                    process.communicate()
                    raise DownloadCancelled("Audio download cancelled.")
                if time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    raise RuntimeError("Audio extraction took too long and was stopped.")
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Audio download cancelled.")
        if process.returncode != 0 or not temporary.is_file() or temporary.stat().st_size <= 0:
            detail = " ".join((stderr or "").split())[-500:]
            raise RuntimeError(
                "FFmpeg could not prepare the downloaded audio."
                + (f" {detail}" if detail else "")
            )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _friendly_error(exc: Exception) -> str:
    raw_message = _ANSI_ESCAPE.sub("", str(exc)).strip()
    if "Douyin did not provide playable video data." in raw_message:
        from haizflow.services.douyin_video import ACCESS_MESSAGE
        return ACCESS_MESSAGE
    message = raw_message.splitlines()[-1] if raw_message else exc.__class__.__name__
    message = re.sub(r"^ERROR:\s*", "", message, flags=re.IGNORECASE)
    if len(message) > 320:
        message = f"{message[:317]}..."
    return message


def _is_retryable_tiktok_error(exc: Exception) -> bool:
    message = _ANSI_ESCAPE.sub("", str(exc)).lower()
    return any(marker in message for marker in _TIKTOK_TRANSIENT_ERROR_MARKERS)


def _is_retryable_download_error(exc: Exception, platform: str) -> bool:
    """Return whether a fresh extractor session is likely to recover the media URL."""
    message = _ANSI_ESCAPE.sub("", str(exc)).lower()
    if any(marker in message for marker in _NON_RETRYABLE_ERROR_MARKERS):
        return False
    if any(marker in message for marker in _FORMAT_REFRESH_ERROR_MARKERS + _NETWORK_RETRY_ERROR_MARKERS):
        return True
    if platform == "TikTok" and _is_retryable_tiktok_error(exc):
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, OSError)) and not isinstance(
        exc, PermissionError
    )


def _log_media_retry(platform: str, exc: Exception, attempt: int, auth=None) -> None:
    if platform != "Douyin":
        return
    from haizflow.services.douyin_adapter import get_douyin_adapter
    from haizflow.services.douyin_classification import Outcome
    message = str(exc).lower()
    classification = (Outcome.MEDIA_EXPIRED if "403" in message or
                      any(marker in message for marker in _FORMAT_REFRESH_ERROR_MARKERS) else
                      Outcome.RATE_LIMIT if "429" in message else Outcome.NETWORK)
    get_douyin_adapter(auth).log_media_refresh(attempt,
        http_status=403 if "403" in message else 429 if "429" in message else 0,
        outcome=classification)


def _download_format_selector(platform: str, *, require_audio: bool = True) -> str:
    """Select a processable video: both picture and audio are mandatory."""
    # `best` does not guarantee a progressive stream. TikTok/Douyin sometimes
    # rank a high-quality video-only HEVC format above the playable stream,
    # which used to import successfully and then fail during audio extraction.
    if platform in {"TikTok", "Douyin"}:
        selector = (
            "best[vcodec!=none][acodec!=none]/"
            "bestvideo[vcodec!=none]+bestaudio[acodec!=none]"
        )
    else:
        selector = (
            "bestvideo[height<=1080][vcodec!=none]+bestaudio[acodec!=none]/"
            "best[height<=1080][vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]/"
            "bestvideo[vcodec!=none]+bestaudio[acodec!=none]"
        )
    if not require_audio:
        selector += "/bestvideo[height<=1080][vcodec!=none]/best[vcodec!=none]/bestvideo[vcodec!=none]"
    return selector


def _wait_for_retry(cancel_event: threading.Event | None, seconds: float) -> None:
    if cancel_event:
        if cancel_event.wait(seconds):
            raise DownloadCancelled("Link inspection cancelled.")
        return
    time.sleep(seconds)


def _inspect_video_info(yt_dlp, url: str, *, impersonate: bool = False, auth=None, cancel_event=None) -> dict:
    with yt_dlp.YoutubeDL(_youtube_dl_options(_ytdlp_auth_for_url(auth, url), impersonate=impersonate)) as downloader:
        return _extract_video_info(downloader, url, download=False, auth=auth, cancel_event=cancel_event)


def inspect_video_url(url: str, cancel_event: threading.Event | None = None, auth=None) -> VideoMetadata:
    normalized_url, platform = validate_video_url(url)
    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Link inspection cancelled.")

    yt_dlp = _load_yt_dlp()
    attempts = 3
    info = None
    for attempt in range(attempts):
        try:
            info = _inspect_video_info(yt_dlp, normalized_url, impersonate=attempt > 0, auth=auth,
                                       cancel_event=cancel_event)
            break
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Link inspection cancelled.") from exc
            if attempt + 1 < attempts and _is_retryable_download_error(exc, platform):
                _wait_for_retry(cancel_event, 0.6)
                continue
            raise RuntimeError(_friendly_error(exc)) from exc

    if cancel_event and cancel_event.is_set():
        raise DownloadCancelled("Link inspection cancelled.")
    if not isinstance(info, dict):
        raise RuntimeError("The video service returned no usable metadata.")
    if info.get("_type") in {"playlist", "multi_video"} or info.get("entries"):
        raise ValueError("Paste a link to one video, not a playlist or channel.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise ValueError("Live and upcoming streams are not supported.")

    resolved_platform = str(info.get("extractor_key") or info.get("extractor") or platform).strip()
    if "youtube" in resolved_platform.lower():
        resolved_platform = "YouTube"
    elif "tiktok" in resolved_platform.lower():
        resolved_platform = "TikTok"
    elif "douyin" in resolved_platform.lower():
        resolved_platform = "Douyin"
    elif "bilibili" in resolved_platform.lower():
        resolved_platform = "Bilibili"
    elif "twitter" in resolved_platform.lower():
        resolved_platform = "X"

    title = str(info.get("title") or "Untitled video").strip()
    return VideoMetadata(
        url=str(info.get("webpage_url") or normalized_url),
        title=title,
        platform=resolved_platform or platform,
        duration_seconds=max(0, int(info.get("duration") or 0)),
        thumbnail_url=str(info.get("thumbnail") or ""),
        uploader=str(info.get("uploader") or info.get("channel") or "").strip(),
    )


def download_audio(
    url: str,
    destination: str | Path,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    auth: dict | None = None,
) -> str:
    """Download one link and normalize its audio with the bundled FFmpeg."""
    normalized_url, platform = validate_video_url(url)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    yt_dlp = _load_yt_dlp()

    def hook(event: dict) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Audio download cancelled.")
        if event.get("status") != "downloading" or not progress_callback:
            return
        downloaded = int(event.get("downloaded_bytes") or 0)
        total = int(event.get("total_bytes") or event.get("total_bytes_estimate") or 0)
        progress_callback(min(95, round(downloaded * 95 / total)) if total else 0, "Downloading audio")

    attempts = 3
    for attempt in range(attempts):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Audio download cancelled.")
        for stale in target.parent.glob(f"{target.stem}.source.*"):
            stale.unlink(missing_ok=True)
        options = _youtube_dl_options(_ytdlp_auth_for_url(auth, normalized_url), impersonate=attempt > 0)
        options.update(
            {
                "outtmpl": str(target.with_name(f"{target.stem}.source.%(ext)s")),
                "format": "bestaudio/best",
                "progress_hooks": [hook],
                "nopart": True,
                "overwrites": True,
            }
        )
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = _extract_video_info(downloader, normalized_url, download=True, auth=auth,
                                           cancel_event=cancel_event)
                source = _downloaded_audio_path(target.parent, info, downloader)
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Audio download cancelled.")
            if progress_callback:
                progress_callback(96, "Preparing downloaded audio")
            _normalize_downloaded_audio(source, target, cancel_event)
            if source != target:
                source.unlink(missing_ok=True)
            if progress_callback:
                progress_callback(100, "Download complete")
            return str(target)
        except DownloadCancelled:
            raise
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Audio download cancelled.") from exc
            if attempt + 1 < attempts and _is_retryable_download_error(exc, platform):
                _log_media_retry(platform, exc, attempt + 1, auth)
                _wait_for_retry(cancel_event, 0.8 * (attempt + 1))
                continue
            raise RuntimeError(_friendly_error(exc)) from exc
        finally:
            # yt-dlp writes its source stream beside the requested output.
            # Never leave those implementation files in the user's download
            # folder after cancellation, conversion failure, or a final retry.
            for stale in target.parent.glob(f"{target.stem}.source.*"):
                stale.unlink(missing_ok=True)
    raise RuntimeError("Audio download did not produce a result.")  # pragma: no cover


def create_download_workspace(project_root: str) -> str:
    downloads_directory = os.path.join(os.path.abspath(project_root), ".downloads")
    os.makedirs(downloads_directory, exist_ok=True)
    return tempfile.mkdtemp(prefix="video-", dir=downloads_directory)


def cleanup_download_workspace(workspace: str) -> None:
    if not workspace:
        return
    workspace_path = Path(workspace).resolve()
    parent = workspace_path.parent
    if parent.name != ".downloads":
        return
    shutil.rmtree(workspace_path, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass


def _downloaded_video_path(workspace: str, info: dict, downloader) -> str:
    workspace = os.path.abspath(workspace)
    candidates = [info.get("filepath"), info.get("_filename")]
    for item in info.get("requested_downloads") or []:
        if isinstance(item, dict):
            candidates.extend([item.get("filepath"), item.get("filename")])
    try:
        candidates.append(downloader.prepare_filename(info))
    except Exception:
        pass

    expanded = []
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.abspath(str(candidate))
        expanded.append(candidate)
        stem, _extension = os.path.splitext(candidate)
        expanded.extend(f"{stem}{extension}" for extension in SUPPORTED_DOWNLOAD_EXTENSIONS)
    for candidate in expanded:
        try:
            inside_workspace = os.path.commonpath([workspace, candidate]) == workspace
        except ValueError:
            inside_workspace = False
        if (
            inside_workspace
            and os.path.isfile(candidate)
            and os.path.splitext(candidate)[1].lower() in SUPPORTED_DOWNLOAD_EXTENSIONS
        ):
            return candidate

    discovered = [
        path
        for path in Path(workspace).glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_DOWNLOAD_EXTENSIONS
    ]
    if not discovered:
        raise RuntimeError("The download finished but no supported video file was produced.")
    return str(max(discovered, key=lambda path: path.stat().st_mtime))


def _validate_processable_video(video_path: str, *, require_audio: bool = True) -> None:
    """Reject downloads that cannot enter the dubbing pipeline."""
    stream_types = get_media_stream_types(video_path)
    if "video" not in stream_types:
        raise RuntimeError("The downloaded media does not contain a video track.")
    if require_audio and "audio" not in stream_types:
        raise RuntimeError(
            "The downloaded video does not contain an audio track. "
            "Try the link again or choose another source video."
        )


def download_video(
    metadata: VideoMetadata,
    workspace: str,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    auth: dict | None = None,
    *,
    require_audio: bool = True,
) -> str:
    """Download one video and return its final MP4/MOV/MKV path."""
    os.makedirs(workspace, exist_ok=True)
    yt_dlp = _load_yt_dlp()
    last_update = {"progress": -1, "detail": "", "time": 0.0}

    def report(progress: int, detail: str) -> None:
        progress = max(0, min(100, int(progress)))
        now = time.monotonic()
        if (
            progress == last_update["progress"]
            and detail == last_update["detail"]
            and now - last_update["time"] < 0.25
        ):
            return
        last_update.update(progress=progress, detail=detail, time=now)
        if progress_callback:
            progress_callback(progress, detail)

    def progress_hook(event: dict) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelled("Video download cancelled.")
        status = event.get("status")
        if status == "downloading":
            downloaded = int(event.get("downloaded_bytes") or 0)
            total = int(event.get("total_bytes") or event.get("total_bytes_estimate") or 0)
            progress = round(downloaded * 100 / total) if total else 0
            speed = float(event.get("speed") or 0)
            detail = f"{_format_bytes(downloaded)}"
            if total:
                detail += f" / {_format_bytes(total)}"
            if speed:
                detail += f"  |  {_format_bytes(speed)}/s"
            report(min(progress, 99), detail)
        elif status == "finished":
            report(99, "Finalizing video")

    report(0, "Starting download")
    attempts = 3
    for attempt in range(attempts):
        options = _youtube_dl_options(_ytdlp_auth_for_url(auth, metadata.url), impersonate=attempt > 0)
        options.update(
            {
                "outtmpl": os.path.join(workspace, "%(title).120B [%(id)s].%(ext)s"),
                "format": _download_format_selector(metadata.platform, require_audio=require_audio),
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
                "progress_hooks": [progress_hook],
                "concurrent_fragment_downloads": 4,
                "nopart": True,
                "overwrites": True,
            }
        )
        try:
            # A new YoutubeDL instance on every attempt forces a fresh media
            # manifest.  TikTok's signed URLs can expire between inspection
            # and download, especially in a multi-video channel import.
            with yt_dlp.YoutubeDL(options) as downloader:
                info = _extract_video_info(downloader, metadata.url, download=True, auth=auth,
                                           cancel_event=cancel_event)
                if cancel_event and cancel_event.is_set():
                    raise DownloadCancelled("Video download cancelled.")
                video_path = _downloaded_video_path(workspace, info, downloader)
                _validate_processable_video(video_path, require_audio=require_audio)
            break
        except DownloadCancelled:
            raise
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Video download cancelled.") from exc
            if attempt + 1 < attempts and _is_retryable_download_error(exc, metadata.platform):
                _log_media_retry(metadata.platform, exc, attempt + 1, auth)
                report(0, "Refreshing video stream and retrying")
                _wait_for_retry(cancel_event, 0.8 * (attempt + 1))
                continue
            raise RuntimeError(_friendly_error(exc)) from exc
    else:  # pragma: no cover - all non-returning paths raise above
        raise RuntimeError("Video download did not produce a result.")

    report(100, "Download complete")
    return video_path


def _format_bytes(value: float) -> str:
    size = max(0.0, float(value))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
