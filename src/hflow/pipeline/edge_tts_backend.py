"""Bounded online synthesis; never publish incomplete or empty Edge audio."""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import threading
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path

from hflow.core.edge_voices import edge_voice
from hflow.pipeline.process_registry import check_cancellation
from hflow.services.video_store import log_to_video
from hflow.utils.ffmpeg import get_video_duration

# Transport/token upgrades must not discard already verified narration.
EDGE_CACHE_VERSION = "edge-7.2.8-verified-v1"
EDGE_CLIENT_MIN_VERSION = (7, 3, 1)
ATTEMPT_TIMEOUT = 45.0
RETRY_DELAYS = (1.0, 3.0)
MAX_CONCURRENCY = 2
# Cap requests across simultaneous projects/event loops, not just one batch.
_SERVICE_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENCY)


class EdgeAudioError(RuntimeError):
    """The service completed a request without usable audio."""


class _RequestPolicy:
    def __init__(self):
        self.limit = MAX_CONCURRENCY
        self.active = 0
        self.resume_at = 0.0

    async def acquire(self, registry_id: str):
        while True:
            check_cancellation(registry_id)
            if (self.active < self.limit and asyncio.get_running_loop().time() >= self.resume_at
                    and _SERVICE_SLOTS.acquire(blocking=False)):
                self.active += 1
                return
            await asyncio.sleep(.05)

    def release(self):
        self.active -= 1
        _SERVICE_SLOTS.release()

    def backoff(self, delay: float):
        # A retryable failure reduces the rest of this batch to serial requests.
        # An already in-flight peer may finish; do not launch more during cooldown.
        self.limit = 1
        self.resume_at = max(self.resume_at, asyncio.get_running_loop().time() + delay)


def _chunks(text: str, max_bytes: int = 1800) -> list[str]:
    # Avoid a multi-request Communicate whose later chunk can fail after it
    # has already streamed a valid prefix. Bound escaped UTF-8, not characters.
    from xml.sax.saxutils import escape

    result, pending, size = [], [], 0
    for char in text:
        width = len(escape(char).encode("utf-8"))
        if pending and size + width > max_bytes:
            value = "".join(pending)
            split = max(value.rfind(" "), value.rfind("。"), value.rfind(".")) + 1
            if split < len(value) // 2:
                split = len(value)
            result.append(value[:split])
            pending = list(value[split:])
            size = len(escape("".join(pending)).encode("utf-8"))
        pending.append(char)
        size += width
    if pending:
        result.append("".join(pending))
    return [item for item in result if item.strip()]


def valid_audio(path: str) -> bool:
    from hflow.pipeline.tts import _is_valid_mp3

    return _is_valid_mp3(path) and get_video_duration(path, timeout_seconds=5) > 0


async def _verified(path: Path, registry_id: str) -> bool:
    check_cancellation(registry_id)
    # ffprobe must not block streaming/cancellation for the other sentence.
    # Drain the bounded probe on cancellation before deleting its staging file
    # (Windows would otherwise keep that file locked).
    task = asyncio.create_task(asyncio.to_thread(valid_audio, str(path)))
    try:
        result = await asyncio.shield(task)
    finally:
        if not task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    check_cancellation(registry_id)
    return result


async def _watch(awaitable, registry_id: str, timeout: float):
    task = asyncio.ensure_future(awaitable)
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while not task.done():
            check_cancellation(registry_id)
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Edge TTS request timed out")
            await asyncio.wait({task}, timeout=.1)
        check_cancellation(registry_id)
        return await task
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def _download(text: str, voice: str, path: Path):
    import edge_tts

    version = str(getattr(edge_tts, "__version__", "0.0.0"))
    parts = tuple(int(part) for part in version.split(".")[:3] if part.isdigit())
    if parts < EDGE_CLIENT_MIN_VERSION:
        raise ValueError("Edge TTS cần bản 7.3.1 trở lên. Cập nhật dependency và khởi động lại ứng dụng.")

    # A Communicate is single-use. Never reuse an exhausted stream on retry.
    communicate = edge_tts.Communicate(text, voice, connect_timeout=10, receive_timeout=20)
    received = 0
    with path.open("wb") as stream:
        async for packet in communicate.stream():
            if packet.get("type") == "audio":
                data = packet.get("data") or b""
                stream.write(data)
                received += len(data)
    if not received:
        raise EdgeAudioError("Empty audio response")


def _retryable(exc: Exception) -> bool:
    import aiohttp
    from edge_tts.exceptions import EdgeTTSException

    if isinstance(exc, (aiohttp.ClientConnectorCertificateError, aiohttp.ClientConnectorSSLError)):
        return False  # Never weaken TLS or retry an invalid trust configuration.
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status in {403, 408, 429} or exc.status >= 500
    return isinstance(exc, (TimeoutError, ConnectionError, EdgeAudioError, EdgeTTSException,
                            aiohttp.ClientConnectionError, aiohttp.ClientPayloadError))


async def _synthesize(text: str, voice: str, output: Path, video_id: str, registry_id: str,
                      policy: _RequestPolicy | None = None):
    policy = policy or _RequestPolicy()
    chunks = _chunks(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Same-volume staging, atomic publish; old good audio survives failures.
    with tempfile.TemporaryDirectory(prefix=".edge-", dir=output.parent) as temporary:
        root = Path(temporary)
        combined = root / "complete.mp3"
        with combined.open("wb") as destination:
            for chunk_index, chunk in enumerate(chunks, 1):
                part = root / "part.mp3"
                for attempt in range(1, len(RETRY_DELAYS) + 2):
                    check_cancellation(registry_id)
                    try:
                        await policy.acquire(registry_id)
                        try:
                            await _watch(_download(chunk, voice, part), registry_id, ATTEMPT_TIMEOUT)
                        finally:
                            policy.release()
                        check_cancellation(registry_id)
                        if not await _verified(part, registry_id):
                            raise EdgeAudioError("Unusable audio response")
                        break
                    except Exception as exc:
                        check_cancellation(registry_id)
                        retry = _retryable(exc) and attempt <= len(RETRY_DELAYS)
                        if retry:
                            policy.backoff(RETRY_DELAYS[attempt - 1])
                        # No text, signed URL, headers or raw exception containing tokens.
                        with contextlib.suppress(OSError, TimeoutError):
                            log_to_video(video_id, f"[EDGE_TTS] chunk={chunk_index} attempt={attempt} "
                                         f"error={type(exc).__name__} retry={retry} concurrency={policy.limit}")
                        if not retry:
                            if _retryable(exc):
                                raise EdgeAudioError(
                                    "Edge TTS chưa trả về audio hợp lệ sau 3 lần thử. "
                                    "Các câu đã tạo được giữ lại; thử lại sau hoặc chọn OmniVoice."
                                ) from None
                            import aiohttp

                            if isinstance(exc, (OSError, ValueError, TypeError)) and not isinstance(exc, aiohttp.ClientError):
                                raise  # Local disk/input errors are not service outages.
                            raise RuntimeError(
                                "Không kết nối được Edge TTS. Kiểm tra mạng, chứng chỉ và giọng đã chọn."
                            ) from None
                        await _watch(asyncio.sleep(RETRY_DELAYS[attempt - 1]), registry_id, 5)
                # Each request was independently verified, not only the MP3 prefix.
                if len(chunks) > 1:
                    with part.open("rb") as source:
                        while data := source.read(64 * 1024):
                            destination.write(data)
        check_cancellation(registry_id)
        # A one-chunk sentence is the exact verified file: no copy or duplicate
        # ffprobe. Multi-chunk narration still verifies the assembled result.
        publish = part if len(chunks) == 1 else combined
        if len(chunks) != 1 and not await _verified(combined, registry_id):
            raise EdgeAudioError("Edge TTS trả về audio không hợp lệ; giọng cũ được giữ nguyên.")
        check_cancellation(registry_id)
        os.replace(publish, output)


def _readable_text(text: str) -> str:
    text = " ".join("".join(char for char in text if not unicodedata.category(char).startswith("C")
                            or char in "\n\r\t").split())
    if not any(unicodedata.category(char)[0] in {"L", "N"} for char in text):
        raise ValueError("Phụ đề không có nội dung đọc được để tạo giọng.")
    return text


async def _batch(requests: Iterable[tuple[str, str]], voice: str, video_id: str, registry_id: str,
                 on_completed: Callable[[int], None] | None):
    pending = iter(requests)
    policy = _RequestPolicy()
    completed = 0

    async def worker():
        nonlocal completed
        # Exactly two worker tasks, even for a many-hour subtitle document.
        for text, output_path in pending:
            check_cancellation(registry_id)
            text = _readable_text(text)
            output = Path(output_path)
            if not await _verified(output, registry_id):
                await _synthesize(text, voice, output, video_id, registry_id, policy)
            check_cancellation(registry_id)
            completed += 1
            if on_completed:
                on_completed(completed)

    workers = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENCY)]
    try:
        await asyncio.gather(*workers)
    finally:
        # A terminal error or user pause cancels peers and waits for network/
        # probe cleanup. Completed atomic files remain reusable on resume.
        for task in workers:
            if not task.done():
                task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


def synthesize_many_to_mp3(requests: Iterable[tuple[str, str]], voice: str, video_id: str, *,
                           language_id: str = "vi", process_registry_id: str | None = None,
                           on_completed: Callable[[int], None] | None = None):
    voice = edge_voice(voice, language_id)
    registry_id = process_registry_id or video_id
    check_cancellation(registry_id)
    asyncio.run(_batch(requests, voice, video_id, registry_id, on_completed))


def synthesize_to_mp3(text: str, voice: str, output_path: str, video_id: str, *,
                      language_id: str = "vi", process_registry_id: str | None = None):
    voice = edge_voice(voice, language_id)
    text = _readable_text(text)
    registry_id = process_registry_id or video_id
    check_cancellation(registry_id)
    asyncio.run(_synthesize(text, voice, Path(output_path), video_id, registry_id))
