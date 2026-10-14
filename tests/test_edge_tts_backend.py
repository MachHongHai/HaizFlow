import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import aiohttp
import pytest
from edge_tts.exceptions import NoAudioReceived

from hflow.pipeline import edge_tts_backend as edge, tts

VOICE = "vi-VN-HoaiMyNeural"
AUDIO = b"\xff\xf3\x64" + b"\x01" * 1000


@pytest.fixture
def backend():
    with (patch.object(edge, "log_to_video") as log,
          patch.object(edge, "check_cancellation"),
          patch.object(edge, "RETRY_DELAYS", (.001, .001)),
          patch.object(edge, "valid_audio", side_effect=lambda path: Path(path).is_file()
                       and Path(path).read_bytes().startswith(AUDIO))):
        yield log


def run(path):
    edge.synthesize_to_mp3("Xin chào.", VOICE, str(path), "fixture")


def fake_communicate(results):
    class Communicate:
        instances = []

        def __init__(self, text, voice, **kwargs):
            self.instances.append(self)
            self.text, self.voice, self.options = text, voice, kwargs

        async def stream(self):
            result = results[len(self.instances) - 1]
            yield {"type": "SentenceBoundary", "text": "metadata"}
            if isinstance(result, Exception):
                raise result
            yield {"type": "audio", "data": result}

    return Communicate


def test_no_audio_retry_uses_fresh_communicate_and_atomic_publish(tmp_path, backend):
    communicate = fake_communicate([NoAudioReceived("empty"), NoAudioReceived("empty"), AUDIO])
    output = tmp_path / "voice.mp3"
    with patch("edge_tts.Communicate", communicate):
        run(output)
    assert output.read_bytes() == AUDIO
    assert len(communicate.instances) == 3
    assert len({id(item) for item in communicate.instances}) == 3
    assert communicate.instances[0].options == {"connect_timeout": 10, "receive_timeout": 20}
    assert list(tmp_path.iterdir()) == [output]


def test_old_client_is_blocked_before_network_without_repeating_empty_audio(tmp_path, backend):
    with patch("edge_tts.__version__", "7.2.8"), patch("edge_tts.Communicate") as communicate:
        with pytest.raises(ValueError, match="7.3.1"):
            run(tmp_path / "voice.mp3")
    communicate.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_transport_upgrade_keeps_verified_audio_cache_and_pins_exact_upstream_source():
    import tomllib

    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    reference = next(value for value in project["project"]["dependencies"] if value.startswith("edge-tts"))
    assert "360fa8e1de354e1dda74c09bd695887d6a44df74" in reference
    assert "sha256=470d399a288b9ff9800988538ae31c99f06e589ec0ed67cb01141b29a005ab47" in reference
    assert edge.EDGE_CACHE_VERSION == "edge-7.2.8-verified-v1"


@pytest.mark.parametrize("failure", [NoAudioReceived("empty"), TimeoutError("slow")])
def test_exhausted_retries_preserve_old_audio_and_cleanup_staging(tmp_path, backend, failure):
    output = tmp_path / "old.mp3"
    output.write_bytes(b"previous good voice")
    communicate = fake_communicate([failure] * 3)
    with patch("edge_tts.Communicate", communicate), pytest.raises(edge.EdgeAudioError, match="3 lần"):
        run(output)
    assert len(communicate.instances) == 3
    assert output.read_bytes() == b"previous good voice"
    assert list(tmp_path.iterdir()) == [output]


def test_empty_packets_are_not_published(tmp_path, backend):
    communicate = fake_communicate([b""] * 3)
    output = tmp_path / "voice.mp3"
    with patch("edge_tts.Communicate", communicate), pytest.raises(edge.EdgeAudioError):
        run(output)
    assert not output.exists()
    assert not list(tmp_path.iterdir())


def test_partial_stream_is_discarded_before_retry(tmp_path, backend):
    calls = []

    async def download(_text, _voice, path):
        calls.append(path)
        if len(calls) == 1:
            path.write_bytes(b"partial")
            raise NoAudioReceived("later chunk failed")
        path.write_bytes(AUDIO)

    with patch.object(edge, "_download", side_effect=download):
        run(tmp_path / "voice.mp3")
    assert len(calls) == 2
    assert (tmp_path / "voice.mp3").read_bytes() == AUDIO


def test_disk_failure_is_not_retried_or_misreported_as_network(tmp_path, backend):
    with patch.object(edge, "_download", side_effect=PermissionError("disk locked")) as download:
        with pytest.raises(PermissionError, match="disk locked"):
            run(tmp_path / "voice.mp3")
    assert download.call_count == 1


def test_busy_diagnostic_log_does_not_break_audio_recovery(tmp_path, backend):
    communicate = fake_communicate([NoAudioReceived("empty"), AUDIO])
    with patch("edge_tts.Communicate", communicate), patch.object(edge, "log_to_video", side_effect=TimeoutError):
        run(tmp_path / "voice.mp3")
    assert (tmp_path / "voice.mp3").read_bytes() == AUDIO


@pytest.mark.parametrize("status,retry", [(403, True), (408, True), (429, True), (503, True),
                                          (400, False), (404, False)])
def test_http_classification(status, retry):
    error = aiohttp.ClientResponseError(SimpleNamespace(real_url=""), (), status=status)
    assert edge._retryable(error) is retry


def test_invalid_text_and_voice_do_not_call_service(tmp_path, backend):
    with patch("edge_tts.Communicate") as communicate:
        for text, voice in [("...\u0000", VOICE), ("Hello", "not-a-voice")]:
            with pytest.raises(ValueError):
                edge.synthesize_to_mp3(text, voice, str(tmp_path / "out.mp3"), "fixture")
    communicate.assert_not_called()


def test_certificate_failure_is_terminal_and_not_logged_with_sensitive_details(tmp_path, backend):
    import ssl

    error = aiohttp.ClientConnectorCertificateError(
        SimpleNamespace(host="private.example", port=443, ssl=True),
        ssl.SSLCertVerificationError(1, "sensitive-details"))
    communicate = fake_communicate([error])
    with patch("edge_tts.Communicate", communicate), pytest.raises(RuntimeError, match="chứng chỉ"):
        run(tmp_path / "voice.mp3")
    assert len(communicate.instances) == 1
    assert "sensitive-details" not in str(backend.call_args_list)
    assert "private.example" not in str(backend.call_args_list)


def test_invalid_audio_retries_without_publishing(tmp_path, backend):
    communicate = fake_communicate([b"ID3" + b"broken" * 300] * 3)
    with patch("edge_tts.Communicate", communicate), pytest.raises(edge.EdgeAudioError):
        run(tmp_path / "voice.mp3")
    assert not list(tmp_path.iterdir())


def test_escaped_utf8_chunks_preserve_all_text_and_have_bounded_size():
    from xml.sax.saxutils import escape

    text = "中文 < & tiếng Việt. " * 600
    chunks = edge._chunks(text)
    assert "".join(chunks) == text
    assert len(chunks) > 1
    assert all(len(escape(item).encode("utf-8")) <= 1800 for item in chunks)


def test_later_chunk_failure_never_publishes_successful_prefix(tmp_path, backend):
    output = tmp_path / "voice.mp3"
    output.write_bytes(b"old")
    communicate = fake_communicate([AUDIO] + [NoAudioReceived("empty")] * 3)
    with patch.object(edge, "_chunks", return_value=["first", "second"]), \
            patch("edge_tts.Communicate", communicate), pytest.raises(edge.EdgeAudioError):
        run(output)
    assert output.read_bytes() == b"old"


def test_timeout_closes_hanging_request_and_does_not_publish(tmp_path, backend):
    closed = []

    async def hanging(*_args):
        try:
            await asyncio.sleep(100)
        finally:
            closed.append(True)

    with patch.object(edge, "_download", side_effect=hanging), patch.object(edge, "ATTEMPT_TIMEOUT", .01):
        with pytest.raises(edge.EdgeAudioError):
            run(tmp_path / "voice.mp3")
    assert len(closed) == 3
    assert not list(tmp_path.iterdir())


def test_cancellation_interrupts_network_without_retry(tmp_path, backend):
    import time
    started = time.monotonic()
    calls = []

    async def hanging(*_args):
        calls.append(True)
        await asyncio.sleep(100)

    def cancellation(_video_id):
        if calls:
            raise RuntimeError("Video cancelled by user.")

    with patch.object(edge, "_download", side_effect=hanging), \
            patch.object(edge, "check_cancellation", side_effect=cancellation), \
            pytest.raises(RuntimeError, match="cancelled"):
        run(tmp_path / "voice.mp3")
    assert len(calls) == 1
    assert time.monotonic() - started < 1
    assert not list(tmp_path.iterdir())


def test_cancellation_interrupts_backoff(tmp_path, backend):
    checks = []

    def cancellation(_video_id):
        checks.append(True)
        if len(checks) > 4:
            raise RuntimeError("Video cancelled by user.")

    communicate = fake_communicate([NoAudioReceived("empty")] * 3)
    with patch("edge_tts.Communicate", communicate), patch.object(edge, "RETRY_DELAYS", (60, 60)), \
            patch.object(edge, "check_cancellation", side_effect=cancellation), \
            pytest.raises(RuntimeError, match="cancelled"):
        run(tmp_path / "voice.mp3")
    assert len(communicate.instances) == 1


def test_only_selected_missing_sentences_are_synthesized(tmp_path, backend):
    segments = tmp_path / "segments.json"
    segments.write_text(json.dumps([{"text": "one"}, {"text": "two"}, {"text": "three"}]))
    parts = tmp_path / "parts"
    parts.mkdir()
    (parts / "voice_0001.mp3").write_bytes(AUDIO)
    progress = Mock()

    async def generate(text, voice, path):
        assert text == "three."
        assert voice == VOICE
        Path(path).write_bytes(AUDIO)

    with patch.object(tts, "log_to_video"), patch.object(edge, "_download", side_effect=generate) as synthesis, \
            patch.object(edge, "check_cancellation") as cancellation:
        tts.generate_voice_parts(str(segments), str(parts), VOICE, "fixture", provider="edge",
                                 segment_indices=[1, 3], process_registry_id="job-id", progress_callback=progress)
    assert synthesis.call_count == 1
    assert all(call.args == ("job-id",) for call in cancellation.call_args_list)
    assert not (parts / "voice_0002.mp3").exists()
    progress.assert_called_with(2, 2)


def test_single_sentence_is_probed_once_and_publishes_exact_verified_bytes(tmp_path, backend):
    communicate = fake_communicate([AUDIO])
    with patch("edge_tts.Communicate", communicate), patch.object(edge, "valid_audio", return_value=True) as probe:
        run(tmp_path / "voice.mp3")
    assert probe.call_count == 1
    assert (tmp_path / "voice.mp3").read_bytes() == AUDIO


def test_multichunk_still_verifies_every_chunk_and_combined_audio(tmp_path, backend):
    communicate = fake_communicate([AUDIO, AUDIO])
    with patch.object(edge, "_chunks", return_value=["first", "second"]), \
            patch("edge_tts.Communicate", communicate), patch.object(edge, "valid_audio", return_value=True) as probe:
        run(tmp_path / "voice.mp3")
    assert probe.call_count == 3
    assert (tmp_path / "voice.mp3").read_bytes() == AUDIO * 2


def test_batch_is_bounded_and_progress_tracks_verified_completions_not_indices(tmp_path, backend):
    active, maximum = 0, 0
    finished = []
    progress = []

    async def download(text, _voice, path):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(.06 if text == "one" else .01)
            path.write_bytes(AUDIO + text.encode())
        finally:
            active -= 1

    def report(completed):
        files = list(tmp_path.glob("*.mp3"))
        assert len(files) == completed
        assert all(path.read_bytes().startswith(AUDIO) for path in files)
        finished.append({path.stem for path in files})
        progress.append(completed)

    with patch.object(edge, "_download", side_effect=download):
        edge.synthesize_many_to_mp3(((text, str(tmp_path / f"{text}.mp3"))
                                    for text in ("one", "two", "three", "four")),
                                   VOICE, "fixture", on_completed=report)
    assert maximum == 2
    assert progress == [1, 2, 3, 4]
    assert finished[0] == {"two"}
    for text in ("one", "two", "three", "four"):
        assert (tmp_path / f"{text}.mp3").read_bytes() == AUDIO + text.encode()


@pytest.mark.parametrize("failure", [NoAudioReceived("empty"),
    aiohttp.ClientResponseError(SimpleNamespace(real_url=""), (), status=429)])
def test_batch_retry_switches_to_serial_with_shared_cooldown(tmp_path, backend, failure):
    starts = []
    active = 0
    failed = False
    failure_at = None

    async def download(text, _voice, path):
        nonlocal active, failed, failure_at
        active += 1
        starts.append((text, active, asyncio.get_running_loop().time(), failed))
        try:
            if text == "one" and not failed:
                failed = True
                failure_at = asyncio.get_running_loop().time()
                raise failure
            await asyncio.sleep(.01)
            path.write_bytes(AUDIO)
        finally:
            active -= 1

    with patch.object(edge, "_download", side_effect=download), patch.object(edge, "RETRY_DELAYS", (.07, .07)):
        edge.synthesize_many_to_mp3(((text, str(tmp_path / f"{text}.mp3"))
                                    for text in ("one", "two", "three", "four")), VOICE, "fixture")
    recovered = [item for item in starts if item[2] >= failure_at + .06]
    assert recovered and all(item[1] == 1 for item in recovered)
    assert len(list(tmp_path.glob("*.mp3"))) == 4
    assert "concurrency=1" in str(backend.call_args_list)


def test_terminal_batch_failure_cleans_peers_and_resume_preserves_completed_parts(tmp_path, backend):
    first_done = asyncio.Event()
    closed = []

    async def download(text, _voice, path):
        if text == "one":
            path.write_bytes(AUDIO)
            return
        if text == "two":
            await first_done.wait()
            raise PermissionError("locked")
        try:
            path.write_bytes(b"partial")
            await asyncio.sleep(100)
        finally:
            closed.append(text)

    def progress(_count):
        first_done.set()

    requests = [(text, str(tmp_path / f"{text}.mp3")) for text in ("one", "two", "three", "four")]
    with patch.object(edge, "_download", side_effect=download), pytest.raises(PermissionError):
        edge.synthesize_many_to_mp3(requests, VOICE, "fixture", on_completed=progress)
    assert (tmp_path / "one.mp3").read_bytes() == AUDIO
    assert not list(tmp_path.glob(".edge-*"))
    assert not (tmp_path / "two.mp3").exists()
    assert not (tmp_path / "three.mp3").exists()

    async def recovered(_text, _voice, path):
        path.write_bytes(AUDIO)

    with patch.object(edge, "_download", side_effect=recovered) as calls:
        edge.synthesize_many_to_mp3(requests, VOICE, "fixture")
    assert sorted(call.args[0] for call in calls.call_args_list) == ["four", "three", "two"]
    assert len(list(tmp_path.glob("*.mp3"))) == 4


def test_batch_cancellation_closes_all_network_streams_and_releases_slots(tmp_path, backend):
    import time

    started, closed = [], []

    async def download(text, _voice, path):
        started.append(text)
        try:
            path.write_bytes(b"partial")
            await asyncio.sleep(100)
        finally:
            closed.append(text)

    def cancellation(_id):
        if len(started) >= 2:
            raise RuntimeError("Video cancelled by user.")

    start = time.monotonic()
    with patch.object(edge, "_download", side_effect=download), \
            patch.object(edge, "check_cancellation", side_effect=cancellation), pytest.raises(RuntimeError, match="cancelled"):
        edge.synthesize_many_to_mp3([(str(i), str(tmp_path / f"{i}.mp3")) for i in range(1000)], VOICE, "fixture")
    assert time.monotonic() - start < 1
    assert len(started) == 2 and sorted(closed) == sorted(started)
    assert not list(tmp_path.iterdir())
    assert edge._SERVICE_SLOTS.acquire(blocking=False)
    assert edge._SERVICE_SLOTS.acquire(blocking=False)
    assert not edge._SERVICE_SLOTS.acquire(blocking=False)
    edge._SERVICE_SLOTS.release()
    edge._SERVICE_SLOTS.release()


def test_cancelled_probe_finishes_before_staging_cleanup(tmp_path, backend):
    import threading
    import time

    probing = threading.Event()
    finished = threading.Event()

    def probe(path):
        probing.set()
        time.sleep(.04)
        assert Path(path).exists()
        finished.set()
        return True

    async def test():
        path = tmp_path / "part.mp3"
        path.write_bytes(AUDIO)
        task = asyncio.create_task(edge._verified(path, "fixture"))
        while not probing.is_set():
            await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    with patch.object(edge, "valid_audio", side_effect=probe):
        asyncio.run(test())


def test_multiple_projects_share_two_network_slots(tmp_path, backend):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    active, maximum = 0, 0

    async def download(_text, _voice, path):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            await asyncio.sleep(.02)
            path.write_bytes(AUDIO)
        finally:
            with lock:
                active -= 1

    def project(number):
        edge.synthesize_many_to_mp3([(str(i), str(tmp_path / str(number) / f"{i}.mp3")) for i in range(5)],
                                   VOICE, f"project-{number}")

    with patch.object(edge, "_download", side_effect=download), ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(project, [1, 2]))
    assert maximum == 2 and active == 0
    assert len(list(tmp_path.rglob("*.mp3"))) == 10


def test_audio_validator_rejects_header_only_or_unprobeable_audio(tmp_path):
    output = tmp_path / "out.mp3"
    output.write_bytes(AUDIO)
    with patch.object(edge, "get_video_duration", return_value=0):
        assert not edge.valid_audio(str(output))
    with patch.object(edge, "get_video_duration", return_value=1):
        assert edge.valid_audio(str(output))


def test_edge_config_catalog_migration_and_resources_are_consistent():
    from hflow.desktop.presenters import voice_options_for_language
    from hflow.desktop.qml_controller import HFlowController
    from hflow.schemas.video import VideoConfig
    from hflow.services.resource_packs import ResourcePackManager
    from hflow.services.video_store import _migrate_video_metadata

    assert VideoConfig(tts_provider="edge", tts_voice=VOICE).tts_provider == "edge"
    value, _ = _migrate_video_metadata({"schema_version": 19, "tts_provider": "edge", "tts_voice": VOICE,
        "files": {"manual_voice_overrides": {"a": {"provider": "edge", "voice": VOICE}}}})
    assert value["tts_provider"] == "edge"
    assert value["tts_voice"] == VOICE
    assert value["files"]["manual_voice_overrides"]["a"]["voice"] == VOICE
    assert ResourcePackManager().required_packs("voice", {"provider": "edge", "device": "gpu"}) == []
    host = SimpleNamespace(_project_gpu_available=lambda: False)
    options = HFlowController._tts_provider_options_for_language(host, "vi")
    assert next(item for item in options if item["provider"] == "edge")["available"]
    for language in ("vi", "en", "zh"):
        voices = voice_options_for_language(language, "vi", "edge")
        assert len(voices) == 2
        assert all(not item["voice"].startswith("omnivoice:") for item in voices)


def test_edge_single_narration_routes_without_loading_omnivoice(tmp_path):
    with patch.object(edge, "synthesize_to_mp3") as synthesize:
        tts.generate_single_voice("Xin chào", str(tmp_path / "out.mp3"), VOICE, "fixture", provider="edge")
    synthesize.assert_called_once_with("Xin chào.", VOICE, str(tmp_path / "out.mp3"), "fixture", language_id="vi")


def test_edge_skips_local_voice_warmup():
    from hflow.desktop.smart_warmup_controller import SmartWarmupController

    controller = SmartWarmupController(SimpleNamespace(_keep_models_warm=True), Mock())
    controller.request("voice", {"provider": "edge"})
    assert not controller._requests


def test_edge_policy_invalidates_only_edge_checkpoint_keys():
    from hflow.pipeline.process_video import _voice_checkpoint_signature

    video = SimpleNamespace(tts_provider="edge", tts_voice=VOICE, target_language="vi", files={}, speaker_mode="single")
    old_edge = _voice_checkpoint_signature(video, "transcript")
    video.tts_provider, video.tts_voice = "omnivoice", "omnivoice:female"
    old_local = _voice_checkpoint_signature(video, "transcript")
    with patch.object(edge, "EDGE_CACHE_VERSION", "new-policy"):
        assert _voice_checkpoint_signature(video, "transcript") == old_local
        video.tts_provider, video.tts_voice = "edge", VOICE
        assert _voice_checkpoint_signature(video, "transcript") != old_edge
