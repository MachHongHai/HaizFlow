import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from haizflow.services import gemini_translation, translation
from haizflow.services.resource_packs import ResourcePackManager


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return json.dumps(self.payload).encode("utf-8")


class GeminiTranslationTests(unittest.TestCase):
    def test_batch_start_is_logged_before_waiting_for_api_response(self):
        events = []

        def send_chunk(chunk, **_kwargs):
            self.assertEqual(events[0][0], "log")
            self.assertIn("Sending Gemini translation batch", events[0][1])
            self.assertEqual(events[1], ("progress", 0))
            events.append(("request", len(chunk)))
            return ["Xin chào" for _ in chunk]

        with (
            patch.object(gemini_translation, "active_key", return_value="fixture-key"),
            patch.object(gemini_translation, "check_cancellation"),
            patch.object(gemini_translation, "log_to_video", side_effect=lambda _id, text, **_: events.append(("log", text))),
            patch.object(gemini_translation, "_request_chunk", side_effect=send_chunk),
        ):
            result = gemini_translation.translate_texts(
                ["Hello"], model="gemini-3.1-flash-lite", source_language="English",
                target_language="Vietnamese", video_id="fixture",
                progress_callback=lambda done, _total, _detail: events.append(("progress", done)),
            )
        self.assertEqual(result, ["Xin chào"])
        self.assertEqual(events[-1], ("progress", 1))

    def test_named_keys_select_active_without_exposing_secrets(self):
        credentials = {}
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(gemini_translation, "_KEYS_PATH", Path(directory) / "keys.json"),
                patch.object(gemini_translation.secure_credentials, "write_secret", side_effect=lambda target, value, **_: credentials.__setitem__(target, value)),
                patch.object(gemini_translation.secure_credentials, "read_secret", side_effect=lambda target: credentials.get(target, "")),
                patch.object(gemini_translation.secure_credentials, "delete_secret", side_effect=lambda target: credentials.pop(target, None) is not None),
            ):
                first = gemini_translation.add_named_key("Cá nhân", "first-secret")
                second = gemini_translation.add_named_key("Công việc", "second-secret")
                self.assertEqual(gemini_translation.active_key(), "second-secret")
                self.assertEqual([row["active"] for row in gemini_translation.list_keys()], [False, True])
                self.assertNotIn("first-secret", (Path(directory) / "keys.json").read_text(encoding="utf-8"))
                self.assertNotIn("second-secret", str(gemini_translation.list_keys()))
                gemini_translation.select_key(first)
                self.assertEqual(gemini_translation.active_key(), "first-secret")
                self.assertTrue(gemini_translation.remove_key(first))
                self.assertEqual(gemini_translation.active_key(), "second-secret")
                self.assertEqual(gemini_translation.list_keys()[0]["id"], second)

    def test_existing_single_key_remains_usable_after_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(gemini_translation, "_KEYS_PATH", Path(directory) / "keys.json"),
                patch.object(gemini_translation.secure_credentials, "read_secret", return_value="existing-secret"),
            ):
                self.assertTrue(gemini_translation.key_configured())
                self.assertEqual(gemini_translation.list_keys(), [{
                    "id": "legacy", "label": "Key mặc định", "active": True,
                }])

    def test_cheaper_stable_flash_lite_model_is_available(self):
        self.assertIn("gemini-3.1-flash-lite", gemini_translation.MODELS)
        self.assertNotIn("gemini-2.5-flash-lite", gemini_translation.MODELS)

    def test_api_translation_needs_no_hymt2_resource_pack(self):
        manager = ResourcePackManager()
        self.assertEqual(
            manager.required_packs("translation", {"translation_model": "gemini-3.5-flash-lite"}),
            [],
        )

    def test_compact_batches_keep_order_and_use_low_thinking(self):
        requests = []

        def fake_open(outgoing, timeout):
            self.assertEqual(timeout, 90)
            self.assertEqual(outgoing.get_header("X-goog-api-key"), "secret-test-key")
            payload = json.loads(outgoing.data)
            self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "minimal")
            self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
            entries = json.loads(payload["contents"][0]["parts"][0]["text"])
            requests.append(entries)
            return _Response({"candidates": [{"content": {"parts": [{"text": json.dumps({
                "translations": [{"id": row["id"], "text": "VI " + row["text"]} for row in entries]
            })}]}}]})

        texts = [f"Sentence {index}" for index in range(50)]
        with (
            patch.object(gemini_translation.secure_credentials, "read_secret", return_value="secret-test-key"),
            patch.object(gemini_translation.request, "urlopen", side_effect=fake_open),
            patch.object(gemini_translation, "check_cancellation"),
        ):
            result = gemini_translation.translate_texts(
                texts, model="gemini-3.5-flash-lite", source_language="English",
                target_language="Vietnamese", video_id="test",
            )
        self.assertEqual(result, ["VI " + text for text in texts])
        self.assertEqual([len(chunk) for chunk in requests], [24, 24, 2])
        self.assertNotIn("secret-test-key", json.dumps(requests))

    def test_missing_key_does_not_send_any_request(self):
        with (
            patch.object(gemini_translation.secure_credentials, "read_secret", return_value=""),
            patch.object(gemini_translation.request, "urlopen") as urlopen,
        ):
            with self.assertRaisesRegex(RuntimeError, "Quản lý API Key"):
                gemini_translation.translate_texts(
                    ["Hello"], model="gemini-3.5-flash-lite",
                    source_language="English", target_language="Vietnamese", video_id="test",
                )
            urlopen.assert_not_called()

    def test_incomplete_response_is_rejected_without_publishing_output(self):
        response = {"candidates": [{"content": {"parts": [{"text": '{"translations":[]}' }]}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            output = root / "translated.json"
            source.write_text(json.dumps([{"start": 0, "end": 1, "text": "Hello"}]), encoding="utf-8")
            output.write_text("old result", encoding="utf-8")
            with (
                patch.object(gemini_translation.secure_credentials, "read_secret", return_value="secret-test-key"),
                patch.object(gemini_translation.request, "urlopen", return_value=_Response(response)),
                patch.object(gemini_translation, "check_cancellation"),
                patch.object(translation, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "thiếu câu dịch"):
                    translation.translate_segments(
                        str(source), str(output), "test", provider="gemini",
                        translation_model="gemini-3.5-flash-lite",
                    )
            self.assertEqual(output.read_text(encoding="utf-8"), "old result")

    def test_auth_error_does_not_retry_or_echo_key(self):
        error = HTTPError("https://generativelanguage.googleapis.com", 403, "Forbidden", {}, None)
        with patch.object(gemini_translation.request, "urlopen", side_effect=error) as urlopen:
            with self.assertRaisesRegex(RuntimeError, "API key") as caught:
                gemini_translation._request_chunk(
                    [(0, "Hello")], key="secret-test-key", model="gemini-3.8-flash",
                    source_language="English", target_language="Vietnamese",
                )
            self.assertEqual(urlopen.call_count, 1)
            self.assertNotIn("secret-test-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
