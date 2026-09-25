import json
import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from haizflow.desktop.manual_edit_history import ManualEditHistory
from haizflow.desktop.manual_preview_audio_controller import (
    ManualPreviewAudioController,
    mix_frames,
    voice_segment_is_compatible,
)
from haizflow.desktop.manual_subtitle_model import ManualSubtitleModel, identify_segments
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.subtitle_overlay_renderer import export_events, rasterize

QML = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


class ManualEditorSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_full_unicode_draft_and_revision_survive_stale_refresh(self):
        original = [{"text": "Cũ", "start": 0, "end": 12}]
        text = "  Đây là nội dung tiếng Việt, có dấu.\n" * 30 + "  "
        model = ManualSubtitleModel()
        model.load("video", original)
        segment_id = model.segments[0]["segment_id"]
        saved = []
        model.saved.connect(lambda *args: saved.append(args))
        with tempfile.TemporaryDirectory() as directory, \
             patch("haizflow.services.manual_artifacts.cache_root", return_value=Path(directory)), \
             patch("haizflow.desktop.manual_subtitle_model.video_store.get_video", return_value=None), \
             patch("haizflow.pipeline.manual_tools.publish_edited_subtitles") as publish:
            self.assertTrue(model.saveText(segment_id, text, 0, "r1"))
            model.load("video", original)
            self.assertEqual(model.segments[0]["text"], text)
            self.assertFalse(model.saveText(segment_id, "stale", 0, "r0"))
            for _ in range(100):
                self.app.processEvents()
                if saved:
                    break
                QTest.qWait(10)
            self.assertTrue(saved)
            self.assertEqual(publish.call_args.args[1][0]["text"], text)
            document = json.loads((Path(directory)/"working/document.json").read_text(encoding="utf-8"))
            self.assertEqual(document["segments"][0]["text"], text)
        model.close()

    def test_ids_do_not_change_when_text_or_timing_is_edited(self):
        rows = identify_segments("video", [{"text": "a", "start": 0, "end": 1}])
        identity = rows[0]["segment_id"]
        rows[0].update(text="b", end=2)
        self.assertEqual(identify_segments("video", rows)[0]["segment_id"], identity)

    def test_edit_history_is_per_video_and_separate_from_navigation(self):
        history = ManualEditHistory()
        model = ManualSubtitleModel(history=history)
        model.load("video-a", [{"text": "ban đầu", "start": 0, "end": 1}])
        segment_id = model.segments[0]["segment_id"]
        with tempfile.TemporaryDirectory() as directory, \
             patch("haizflow.services.manual_artifacts.cache_root", return_value=Path(directory)), \
             patch("haizflow.desktop.manual_subtitle_model.video_store.get_video", return_value=None), \
             patch("haizflow.pipeline.manual_tools.publish_edited_subtitles"):
            self.assertTrue(model.saveText(segment_id, "đã sửa", 0, "edit"))
            self.assertTrue(history.canUndo)
            self.assertEqual(history.undoLabel, "subtitle_text")
            self.assertTrue(history.undo())
            self.assertEqual(model.segments[0]["text"], "ban đầu")
            self.assertTrue(history.canRedo)
            self.assertTrue(history.redo())
            self.assertEqual(model.segments[0]["text"], "đã sửa")
            model.load("video-b", [{"text": "video khác", "start": 0, "end": 1}])
            self.assertFalse(history.canUndo)
            self.assertFalse(history.canRedo)
            history.select_video("video-a")
            self.assertTrue(history.canUndo)
            self.assertEqual(history.undoLabel, "subtitle_text")
        model.close()

    def test_edit_history_accepts_changes_for_an_inactive_document(self):
        history = ManualEditHistory()
        applied = []
        history.select_context("settings")
        history.record(
            "Cài đặt video",
            lambda: applied.append("undo") or True,
            lambda: applied.append("redo") or True,
            context_id="video:video-a",
        )
        self.assertFalse(history.canUndo)
        history.select_video("video-a")
        self.assertTrue(history.canUndo)
        self.assertTrue(history.undo())
        self.assertEqual(applied, ["undo"])
        history.select_context("settings")
        self.assertFalse(history.canUndo)
        history.select_video("video-a")
        self.assertTrue(history.canRedo)

    def test_delayed_settings_save_records_history_for_its_own_video(self):
        before_video = SimpleNamespace(video_id="video-a", marker="before")
        after_video = SimpleNamespace(video_id="video-a", marker="after")
        draft = object()
        host = SimpleNamespace(
            _selected_video_id="video-b",
            _manual_settings_drafts={"video-a": draft},
            _processing_queue=SimpleNamespace(contains=lambda _video_id: False),
            _apply_config_to_video=Mock(),
            _video_settings_snapshot=lambda video: {"marker": video.marker},
            _record_video_settings_change=Mock(),
        )
        with patch(
            "haizflow.desktop.qml_controller.video_store.get_video",
            side_effect=[before_video, after_video],
        ):
            self.assertTrue(HaizFlowController.persistVideoSettingsFor(host, "video-a"))
        host._apply_config_to_video.assert_called_once_with(before_video, draft)
        host._record_video_settings_change.assert_called_once_with(
            "video-a",
            {"marker": "before"},
            {"marker": "after"},
        )
        self.assertNotIn("video-a", host._manual_settings_drafts)

    def test_edit_history_covers_every_user_editable_video_setting(self):
        self.assertEqual(
            set(HaizFlowController._EDITABLE_VIDEO_SETTING_FIELDS),
            {
                "target_language",
                "speech_recognition_model",
                "tts_provider",
                "tts_voice",
                "speaker_mode",
                "subtitle_style",
                "subtitle_layout_override",
                "remove_original_subtitles",
                "original_subtitle_removal_mode",
                "output_format",
                "crop",
                "enable_audio_separation",
                "original_video_volume",
                "background_music_volume",
                "tts_volume",
                "watermark_text",
                "watermark_scale_percent",
                "watermark_kind",
                "watermark_opacity_percent",
                "watermark_outline_percent",
                "watermark_font_family",
                "watermark_text_color",
                "watermark_bold",
                "watermark_italic",
            },
        )

    def test_text_editor_only_commits_full_draft_when_save_is_pressed(self):
        class Controller(QObject):
            manualSubtitleSaved = Signal(str, int, str)
            manualSubtitleSaveFailed = Signal(str, str, str)
        controller = Controller()
        engine = QQmlEngine()
        engine.rootContext().setContextProperty("AppController", controller)
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML / "SubtitleTextEditor.qml")))
        self.assertTrue(component.isReady(), str(component.errors()))
        item = component.createWithInitialProperties({"segmentId": "sentence-1", "savedText": "Cũ",
                                                     "width": 300, "height": 500, "controller": controller})
        self.assertIsNotNone(item, str(component.errors()))
        self.app.processEvents()
        editor = item.findChild(QObject, "manualSubtitleTextInput")
        commits = []
        item.commitRequested.connect(lambda *args: commits.append(args))
        text = "  Tiếng Việt có dấu và xuống dòng.\n" * 25 + "  "
        editor.setProperty("text", text)
        item.dismiss()
        QTest.qWait(550)
        self.assertEqual(commits, [])
        self.assertEqual(item.property("saveStatus"), "dirty")
        item.apply()
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0][1], text)
        controller.manualSubtitleSaved.emit("sentence-1", 1, commits[0][3])
        self.assertEqual(item.property("saveStatus"), "saved")
        self.assertFalse(editor.property("activeFocus"))
        item.deleteLater()
        engine.deleteLater()

    def test_overlay_never_displays_previous_phrase_on_cache_miss(self):
        from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer
        renderer = SubtitleOverlayRenderer()
        renderer._events = [{"start": 0, "end": 1, "body": "first"},
                            {"start": 1, "end": 2, "body": "second"}]
        renderer._cache[(0, "first")] = {"normal": "first.png"}
        with patch.object(renderer, "_request_frame"):
            renderer.seek(.5)
            self.assertEqual(renderer.frame["normal"], "first.png")
            renderer.seek(1.5)
            self.assertEqual(renderer.frame, {})
        renderer.close()

    def test_overlay_configuration_clears_old_frame_and_cancels_queued_work(self):
        from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer

        class PendingFuture:
            def __init__(self):
                self.cancelled_flag = False

            def cancel(self):
                self.cancelled_flag = True
                return True

        renderer = SubtitleOverlayRenderer()
        queued = PendingFuture()
        renderer._futures.add(queued)
        renderer._frame = {"normal": "old-revision.png"}
        changes = []
        renderer.changed.connect(lambda: changes.append(True))
        layout = json.dumps({
            "fontSize": 32,
            "outline": 3,
            "positionXPercent": 50,
            "positionYPercent": 82,
            "layoutWidth": 300,
            "layoutHeight": 70,
            "outputWidth": 360,
            "outputHeight": 640,
        })
        with patch.object(renderer, "_submit"):
            renderer.configure('[]', layout, True)
        self.assertTrue(queued.cancelled_flag)
        self.assertEqual(renderer.frame, {})
        self.assertTrue(changes)
        renderer.close()

    def test_overlay_release_drops_editor_state_but_keeps_raster_cache(self):
        from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer

        renderer = SubtitleOverlayRenderer()
        renderer._key = "video-a"
        renderer._events = [{"start": 0, "end": 1, "body": "old"}]
        renderer._header = "header"
        renderer._layout = {"outputWidth": 360}
        renderer._frame = {"normal": "old.png"}
        renderer._cache[(0, "old")] = {"normal": "cached.png"}
        renderer.release()
        self.assertEqual(renderer.frame, {})
        self.assertEqual(renderer._events, [])
        self.assertEqual(renderer._key, "")
        self.assertIn((0, "old"), renderer._cache)
        renderer.close()

    def test_mix_mutes_only_stale_voice_and_loops_music(self):
        samples = np.full((8, 2), 1000, dtype=np.int16)
        tracks = [{"id": "source", "kind": "source", "samples": samples, "start": 0},
                  {"id": "voice-1", "kind": "voice", "samples": samples, "start": 0},
                  {"id": "music", "kind": "music", "samples": samples[:2], "start": 0, "loop": True}]
        output = np.frombuffer(mix_frames(tracks, 1, 4, {"source": .5, "voice": 1, "music": .2},
                                         {"voice-1"}), dtype="<i2")
        self.assertTrue(np.all(output == 700))

    def test_voice_preview_keeps_only_sentences_matching_the_published_manifest(self):
        source = {"text": "Câu chưa đổi", "start": 1, "end": 2}
        self.assertTrue(voice_segment_is_compatible(dict(source), source))
        self.assertFalse(voice_segment_is_compatible({**source, "text": "Câu mới"}, source))
        # Single-speaker clips are text keyed, so moving a sentence keeps its
        # voice. Multiple-speaker clips also encode the recognized speaker at
        # that timestamp and therefore require timing compatibility.
        self.assertTrue(
            voice_segment_is_compatible({**source, "start": 3, "end": 4}, source, False)
        )
        self.assertFalse(
            voice_segment_is_compatible({**source, "start": 3, "end": 4}, source, True)
        )

    def test_repeated_seeks_reuse_one_audio_output_and_release_it(self):
        from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
        class Device:
            def write(self, data):
                return len(data)
        class Sink:
            def __init__(self):
                self.resets = 0
                self.stops = 0
                self.deleted = 0
                self.device = Device()
            def reset(self):
                self.resets += 1
            def start(self):
                return self.device
            def stop(self):
                self.stops += 1
            def deleteLater(self):
                self.deleted += 1
            def bytesFree(self):
                return 9600
            def bufferSize(self):
                return 9600
        audio = ManualPreviewAudioController()
        sink = Sink()
        audio._sink = sink
        audio._playing = True
        for index in range(100):
            audio.seek(index / 10)
            audio.setVolumes(index, 100 - index, 30)
            audio._pump()
            self.assertIs(audio._sink, sink)
            self.assertLess(abs(audio._cursor / 48000 - index / 10), .05)
        audio.close()
        self.assertEqual(sink.resets, 100)
        self.assertEqual(sink.stops, 1)
        self.assertEqual(sink.deleted, 1)
        self.assertIsNone(audio._sink)

    def test_karaoke_clock_tracks_samples_played_not_audio_buffered_ahead(self):
        class Device:
            def write(self, data):
                return len(data)

        class Sink:
            def __init__(self):
                self.device = Device()

            def reset(self):
                return None

            def start(self):
                return self.device

            def stop(self):
                return None

            def deleteLater(self):
                return None

            def bytesFree(self):
                return 4800

            def bufferSize(self):
                return 9600

        audio = ManualPreviewAudioController()
        audio._sink = Sink()
        audio._playing = True
        audio.seek(5.0)
        audio._pump()

        # 1,200 stereo frames were written and exactly 1,200 are buffered;
        # the visible karaoke clock must remain at the audible 5.0 seconds.
        self.assertAlmostEqual(audio.positionSeconds, 5.0, places=3)
        audio.close()

    def test_pending_voice_choice_does_not_replace_published_preview_audio(self):
        class PendingFuture:
            def __init__(self):
                self.cancelled_flag = False

            def add_done_callback(self, _callback):
                return None

            def cancel(self):
                self.cancelled_flag = True
                return True

        class RecordingExecutor:
            def __init__(self):
                self.calls = 0

            def submit(self, _callback):
                self.calls += 1
                return PendingFuture()

            def shutdown(self, **_kwargs):
                return None

        video = SimpleNamespace(
            video_id="manual-video",
            project_type="manual",
            tts_provider="edge",
            tts_voice="vi-VN-NamMinhNeural",
            enable_audio_separation=False,
            files={},
        )
        segments = [{"segment_id": "segment-a", "text": "Xin chào", "start": 0, "end": 1}]
        published = {
            "signature": "published-voice",
            "resolved_outputs": {"manifest": "voice-manifest.json"},
        }
        audio = ManualPreviewAudioController()
        audio._executor.shutdown(wait=False, cancel_futures=True)
        executor = RecordingExecutor()
        audio._executor = executor
        with patch("haizflow.pipeline.manual_tools.published_voice_record", return_value=published):
            audio.request(video, segments)
            original_key = audio._key
            video.tts_voice = "vi-VN-HoaiMyNeural"
            audio.request(video, segments)
            video.files["watermark"] = "HaizFlow"
            video.files["ocr_region"] = "region.json"
            audio.request(video, segments)

        self.assertEqual(audio._key, original_key)
        self.assertEqual(executor.calls, 1)
        audio.close()

    def test_obsolete_audio_decode_is_cancelled_when_audio_inputs_change(self):
        class PendingFuture:
            def __init__(self):
                self.cancelled_flag = False

            def add_done_callback(self, _callback):
                return None

            def cancel(self):
                self.cancelled_flag = True
                return True

        class RecordingExecutor:
            def __init__(self):
                self.futures = []

            def submit(self, _callback):
                future = PendingFuture()
                self.futures.append(future)
                return future

            def shutdown(self, **_kwargs):
                return None

        video = SimpleNamespace(
            video_id="manual-video",
            project_type="manual",
            enable_audio_separation=False,
            files={},
        )
        segments = [{"segment_id": "segment-a", "text": "Xin chào", "start": 0, "end": 1}]
        audio = ManualPreviewAudioController()
        audio._executor.shutdown(wait=False, cancel_futures=True)
        executor = RecordingExecutor()
        audio._executor = executor
        with patch("haizflow.pipeline.manual_tools.published_voice_record", return_value=None):
            audio.request(video, segments)
            first = executor.futures[0]
            video.files["background_music"] = "new-music.mp3"
            audio.request(video, segments)
        self.assertTrue(first.cancelled_flag)
        self.assertEqual(len(executor.futures), 2)
        audio.close()

    def test_manual_audio_refresh_is_dormant_outside_editor(self):
        host = SimpleNamespace(
            _manual_editor_active=False,
            _selected_video=Mock(),
            _manual_audio=Mock(),
            _manual_subtitles=SimpleNamespace(video_id="manual-video", segments=[]),
        )
        HaizFlowController.refreshManualPreviewAudio(host)
        host._selected_video.assert_not_called()
        host._manual_audio.request.assert_not_called()

    def test_reopening_editor_does_not_run_pending_voice_refresh(self):
        timer = Mock()
        timer.isActive.return_value = False
        subtitles = Mock()
        host = SimpleNamespace(
            _manual_editor_active=False,
            _manual_voice_video_id="manual-video",
            _selected_video_id="manual-video",
            _manual_voice_refresh_pending=True,
            _manual_voice_refresh_enabled=True,
            _manual_voice_refresh_timer=timer,
            _manual_subtitles=subtitles,
            reviewSegments=[{"text": "Đã sửa", "start": 0, "end": 1}],
            refreshManualPreviewAudio=Mock(),
            _schedule_manual_cache_migration=Mock(),
        )
        with patch("haizflow.desktop.qml_controller.QTimer.singleShot") as single_shot:
            HaizFlowController.loadManualSubtitles(host)
        self.assertTrue(host._manual_editor_active)
        subtitles.load.assert_called_once_with("manual-video", host.reviewSegments)
        host.refreshManualPreviewAudio.assert_not_called()
        self.assertEqual([call.args[0] for call in single_shot.call_args_list], [180, 950])
        single_shot.call_args_list[0].args[1]()
        host.refreshManualPreviewAudio.assert_called_once_with()
        host._schedule_manual_cache_migration.assert_not_called()
        single_shot.call_args_list[1].args[1]()
        host._schedule_manual_cache_migration.assert_called_once_with("manual-video")
        timer.start.assert_not_called()

    def test_startup_indexes_migrated_manual_projects_and_defers_legacy_work(self):
        manual_a = SimpleNamespace(
            video_id="manual-a",
            project_type="manual",
            manual_artifact_migration_version=1,
        )
        download = SimpleNamespace(video_id="download-a", project_type="download")
        legacy = SimpleNamespace(
            video_id="manual-legacy",
            project_type="manual",
            manual_artifact_migration_version=0,
        )
        manual_b = SimpleNamespace(
            video_id="manual-b",
            project_type="manual",
            manual_artifact_migration_version=1,
        )
        host = SimpleNamespace(
            _background_shutdown_event=threading.Event(),
            _manual_cache_jobs_lock=threading.Lock(),
            _manual_cache_jobs=set(),
            _manual_cache_indexed=set(),
            _manual_cache_events=queue.Queue(),
            _startup_maintenance_events=queue.Queue(),
            _migrate_legacy_project_thumbnails=Mock(),
        )

        with (
            patch("haizflow.desktop.qml_controller.video_store.migrate_legacy_project_data", return_value=[]),
            patch("haizflow.desktop.qml_controller.video_store.recover_interrupted_videos", return_value=[]),
            patch(
                "haizflow.desktop.qml_controller.video_store.list_videos",
                return_value=[manual_a, download, legacy, manual_b],
            ),
            patch("haizflow.pipeline.manual_tools.migrate_legacy_artifacts", return_value=False) as migrate,
            patch(
                "haizflow.pipeline.manual_tools.restore_cached_variants",
                side_effect=lambda video_id, **_kwargs: [f"restored:{video_id}"],
            ) as restore,
        ):
            HaizFlowController._run_startup_maintenance(host)

        self.assertEqual([call.args[0] for call in migrate.call_args_list], ["manual-a", "manual-b"])
        self.assertEqual([call.args[0] for call in restore.call_args_list], ["manual-a", "manual-b"])
        self.assertTrue(all(call.kwargs == {"validate": False} for call in restore.call_args_list))
        events = [host._manual_cache_events.get_nowait(), host._manual_cache_events.get_nowait()]
        self.assertEqual([event["video_id"] for event in events], ["manual-a", "manual-b"])

    def test_cache_recovery_reconciles_voice_and_music_into_open_editor(self):
        selected = SimpleNamespace(video_id="manual-a", project_type="manual")
        ensured_document = object()
        synced_document = object()
        subtitles = Mock()
        subtitles.segments = [{"segment_id": "segment-a", "text": "Xin chào"}]
        host = SimpleNamespace(
            _manual_cache_events=queue.Queue(),
            _manual_cache_jobs_lock=threading.Lock(),
            _manual_cache_jobs={"manual-a"},
            _manual_cache_indexed=set(),
            _selected_video_id="manual-a",
            _selected_video_snapshot=None,
            manualToolStateChanged=SimpleNamespace(emit=Mock()),
            _manual_subtitles=subtitles,
            reviewSegments=[{"text": "Xin chào", "start": 0, "end": 1}],
            _manual_editor_document=SimpleNamespace(set_document=Mock()),
            _manual_preview_composition=SimpleNamespace(refresh=Mock()),
            manualSubtitleDocumentChanged=SimpleNamespace(emit=Mock()),
            refreshManualPreviewAudio=Mock(),
        )
        host._manual_cache_events.put(
            {"video_id": "manual-a", "changed": True, "restored": ["voice", "music"], "error": ""}
        )

        with (
            patch("haizflow.desktop.qml_controller.video_store.get_video", return_value=selected),
            patch("haizflow.desktop.qml_controller.editor_documents.ensure", return_value=ensured_document) as ensure,
            patch(
                "haizflow.desktop.qml_controller.editor_documents.sync_subtitle_clips",
                return_value=synced_document,
            ) as sync,
        ):
            HaizFlowController._drain_manual_cache_events(host)

        self.assertIn("manual-a", host._manual_cache_indexed)
        subtitles.load.assert_called_once_with("manual-a", host.reviewSegments)
        ensure.assert_called_once_with(selected)
        sync.assert_called_once_with(selected, subtitles.segments)
        host._manual_editor_document.set_document.assert_called_once_with(synced_document)
        host._manual_preview_composition.refresh.assert_called_once_with()
        host.refreshManualPreviewAudio.assert_called_once_with()

    def test_scrub_keeps_latest_target_across_source_swap(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML/"PreviewScrubController.qml")))
        self.assertTrue(component.isReady(), str(component.errors()))
        item = component.create()
        seeks = []
        item.seekRequested.connect(seeks.append)
        item.begin(1000, False)
        item.updatePosition(2200)
        item.sourceChanged()
        item.observe(0)
        self.assertEqual(item.property("scrubPositionMs"), 2200)
        item.end(4500)
        item.sourceReady()
        self.assertEqual(seeks[-1], 4500)
        item.observe(1000)
        self.assertEqual(item.property("scrubPositionMs"), 4500)
        item.observe(4500)
        self.assertFalse(item.property("pending"))
        item.deleteLater()
        engine.deleteLater()

    def test_libass_sprites_have_identical_geometry(self):
        layout = dict(outputWidth=360, outputHeight=640, layoutWidth=300, layoutHeight=70,
                      fontSize=32, outline=3, positionXPercent=50, positionYPercent=82)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            header, events = export_events([{"text": "Một ngày tốt lành", "start": 0, "end": 3}],
                                           layout, True, work)
            self.assertTrue(events)
            frame = rasterize(header, events[0]["body"], layout, work)
            from PIL import Image
            normal = Image.open(QUrl(frame["normal"]).toLocalFile())
            karaoke = Image.open(QUrl(frame["karaoke"]).toLocalFile())
            self.assertEqual(normal.getchannel("A").getbbox(), karaoke.getchannel("A").getbbox())
            self.assertLess(frame["height"], 100)
            self.assertGreater(frame["width"], 20)
            self.assertNotEqual(normal.tobytes(), karaoke.tobytes())


if __name__ == "__main__":
    unittest.main()
