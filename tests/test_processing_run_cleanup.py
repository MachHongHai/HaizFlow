"""Cancel rolls back this run; pause/resume preserves it; restart discards it."""

import uuid
from pathlib import Path

import pytest

from haizflow.schemas.video import VideoConfig
from haizflow.services import manual_artifacts, processing_runs, project_store, video_store


@pytest.fixture
def video_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(processing_runs, "_RUNS", {})
    monkeypatch.setattr(processing_runs, "_CHECKED", set())
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORTS", {})
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORT_STATES", {})
    processing_runs._CURRENT.run = None
    def create(kind="manual"):
        project = project_store.create_project("Run " + uuid.uuid4().hex[:8], str(tmp_path), kind)
        config = VideoConfig(project_type=kind, project_key=project["key"], project_id=project["project_id"],
                             project_name=project["project_name"], project_directory=str(tmp_path))
        video = video_store.create_video(uuid.uuid4().hex, "source.mp4", config)
        Path(video.files["video_input"]).write_bytes(b"original source")
        video_store.update_video(video.video_id, manual_target_tool="export" if kind == "manual" else "",
                                 status="processing")
        return video_store.get_video(video.video_id)
    yield create
    processing_runs._CURRENT.run = None


def artifact(video, kind, signature, data=b"result", activate=True):
    staged = manual_artifacts.create_staging_directory(video.video_id, kind)
    (staged / "result.bin").write_bytes(data)
    return manual_artifacts.publish(video.video_id, kind, signature, staged, {"data": "result.bin"},
                                    activate_artifact=activate)


@pytest.mark.parametrize("action", ["cancel", "restart", "resume"])
def test_reopen_recovers_unflushed_publications_without_deleting_unrelated_cache(video_factory, monkeypatch, action):
    video = video_factory()
    old = artifact(video, "tts_clip", "before-crash", activate=False)
    run = processing_runs.begin(video.video_id)
    created = artifact(video, "tts_clip", "created-before-crash", activate=False)
    # Simulate exit before finish() and before the 16-artifact journal flush.
    processing_runs._CURRENT.run = None
    monkeypatch.setattr(processing_runs, "_RUNS", {})
    monkeypatch.setattr(processing_runs, "_CHECKED", set())
    unrelated = artifact(video, "tts_clip", "not-owned-by-run", activate=False)
    video_store.update_video(video.video_id, status="paused", resume_step="export")
    restored = processing_runs._get(video.video_id)
    assert created["artifact_id"] in restored["created"]
    assert unrelated["artifact_id"] not in restored["created"]
    if action == "cancel":
        processing_runs.request_discard(video.video_id, run["id"])
        assert processing_runs.settle_export(video.video_id, "cancelled", run["id"])
    else:
        processing_runs.begin(video.video_id, resuming=action == "resume")
        video_store.update_video(video.video_id, status="manual_ready")
        processing_runs.finish(video.video_id)
    assert Path(created["resolved_outputs"]["data"]).exists() == (action == "resume")
    assert Path(old["resolved_outputs"]["data"]).exists()
    assert Path(unrelated["resolved_outputs"]["data"]).exists()


@pytest.mark.parametrize("status", ["paused", "failed"])
@pytest.mark.parametrize("reopen", [False, True])
def test_cache_maintenance_keeps_completed_partial_voice_until_discard(video_factory, monkeypatch, status, reopen):
    video = video_factory()
    old = artifact(video, "export", "before-partial")
    unused = artifact(video, "tts_clip", "old-unused", activate=False)
    run = processing_runs.begin(video.video_id)
    partial = artifact(video, "tts_clip", "finished-sentence", activate=False)
    video_store.update_video(video.video_id, status=status, resume_step="voice")
    processing_runs.finish(video.video_id)
    if reopen:
        monkeypatch.setattr(processing_runs, "_RUNS", {})
        monkeypatch.setattr(processing_runs, "_CHECKED", set())
    manual_artifacts.prune(video.video_id, limit_bytes=0)
    assert Path(partial["resolved_outputs"]["data"]).exists()
    assert Path(old["resolved_outputs"]["data"]).exists()
    assert not Path(unused["resolved_outputs"]["data"]).exists()
    processing_runs.request_discard(video.video_id, run["id"])
    assert processing_runs.settle_export(video.video_id, "cancelled", run["id"])
    assert not Path(partial["resolved_outputs"]["data"]).exists()
    assert Path(old["resolved_outputs"]["data"]).exists()


def test_late_cancel_cleanup_cannot_clear_a_new_manual_tool_request(video_factory):
    video = video_factory()
    video_store.update_video(video.video_id, status="manual_ready", manual_target_tool="", step="manual_voice")
    scope = processing_runs.arm_export(video.video_id)
    video_store.update_video(video.video_id, status="processing", manual_target_tool="export")
    processing_runs.begin(video.video_id)
    current = artifact(video, "audio_mix", "cancel-pinned")
    manual_artifacts.pin(video.video_id, "audio_mix", "cancel-pinned", "late-reader")
    try:
        processing_runs.request_discard(video.video_id, scope)
        video_store.update_video(video.video_id, status="cancelled")
        processing_runs.finish(video.video_id)
        assert processing_runs.discard_pending(video.video_id, scope)
    finally:
        manual_artifacts.unpin(video.video_id, "late-reader")
    video_store.update_video(video.video_id, status="processing", manual_target_tool="voice", step="starting")
    processing_runs.begin(video.video_id)
    refreshed = video_store.get_video(video.video_id)
    assert refreshed.manual_target_tool == "voice" and refreshed.status == "processing"
    assert not Path(current["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.finish(video.video_id)


@pytest.mark.parametrize('tool,kind', [('translation', 'recognition'), ('separation', 'source_audio'),
    ('voice', 'tts_clip'), ('image', 'ocr_region'), ('audio', 'audio_mix')])
@pytest.mark.parametrize('reopen', [False, True])
def test_retry_failed_tool_keeps_completed_outputs_without_requiring_deletion(video_factory, monkeypatch, tool, kind, reopen):
    """A provider failure is not Cancel; its completed prerequisites are reusable."""
    video = video_factory()
    baseline = artifact(video, 'separation', 'older-success')
    video_store.update_video(video.video_id, manual_target_tool=tool)
    processing_runs.begin(video.video_id)
    completed = artifact(video, kind, 'completed-before-model-error', activate=kind != 'tts_clip')
    video_store.update_video(video.video_id, status='failed', error='Gemini HTTP 503', manual_target_tool=tool)
    processing_runs.finish(video.video_id)
    failed_id = processing_runs.current_id(video.video_id)
    if reopen:
        monkeypatch.setattr(processing_runs, '_RUNS', {})
        monkeypatch.setattr(processing_runs, '_CHECKED', set())
    video_store.update_video(video.video_id, status='processing', manual_target_tool=tool, resume_step='')
    # Preview/AV may retain an output, but retry must not require removing it.
    monkeypatch.setattr(manual_artifacts, '_remove_inactive_directory', lambda _path: False)
    retry = processing_runs.begin(video.video_id)
    assert retry['id'] != failed_id
    assert Path(completed['resolved_outputs']['data']).exists()
    assert Path(baseline['resolved_outputs']['data']).exists()
    video_store.update_video(video.video_id, status='manual_ready')
    processing_runs.finish(video.video_id)


@pytest.mark.parametrize('reopen', [False, True])
def test_legacy_discarding_journal_can_restart_while_old_cache_reader_is_open(video_factory, monkeypatch, reopen):
    video = video_factory()
    old = artifact(video, 'export', 'previous-valid')
    processing_runs.begin(video.video_id)
    current = artifact(video, 'export', 'failed-new')
    manual_artifacts.pin(video.video_id, 'export', 'failed-new', 'old-preview')
    video_store.update_video(video.video_id, status='failed', error='503')
    processing_runs.finish(video.video_id)
    previous = processing_runs._get(video.video_id)
    previous['discard'] = True  # Journal left by 1.0.0's failed retry.
    assert not processing_runs.rollback(previous)
    assert previous['state'] == 'discarding'
    if reopen:
        monkeypatch.setattr(processing_runs, '_RUNS', {})
        monkeypatch.setattr(processing_runs, '_CHECKED', set())
    video_store.update_video(video.video_id, status='processing', manual_target_tool='export')
    try:
        retry = processing_runs.begin(video.video_id)
        assert retry['id'] != previous['id']
        assert retry['active_artifacts'] == {'export': 'previous-valid'}
        assert Path(old['resolved_outputs']['data']).exists()
        assert Path(current['resolved_outputs']['data']).exists()
        assert manual_artifacts.resolve(video.video_id, 'export', 'failed-new') is None
        assert video_store.get_video(video.video_id).active_artifacts == {'export': 'previous-valid'}
    finally:
        manual_artifacts.unpin(video.video_id, 'old-preview')
        video_store.update_video(video.video_id, status='manual_ready')
        processing_runs.finish(video.video_id)
    manual_artifacts.prune(video.video_id)
    assert not Path(current['resolved_outputs']['data']).exists()
    assert Path(old['resolved_outputs']['data']).exists()


@pytest.mark.parametrize('reopen', [False, True])
def test_legacy_self_referencing_journal_cannot_permanently_protect_its_own_output(video_factory, monkeypatch, reopen):
    """Reproduce the persisted 1.0.0 stale pre-rollback snapshot, without any OS lock."""
    video = video_factory()
    baseline = artifact(video, 'export', 'real-older-result')
    processing_runs.begin(video.video_id)
    current = artifact(video, 'export', 'self-pinned-new-result')
    run = processing_runs._get(video.video_id)
    new_path = current['resolved_outputs']['data']
    # The old begin() saved references from before it rolled back the last
    # attempt, even though baseline_ids correctly came from after rollback.
    run['active_artifacts'] = {'export': 'self-pinned-new-result'}
    run['files']['final_video'] = new_path
    video_store.update_video(video.video_id, status='failed', files={**video.files, 'final_video': new_path})
    processing_runs.finish(video.video_id)
    run['discard'] = True
    run['state'] = 'discarding'
    processing_runs._save(run)
    if reopen:
        monkeypatch.setattr(processing_runs, '_RUNS', {})
        monkeypatch.setattr(processing_runs, '_CHECKED', set())
    video_store.update_video(video.video_id, status='processing', resume_step='')
    retry = processing_runs.begin(video.video_id)
    assert retry['id'] != run['id']
    assert 'export' not in retry['active_artifacts']
    assert retry['files'].get('final_video') != new_path
    assert not Path(new_path).exists()
    assert Path(baseline['resolved_outputs']['data']).exists()
    video_store.update_video(video.video_id, status='manual_ready')
    processing_runs.finish(video.video_id)


@pytest.mark.parametrize('prior_status', ['error', 'discarded'])
def test_a_preexisting_error_record_is_not_a_preexisting_successful_output(video_factory, prior_status):
    video = video_factory()
    manual_artifacts.record_error(video.video_id, 'tts_clip', 'retry-key', 'old model error')
    manifest = manual_artifacts.load_manifest(video.video_id)
    manifest['artifacts']['tts_clip:retry-key']['status'] = prior_status
    manual_artifacts._save_manifest(video.video_id, manifest)
    processing_runs.begin(video.video_id)
    completed = artifact(video, 'tts_clip', 'retry-key', activate=False)
    video_store.update_video(video.video_id, status='cancelled')
    processing_runs.request_discard(video.video_id)
    processing_runs.finish(video.video_id)
    assert not Path(completed['resolved_outputs']['data']).exists()


def test_transient_temp_cleanup_failure_has_evidence_and_can_retry(video_factory, monkeypatch):
    video = video_factory()
    processing_runs.begin(video.video_id)
    run = processing_runs._get(video.video_id)
    generated = Path(video_store.get_video_dir(video.video_id)) / 'temp' / 'generated.tmp'
    generated.parent.mkdir(exist_ok=True)
    generated.write_bytes(b'owned partial')
    original = Path.unlink
    def locked(path, *args, **kwargs):
        if path == generated:
            raise PermissionError(13, 'fixture sharing violation')
        return original(path, *args, **kwargs)
    with monkeypatch.context() as locked_context:
        locked_context.setattr(Path, 'unlink', locked)
        assert not processing_runs.rollback(run)
    assert run['cleanup_error']['phase'] == 'temporary_files'
    assert run['cleanup_error']['type'] == 'PermissionError'
    assert processing_runs.rollback(run)
    assert not generated.exists()


@pytest.mark.parametrize('reopen', [False, True])
def test_manual_gemini_503_then_fresh_run_can_translate_and_publish_subtitles(video_factory, monkeypatch, reopen):
    import json
    from haizflow.pipeline import manual_tools
    from haizflow.services import gemini_translation

    video = video_factory()
    video_store.update_video(video.video_id, manual_target_tool='translation', enable_audio_separation=False,
        translation_model='gemini-3.1-flash-lite', target_language='vi')
    source_segments = [{'start': 0., 'end': 1.8, 'text': 'Hello friend.', 'language': 'en'}]
    def transcribe(_audio, output, *_args, **_kwargs):
        Path(output).write_text(json.dumps(source_segments), encoding='utf-8')
    monkeypatch.setattr(manual_tools, 'transcribe', transcribe)
    monkeypatch.setattr(manual_tools, '_release_recognition_runtime', lambda: None)
    monkeypatch.setattr(manual_tools, 'shutdown_hymt2_worker', lambda: None)
    monkeypatch.setattr('haizflow.pipeline.omnivoice_tts.clear_runtime', lambda: None)
    monkeypatch.setattr(gemini_translation, 'active_key', lambda: 'isolated-test-key-not-real')
    calls = []
    def translate(chunk, **_kwargs):
        calls.append(chunk)
        if len(calls) == 1:
            raise RuntimeError('Gemini HTTP 503 UNAVAILABLE')
        return ['Chào bạn.']
    monkeypatch.setattr(gemini_translation, '_request_chunk', translate)
    # Never allow these regression tests to send real requests or spend tokens.
    monkeypatch.setattr(gemini_translation, "_open_request", lambda *_a, **_k: pytest.fail('Unexpected network request'))
    processing_runs.begin(video.video_id)
    manual_tools.run_manual_tool_sync(video.video_id, 'translation')
    processing_runs.finish(video.video_id)
    failed = video_store.get_video(video.video_id)
    assert failed.status == 'failed' and '503' in failed.error
    recognized = manual_artifacts.active(failed, 'recognition')
    assert recognized
    original_recognition = Path(recognized['resolved_outputs']['segments'])
    if reopen:
        monkeypatch.setattr(processing_runs, '_RUNS', {})
        monkeypatch.setattr(processing_runs, '_CHECKED', set())
    assert manual_tools.prepare_manual_rerun(video.video_id, 'translation')
    video_store.update_video(video.video_id, status='processing', resume_step='')
    processing_runs.begin(video.video_id)
    manual_tools.run_manual_tool_sync(video.video_id, 'translation')
    processing_runs.finish(video.video_id)
    completed = video_store.get_video(video.video_id)
    assert completed.status == 'manual_ready', completed.error
    assert not completed.error and original_recognition.exists()
    assert len(calls) == 2
    published = manual_artifacts.active(completed, 'subtitle_document')
    assert published
    assert json.loads(Path(published['resolved_outputs']['segments']).read_text('utf-8'))[0]['text'] == 'Chào bạn.'


@pytest.mark.parametrize('tool,kind', [('translation', 'recognition'), ('separation', 'source_audio'), ('voice', 'tts_clip')])
def test_resume_after_reopen_preserves_completed_artifacts_and_scope(video_factory, monkeypatch, tool, kind):
    video = video_factory()
    video_store.update_video(video.video_id, manual_target_tool=tool)
    run = processing_runs.begin(video.video_id)
    complete = artifact(video, kind, 'completed-before-pause', activate=kind != 'tts_clip')
    video_store.update_video(video.video_id, status='paused', resume_step=tool)
    processing_runs.finish(video.video_id)
    monkeypatch.setattr(processing_runs, '_RUNS', {})
    monkeypatch.setattr(processing_runs, '_CHECKED', set())
    resumed = processing_runs.begin(video.video_id, resuming=True)
    assert resumed['id'] == run['id'] and not resumed['discard']
    assert Path(complete['resolved_outputs']['data']).exists()
    video_store.update_video(video.video_id, status='manual_ready')
    processing_runs.finish(video.video_id)


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Actual Windows sharing-mode regression')
def test_restart_with_real_windows_locked_cache_retires_then_cleans_when_released(video_factory, monkeypatch):
    import ctypes
    from ctypes import wintypes

    video = video_factory()
    before = artifact(video, 'export', 'before-real-lock')
    processing_runs.begin(video.video_id)
    created = artifact(video, 'export', 'real-reader-locked')
    locked = Path(created['resolved_outputs']['data'])
    video_store.update_video(video.video_id, status='paused', resume_step='export')
    processing_runs.finish(video.video_id)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(locked), 0x80000000, 3, None, 3, 0x80, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        video_store.update_video(video.video_id, status='processing', resume_step='')
        processing_runs.begin(video.video_id, resuming=False)
        assert locked.exists()
        assert manual_artifacts.resolve(video.video_id, 'export', 'real-reader-locked') is None
        assert Path(before['resolved_outputs']['data']).exists()
    finally:
        kernel.CloseHandle(handle)
        video_store.update_video(video.video_id, status='manual_ready')
        processing_runs.finish(video.video_id)
    manual_artifacts.prune(video.video_id)
    assert not locked.exists()
    assert Path(before['resolved_outputs']['data']).exists()


def test_cancel_removes_new_complete_cache_but_restores_previous_result(video_factory):
    video = video_factory()
    old = artifact(video, "export", "old", b"old complete result")
    old_path = Path(old["resolved_outputs"]["data"])
    video_store.update_video(video.video_id, files={**video.files, "final_video": str(old_path)})
    scope_id = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    new = artifact(video, "export", "new", b"new complete result")
    new_path = Path(new["resolved_outputs"]["data"])
    video_store.update_video(video.video_id, files={**video.files, "final_video": str(new_path)}, status="cancelled")
    processing_runs.request_discard(video.video_id, scope_id)
    processing_runs.finish(video.video_id)
    assert old_path.read_bytes() == b"old complete result"
    assert not new_path.exists()
    restored = video_store.get_video(video.video_id)
    assert restored.active_artifacts["export"] == "old"
    assert restored.files["final_video"] == str(old_path)
    assert Path(video.files["video_input"]).read_bytes() == b"original source"
    assert processing_runs._get(video.video_id) is None


@pytest.mark.parametrize("prior_status", ["manual_ready", "done", "paused"])
def test_cancelled_manual_export_restores_exact_idle_state_after_cache_rollback(video_factory, prior_status):
    video = video_factory()
    old = artifact(video, "export", "old-state")
    fields = {"status": prior_status, "step": "manual_voice", "step_detail": "Giọng đã tạo",
              "progress": 81, "current_item": 7, "total_items": 7, "error": None,
              "manual_target_tool": "voice" if prior_status == "paused" else "",
              "resume_step": "voice" if prior_status == "paused" else ""}
    video_store.update_video(video.video_id, **fields)
    identifier = processing_runs.arm_export(video.video_id)
    # Queue updates happen after capture, before the worker journal exists.
    video_store.update_video(video.video_id, status="processing", progress=0, manual_target_tool="export")
    processing_runs.begin(video.video_id)
    new = artifact(video, "export", "cancelled-new")
    video_store.update_video(video.video_id, status="cancelled", step="cancelled", progress=99, resume_step="")
    processing_runs.request_discard(video.video_id, identifier)
    processing_runs.finish(video.video_id)
    restored = video_store.get_video(video.video_id)
    for name, value in fields.items():
        assert getattr(restored, name) == value
    assert restored.active_artifacts["export"] == "old-state"
    assert Path(old["resolved_outputs"]["data"]).exists()
    assert not Path(new["resolved_outputs"]["data"]).exists()


def test_cancelled_export_idle_snapshot_survives_app_restart_journal_load(video_factory, monkeypatch):
    video = video_factory()
    video_store.update_video(video.video_id, status="manual_ready", manual_target_tool="", progress=87)
    identifier = processing_runs.arm_export(video.video_id)
    video_store.update_video(video.video_id, status="processing", manual_target_tool="export")
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="paused")
    processing_runs.finish(video.video_id)
    monkeypatch.setattr(processing_runs, "_RUNS", {})
    monkeypatch.setattr(processing_runs, "_CHECKED", set())
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORTS", {})
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORT_STATES", {})
    video_store.update_video(video.video_id, status="cancelled")
    assert processing_runs.settle_export(video.video_id, "cancelled", identifier)
    restored = video_store.get_video(video.video_id)
    assert restored.status == "manual_ready" and restored.progress == 87
    assert not restored.manual_target_tool


def test_queued_cancel_without_worker_restores_state_but_not_a_replaced_source(video_factory):
    video = video_factory()
    video_store.update_video(video.video_id, status="manual_ready", manual_target_tool="")
    video = video_store.get_video(video.video_id)
    snapshot = processing_runs.manual_export_state(video)
    video_store.update_video(video.video_id, status="cancelled", manual_target_tool="export")
    assert processing_runs.restore_cancelled_manual_export(video.video_id, snapshot)
    assert video_store.get_video(video.video_id).status == "manual_ready"
    video_store.update_video(video.video_id, status="cancelled", created_at="changed-source")
    assert not processing_runs.restore_cancelled_manual_export(video.video_id, snapshot)
    assert video_store.get_video(video.video_id).status == "cancelled"


def test_auto_export_cancel_keeps_its_original_cancel_semantics(video_factory):
    video = video_factory("single")
    assert processing_runs.manual_export_state(video) is None
    identifier = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id, identifier)
    processing_runs.finish(video.video_id)
    assert video_store.get_video(video.video_id).status == "cancelled"


def test_pause_and_resume_keep_progress_then_explicit_restart_removes_it(video_factory):
    video = video_factory()
    old = artifact(video, "tts_clip", "before", activate=False)
    processing_runs.begin(video.video_id)
    partial = artifact(video, "tts_clip", "during", activate=False)
    video_store.update_video(video.video_id, status="paused", resume_step="export")
    processing_runs.finish(video.video_id)
    assert Path(partial["resolved_outputs"]["data"]).exists()
    run_id = processing_runs._get(video.video_id)["id"]
    processing_runs.begin(video.video_id, resuming=True)
    assert processing_runs._get(video.video_id)["id"] == run_id
    video_store.update_video(video.video_id, status="paused")
    processing_runs.finish(video.video_id)
    processing_runs.begin(video.video_id, resuming=False)
    assert not Path(partial["resolved_outputs"]["data"]).exists()
    assert Path(old["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.finish(video.video_id)


def test_auto_cancel_restores_mutable_old_files_and_drops_only_new_files(video_factory):
    video = video_factory("single")
    temporary = Path(video_store.get_video_dir(video.video_id)) / "temp"
    temporary.mkdir(exist_ok=True)
    old = temporary / "voice_final.wav"
    old.write_bytes(b"previous valid audio")
    scope_id = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    old.write_bytes(b"overwritten by current run")
    new = temporary / "new-render.mp4"
    new.write_bytes(b"partial")
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id, scope_id)
    processing_runs.finish(video.video_id)
    assert old.read_bytes() == b"previous valid audio" and not new.exists()
    assert not list(temporary.parent.glob(".processing-backup-*"))


def test_prior_cache_cannot_be_pruned_while_run_temporarily_replaces_active_reference(video_factory):
    video = video_factory()
    old = artifact(video, "export", "old")
    processing_runs.begin(video.video_id)
    artifact(video, "export", "new")
    manual_artifacts.prune(video.video_id, limit_bytes=0)
    assert Path(old["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id)
    processing_runs.finish(video.video_id)


def test_pending_cancel_retries_after_reader_unpins_new_artifact(video_factory):
    video = video_factory()
    artifact(video, "export", "old")
    identifier = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    current = artifact(video, "export", "new")
    manual_artifacts.pin(video.video_id, "export", "new", "test-reader")
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id, identifier)
    processing_runs.finish(video.video_id)
    assert Path(current["resolved_outputs"]["data"]).exists()
    assert processing_runs.discard_pending(video.video_id, identifier)
    manual_artifacts.unpin(video.video_id, "test-reader")
    assert processing_runs.settle_export(video.video_id, "cancelled", identifier)
    assert not Path(current["resolved_outputs"]["data"]).exists()


def test_old_export_completion_cannot_discard_a_later_run(video_factory):
    video = video_factory()
    identifier = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="done")
    processing_runs.finish(video.video_id)
    processing_runs.settle_export(video.video_id, "done", identifier)
    new_id = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    current = artifact(video, "export", "new")
    processing_runs.request_discard(video.video_id, identifier)
    assert processing_runs.settle_export(video.video_id, "cancelled", identifier)
    assert not processing_runs._get(video.video_id)["discard"]
    assert processing_runs._get(video.video_id)["id"] == new_id
    assert Path(current["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="done")
    processing_runs.finish(video.video_id)
    processing_runs.settle_export(video.video_id, "done", new_id)


def test_switching_tools_after_pause_does_not_discard_completed_progress(video_factory):
    video = video_factory()
    video_store.update_video(video.video_id, manual_target_tool="voice")
    processing_runs.begin(video.video_id)
    partial = artifact(video, "tts_clip", "completed-before-pause", activate=False)
    video_store.update_video(video.video_id, status="paused", resume_step="voice")
    processing_runs.finish(video.video_id)
    video_store.update_video(video.video_id, manual_target_tool="image", resume_step="")
    processing_runs.begin(video.video_id, resuming=False)
    assert Path(partial["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.finish(video.video_id)


def test_cancel_waiting_export_disarms_only_it_not_prior_paused_tool(video_factory):
    video = video_factory()
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="paused", resume_step="export")
    processing_runs.finish(video.video_id)
    old = processing_runs._get(video.video_id)
    waiting_id = processing_runs.arm_export(video.video_id)
    processing_runs.request_discard(video.video_id, waiting_id)
    assert video.video_id not in processing_runs._ARMED_EXPORTS
    assert processing_runs._get(video.video_id)["id"] == old["id"]
    assert not old["discard"]
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.begin(video.video_id)
    processing_runs.finish(video.video_id)


def test_copy_of_previous_ready_render_does_not_keep_or_rollback_old_run_journal(video_factory):
    video = video_factory()
    processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    current = artifact(video, "export", "ready-from-previous-session")
    video_store.update_video(video.video_id, status="done")
    processing_runs.finish(video.video_id)
    assert processing_runs._get(video.video_id)["state"] == "ready"
    processing_runs.commit_previous_ready(video.video_id)
    assert processing_runs._get(video.video_id) is None
    assert Path(current["resolved_outputs"]["data"]).exists()


def test_export_cancel_cleans_published_worker_results_before_queue_detaches(video_factory, monkeypatch):
    import threading
    from unittest.mock import Mock
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
    from haizflow.desktop.video_export_controller import VideoExportController
    from haizflow.pipeline.process_registry import check_cancellation, clean_video, start_video
    from haizflow.services.processing_queue import SerialProcessingQueue

    app = QGuiApplication.instance() or QGuiApplication([])
    video = video_factory()
    old = artifact(video, "export", "before-run")
    started = threading.Event()
    release = threading.Event()
    state = {}
    host = QObject()
    host._settings_language = "vi"
    host._deleted_video_ids = set()
    host._initial_model_warmup_done = threading.Event()
    for name in ("exportStateChanged", "selectedVideoChanged", "processingChanged"):
        setattr(host, name, Mock())
    host.refreshVideos = Mock()
    lifecycle = ProcessingLifecycleController(host)
    task_queue = SerialProcessingQueue(lifecycle.execute_pipeline)
    host._processing_queue = task_queue
    exporter = VideoExportController(host)
    exporter.timer.stop()
    def pipeline(identifier, _tool):
        start_video(identifier)
        state["new"] = artifact(video_store.get_video(identifier), "audio_mix", "worker-new-result")
        started.set()
        try:
            release.wait(3)
            check_cancellation(identifier)
        except RuntimeError:
            video_store.update_video(identifier, status="cancelled", step="cancelled")
        finally:
            clean_video(identifier)
    monkeypatch.setattr("haizflow.pipeline.manual_tools.run_manual_tool_sync", pipeline)
    identifier = processing_runs.arm_export(video.video_id)
    job = {"videoId": video.video_id, "status": "rendering", "progress": 10, "runScopeId": identifier}
    exporter.jobs = [job]
    try:
        assert task_queue.enqueue(video.video_id) and started.wait(2)
        exporter._capture_render_owner(job)
        exporter.cancel_all()
        release.set()
        assert task_queue.shutdown(timeout_seconds=3)
        exporter.poll()
        assert not Path(state["new"]["resolved_outputs"]["data"]).exists()
        assert Path(old["resolved_outputs"]["data"]).exists()
        assert not exporter.busy and job["runSettled"]
        assert video_store.get_video(video.video_id).active_artifacts == {"export": "before-run"}
    finally:
        release.set()
        task_queue.shutdown(timeout_seconds=3)
        exporter.shutdown()
        app.processEvents()
