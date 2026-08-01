import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services.tiktok_studio import (
    _CdpClient,
    _caption_editor_expression,
    _caption_fill_expression,
    _read_debug_port,
    _select_matching_hashtag_suggestion,
    _split_caption_and_hashtags,
    _type_caption_with_cdp,
    _wait_and_fill_caption,
)


class _Socket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    def send(self, value):
        self.sent.append(json.loads(value))

    def recv(self, timeout=None):
        del timeout
        return json.dumps(self.messages.pop(0))


class _CaptionClient:
    def __init__(self):
        self.calls = []
        self.value = ""
        self.fresh_reads = 0
        self.confirmed_hashtags = []

    def call(self, method, params=None, timeout=5.0):
        del timeout
        params = params or {}
        self.calls.append((method, params))
        function = params.get("functionDeclaration", "")
        if method == "Runtime.callFunctionOn" and "focused: document.activeElement" in function:
            return {"result": {"value": {"focused": True, "contentEditable": True}}}
        if method == "Input.dispatchKeyEvent" and params.get("key") == "Backspace" and params.get("type") == "rawKeyDown":
            self.value = ""
        if method == "Input.insertText":
            self.value += params["text"]
            return {}
        if method == "Runtime.evaluate" and "const wanted" in params.get("expression", ""):
            if "querySelectorAll('[role=\"option\"]')" in params["expression"]:
                return {"result": {"value": {"x": 100, "y": 200}}}
            if "mentionText" in params["expression"]:
                return {"result": {"value": bool(self.confirmed_hashtags)}}
        if method == "Input.dispatchMouseEvent" and params.get("type") == "mouseReleased":
            self.confirmed_hashtags.append(True)
            if self.value and not self.value.endswith(" "):
                self.value += " "
            return {}
        if method == "Runtime.evaluate" and "const element" in params.get("expression", ""):
            self.fresh_reads += 1
            # Draft.js replaces the edited node asynchronously. Simulate the
            # new node being unavailable briefly before it exposes the value.
            value = None if self.fresh_reads < 3 else self.value
            return {"result": {"value": value}}
        return {"result": {"value": True}}


class _CaptionLocatorClient:
    def call(self, method, params=None, timeout=5.0):
        del method, params, timeout
        return {"result": {"objectId": "current-editor"}}


class TikTokStudioTests(unittest.TestCase):
    def test_cdp_client_ignores_events_and_returns_matching_response(self):
        socket = _Socket(
            [
                {"method": "Page.loadEventFired", "params": {}},
                {"id": 1, "result": {"value": True}},
            ]
        )

        result = _CdpClient(socket).call("Runtime.evaluate", {"expression": "true"})

        self.assertEqual(result, {"value": True})
        self.assertEqual(socket.sent[0]["method"], "Runtime.evaluate")

    def test_caption_expression_preserves_quotes_and_unicode_as_data(self):
        expression = _caption_fill_expression('Hải nói: "xin chào"')

        self.assertIn('const text = "Hải nói: \\"xin chào\\"";', expression)
        self.assertIn("InputEvent('input'", expression)

    def test_caption_editor_locator_prioritizes_tiktok_and_rich_text_editors(self):
        expression = _caption_editor_expression()

        self.assertIn('data-e2e*="caption"', expression)
        self.assertIn("ProseMirror", expression)
        self.assertIn("contenteditable", expression)
        self.assertIn("box.height >= 16", expression)
        self.assertNotIn("box.height >= 24", expression)

    def test_draftjs_caption_uses_native_replace_sequence_only_once(self):
        client = _CaptionClient()

        with patch("haizflow.services.tiktok_studio.time.sleep"):
            self.assertTrue(_type_caption_with_cdp(client, "editor-object", "Caption\n#video #fyp"))

        key_calls = [
            params
            for method, params in client.calls
            if method == "Input.dispatchKeyEvent"
        ]
        insert_calls = [params for method, params in client.calls if method == "Input.insertText"]
        mouse_releases = [params for method, params in client.calls if method == "Input.dispatchMouseEvent" and params["type"] == "mouseReleased"]
        self.assertEqual([call["key"] for call in key_calls], ["a", "a", "Backspace", "Backspace"])
        self.assertEqual(insert_calls, [{"text": "Caption\n#video #fyp"}])
        self.assertEqual(len(mouse_releases), 1)
        self.assertEqual(client.fresh_reads, 8)

    def test_caption_suffix_is_split_without_touching_caption_hashtags(self):
        self.assertEqual(
            _split_caption_and_hashtags("Caption #inside\n#video #fyp"),
            ("Caption #inside", ["#video", "#fyp"]),
        )
        self.assertEqual(_split_caption_and_hashtags("Caption only"), ("Caption only", []))

    def test_hashtag_picker_requires_exact_visible_topic_and_clicks_it(self):
        client = _CaptionClient()

        with patch("haizflow.services.tiktok_studio.time.sleep"):
            self.assertTrue(_select_matching_hashtag_suggestion(client, "#video", timeout_seconds=1.0))

        expressions = [
            params["expression"]
            for method, params in client.calls
            if method == "Runtime.evaluate" and "const wanted" in params.get("expression", "")
        ]
        self.assertIn("[role=\"option\"]", expressions[0])
        self.assertIn(".hash-tag-topic", expressions[0])

    def test_tiktok_editor_reset_retries_with_a_fresh_replacement(self):
        client = _CaptionLocatorClient()
        cancel = threading.Event()

        with (
            patch("haizflow.services.tiktok_studio._type_caption_with_cdp", side_effect=[False, True]) as insert,
            patch("haizflow.services.tiktok_studio.time.sleep"),
        ):
            result = _wait_and_fill_caption(client, "Caption\n#video", time.monotonic() + 5.0, cancel)

        self.assertTrue(result)
        self.assertEqual(insert.call_count, 2)
        insert.assert_called_with(client, "current-editor", "Caption\n#video")

    def test_debug_port_is_read_only_from_the_managed_browser_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DevToolsActivePort"
            path.write_text("49152\n/devtools/browser/id\n", encoding="utf-8")

            self.assertEqual(_read_debug_port(directory), 49152)


if __name__ == "__main__":
    unittest.main()
