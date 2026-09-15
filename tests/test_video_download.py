import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services import video_download  # noqa: E402


class VideoDownloadTests(unittest.TestCase):
    def test_supported_social_links_are_normalized(self):
        cases = {
            "youtu.be/BaW_jenozKc": "YouTube",
            "https://www.youtube.com/watch?v=BaW_jenozKc": "YouTube",
            "https://vm.tiktok.com/example": "TikTok",
            "https://v.douyin.com/example": "Douyin",
            "https://www.bilibili.com/video/BV1xx411c7mD": "Bilibili",
            "https://www.instagram.com/reel/example": "Instagram",
            "https://vimeo.com/123": "Vimeo",
        }
        for value, expected_platform in cases.items():
            with self.subTest(value=value):
                url, platform = video_download.validate_video_url(value)
                self.assertTrue(url.startswith("https://"))
                self.assertEqual(platform, expected_platform)

    def test_mobile_share_text_extracts_the_supported_link(self):
        url, platform = video_download.validate_video_url(
            "Xem video này nhé https://vm.tiktok.com/ZM-demo/?share=1. Nội dung khác"
        )
        self.assertEqual(url, "https://vm.tiktok.com/ZM-demo/?share=1")
        self.assertEqual(platform, "TikTok")

    def test_lookalike_and_unrelated_hosts_are_rejected(self):
        for value in ("https://youtube.com.evil.example/video", "https://example.invalid/1", "file:///clip.mp4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    video_download.validate_video_url(value)

    def test_metadata_is_reduced_to_ui_fields(self):
        downloader = mock.MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.extract_info.return_value = {
            "title": "Demo clip",
            "duration": 42.8,
            "thumbnail": "https://example.com/thumb.jpg",
            "uploader": "Creator",
            "extractor_key": "Youtube",
            "webpage_url": "https://www.youtube.com/watch?v=demo",
        }
        with mock.patch("yt_dlp.YoutubeDL", return_value=downloader):
            metadata = video_download.inspect_video_url("https://youtu.be/demo")

        self.assertEqual(metadata.title, "Demo clip")
        self.assertEqual(metadata.platform, "YouTube")
        self.assertEqual(metadata.duration_seconds, 42)
        self.assertEqual(metadata.uploader, "Creator")

    def test_tiktok_metadata_uses_app_api_and_retries_a_transient_failure(self):
        first_downloader = mock.MagicMock()
        first_downloader.__enter__.return_value = first_downloader
        first_downloader.extract_info.side_effect = RuntimeError(
            "ERROR: [TikTok] Unable to extract universal data for rehydration"
        )
        second_downloader = mock.MagicMock()
        second_downloader.__enter__.return_value = second_downloader
        second_downloader.extract_info.return_value = {
            "title": "TikTok clip",
            "duration": 18,
            "extractor_key": "TikTok",
        }

        with (
            mock.patch("yt_dlp.YoutubeDL", side_effect=[first_downloader, second_downloader]) as youtube_dl,
            mock.patch("haizflow.services.video_download._wait_for_retry") as wait_for_retry,
        ):
            metadata = video_download.inspect_video_url("https://www.tiktok.com/@creator/video/123")

        self.assertEqual(metadata.title, "TikTok clip")
        self.assertEqual(youtube_dl.call_count, 2)
        self.assertEqual(wait_for_retry.call_count, 1)
        options = youtube_dl.call_args_list[0].args[0]
        self.assertEqual(options["extractor_args"]["tiktok"]["app_info"], [""])

    def test_tiktok_challenge_response_is_retried_with_browser_impersonation(self):
        first_downloader = mock.MagicMock()
        first_downloader.__enter__.return_value = first_downloader
        first_downloader.extract_info.side_effect = RuntimeError(
            "ERROR: [TikTok] Unexpected response from webpage request"
        )
        second_downloader = mock.MagicMock()
        second_downloader.__enter__.return_value = second_downloader
        second_downloader.extract_info.return_value = {
            "title": "Recovered TikTok clip",
            "duration": 20,
            "extractor_key": "TikTok",
        }

        with (
            mock.patch(
                "yt_dlp.YoutubeDL",
                side_effect=[first_downloader, second_downloader],
            ) as youtube_dl,
            mock.patch.object(video_download, "_wait_for_retry"),
            mock.patch.object(video_download.importlib.util, "find_spec", return_value=object()),
        ):
            metadata = video_download.inspect_video_url(
                "https://www.tiktok.com/@creator/video/123"
            )

        self.assertEqual(metadata.title, "Recovered TikTok clip")
        self.assertEqual(youtube_dl.call_count, 2)
        self.assertEqual(youtube_dl.call_args_list[1].args[0]["impersonate"], "chrome")

    def test_non_transient_tiktok_metadata_errors_are_not_retried(self):
        downloader = mock.MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.extract_info.side_effect = RuntimeError("ERROR: [TikTok] Video is private")

        with mock.patch("yt_dlp.YoutubeDL", return_value=downloader) as youtube_dl:
            with self.assertRaisesRegex(RuntimeError, "Video is private"):
                video_download.inspect_video_url("https://www.tiktok.com/@creator/video/123")

        self.assertEqual(youtube_dl.call_count, 1)

    def test_youtube_metadata_retries_a_temporary_dns_failure_with_fresh_session(self):
        first_downloader = mock.MagicMock()
        first_downloader.__enter__.return_value = first_downloader
        first_downloader.extract_info.side_effect = RuntimeError(
            "ERROR: Unable to download webpage: Temporary failure in name resolution"
        )
        second_downloader = mock.MagicMock()
        second_downloader.__enter__.return_value = second_downloader
        second_downloader.extract_info.return_value = {
            "title": "Recovered clip",
            "duration": 12,
            "extractor_key": "Youtube",
        }

        with (
            mock.patch(
                "yt_dlp.YoutubeDL",
                side_effect=[first_downloader, second_downloader],
            ) as youtube_dl,
            mock.patch.object(video_download, "_wait_for_retry") as wait_for_retry,
            mock.patch.object(video_download.importlib.util, "find_spec", return_value=object()),
        ):
            metadata = video_download.inspect_video_url("https://youtu.be/demo")

        self.assertEqual(metadata.title, "Recovered clip")
        self.assertEqual(youtube_dl.call_count, 2)
        self.assertNotIn("impersonate", youtube_dl.call_args_list[0].args[0])
        self.assertEqual(youtube_dl.call_args_list[1].args[0]["impersonate"], "chrome")
        wait_for_retry.assert_called_once()

    def test_access_errors_are_not_hidden_by_network_words_in_message(self):
        error = RuntimeError(
            "ERROR: Video unavailable. Sign in to confirm this private video is yours; try again"
        )

        self.assertFalse(video_download._is_retryable_download_error(error, "YouTube"))

    def test_operating_system_network_errors_are_retryable(self):
        self.assertTrue(
            video_download._is_retryable_download_error(
                ConnectionResetError("socket closed"),
                "Vimeo",
            )
        )

    def test_ffprobe_postprocessing_failures_are_retried(self):
        error = RuntimeError("Postprocessing: WARNING: unable to obtain file audio codec with ffprobe")
        self.assertTrue(video_download._is_retryable_download_error(error, "TikTok"))

    def test_downloader_error_text_removes_ansi_escape_sequences(self):
        self.assertEqual(
            video_download._friendly_error(RuntimeError("\x1b[0;31mERROR:\x1b[0m Link unavailable")),
            "Link unavailable",
        )

    def test_download_reports_progress_and_returns_project_staging_file(self):
        class FakeDownloader:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download):
                self.assert_download(download)
                workspace = os.path.dirname(self.options["outtmpl"])
                output = os.path.join(workspace, "clip.mp4")
                Path(output).write_bytes(b"video")
                for hook in self.options["progress_hooks"]:
                    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
                    hook({"status": "finished"})
                return {"filepath": output, "title": "clip", "ext": "mp4"}

            @staticmethod
            def assert_download(download):
                if download is not True:
                    raise AssertionError("download=True was not used")

            @staticmethod
            def prepare_filename(info):
                return info["filepath"]

        metadata = video_download.VideoMetadata(
            url="https://youtu.be/demo",
            title="Demo",
            platform="YouTube",
            duration_seconds=10,
            thumbnail_url="",
            uploader="",
        )
        progress = []
        with tempfile.TemporaryDirectory() as workspace:
            with (
                mock.patch("yt_dlp.YoutubeDL", FakeDownloader),
                mock.patch.object(
                    video_download, "get_media_stream_types", return_value={"video", "audio"}
                ),
            ):
                path = video_download.download_video(
                    metadata,
                    workspace,
                    lambda value, detail: progress.append((value, detail)),
                    threading.Event(),
                )
            self.assertTrue(Path(path).is_file())
            self.assertTrue(Path(path).is_relative_to(Path(workspace)))

        self.assertEqual(progress[-1], (100, "Download complete"))
        self.assertTrue(any(value == 50 for value, _detail in progress))

    def test_tiktok_download_refreshes_a_stale_format_automatically(self):
        first_downloader = mock.MagicMock()
        first_downloader.__enter__.return_value = first_downloader
        first_downloader.extract_info.side_effect = RuntimeError(
            "ERROR: [TikTok] Requested format is not available"
        )
        second_downloader = mock.MagicMock()
        second_downloader.__enter__.return_value = second_downloader

        with tempfile.TemporaryDirectory() as workspace:
            output = Path(workspace) / "fresh.mp4"
            output.write_bytes(b"video")
            second_downloader.extract_info.return_value = {
                "filepath": str(output), "title": "fresh", "ext": "mp4",
            }
            second_downloader.prepare_filename.return_value = str(output)
            yt_dlp = mock.MagicMock()
            yt_dlp.YoutubeDL.side_effect = [first_downloader, second_downloader]
            progress = []
            metadata = video_download.VideoMetadata(
                url="https://www.tiktok.com/@creator/video/123",
                title="TikTok clip",
                platform="TikTok",
                duration_seconds=10,
                thumbnail_url="",
                uploader="",
            )
            with (
                mock.patch.object(video_download, "_load_yt_dlp", return_value=yt_dlp),
                mock.patch.object(video_download, "_wait_for_retry") as wait_for_retry,
                mock.patch.object(
                    video_download, "get_media_stream_types", return_value={"video", "audio"}
                ),
            ):
                path = video_download.download_video(
                    metadata,
                    workspace,
                    lambda value, detail: progress.append((value, detail)),
                    threading.Event(),
                )

        self.assertEqual(path, str(output))
        self.assertEqual(yt_dlp.YoutubeDL.call_count, 2)
        selector = yt_dlp.YoutubeDL.call_args_list[0].args[0]["format"]
        self.assertIn("acodec!=none", selector)
        wait_for_retry.assert_called_once()
        self.assertIn((0, "Refreshing video stream and retrying"), progress)

    def test_download_rejects_a_video_only_result_before_project_import(self):
        downloader = mock.MagicMock()
        downloader.__enter__.return_value = downloader
        metadata = video_download.VideoMetadata(
            url="https://www.tiktok.com/@creator/video/123",
            title="Video-only clip",
            platform="TikTok",
            duration_seconds=10,
            thumbnail_url="",
            uploader="",
        )

        with tempfile.TemporaryDirectory() as workspace:
            output = Path(workspace) / "video-only.mp4"
            output.write_bytes(b"video")
            downloader.extract_info.return_value = {
                "filepath": str(output), "title": "video-only", "ext": "mp4",
            }
            downloader.prepare_filename.return_value = str(output)
            yt_dlp = mock.MagicMock()
            yt_dlp.YoutubeDL.return_value = downloader
            with (
                mock.patch.object(video_download, "_load_yt_dlp", return_value=yt_dlp),
                mock.patch.object(video_download, "get_media_stream_types", return_value={"video"}),
                self.assertRaisesRegex(RuntimeError, "does not contain an audio track"),
            ):
                video_download.download_video(metadata, workspace)

    def test_cancelled_download_stops_before_network_work(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(video_download.DownloadCancelled):
            video_download.inspect_video_url("https://youtu.be/demo", event)

    def test_audio_download_uses_shared_retry_and_browser_impersonation(self):
        first = mock.MagicMock()
        first.__enter__.return_value = first
        first.extract_info.side_effect = RuntimeError("ERROR: HTTP Error 403: Forbidden")
        second = mock.MagicMock()
        second.__enter__.return_value = second
        yt_dlp = mock.MagicMock()
        yt_dlp.YoutubeDL.side_effect = [first, second]

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.m4a"
            source = Path(directory) / "sample.source.webm"

            def finish(_url, download):
                self.assertTrue(download)
                source.write_bytes(b"downloaded audio")
                return {"filepath": str(source)}

            def normalize(_source, target, _cancel_event):
                self.assertEqual(_source, source)
                target.write_bytes(b"normalized audio")

            second.extract_info.side_effect = finish
            with (
                mock.patch.object(video_download, "_load_yt_dlp", return_value=yt_dlp),
                mock.patch.object(video_download, "_wait_for_retry") as wait_for_retry,
                mock.patch.object(video_download.importlib.util, "find_spec", return_value=object()),
                mock.patch.object(video_download, "_normalize_downloaded_audio", side_effect=normalize),
            ):
                result = video_download.download_audio("https://youtu.be/demo", destination)

        self.assertEqual(result, str(destination))
        self.assertEqual(yt_dlp.YoutubeDL.call_count, 2)
        self.assertNotIn("impersonate", yt_dlp.YoutubeDL.call_args_list[0].args[0])
        self.assertEqual(yt_dlp.YoutubeDL.call_args_list[1].args[0]["impersonate"], "chrome")
        self.assertNotIn("postprocessors", yt_dlp.YoutubeDL.call_args_list[1].args[0])
        wait_for_retry.assert_called_once()

    def test_failed_audio_download_removes_temporary_source_file(self):
        downloader = mock.MagicMock()
        downloader.__enter__.return_value = downloader
        yt_dlp = mock.MagicMock()
        yt_dlp.YoutubeDL.return_value = downloader

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.m4a"
            source = Path(directory) / "sample.source.webm"

            def fail(_url, download):
                self.assertTrue(download)
                source.write_bytes(b"partial source")
                raise RuntimeError("unsupported url")

            downloader.extract_info.side_effect = fail
            with (
                mock.patch.object(video_download, "_load_yt_dlp", return_value=yt_dlp),
                self.assertRaisesRegex(RuntimeError, "unsupported url"),
            ):
                video_download.download_audio("https://youtu.be/demo", destination)

            self.assertFalse(source.exists())
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
