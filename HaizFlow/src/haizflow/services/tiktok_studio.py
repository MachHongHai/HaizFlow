"""Local TikTok Studio preparation through Chrome's DevTools Protocol."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class StudioPreparationResult:
    video_attached: bool
    caption_filled: bool
    error: str = ""

    @property
    def ready_for_review(self) -> bool:
        return self.video_attached and self.caption_filled


class _CdpClient:
    def __init__(self, websocket):
        self._websocket = websocket
        self._request_id = 0

    def call(self, method: str, params: dict | None = None, *, timeout: float = 5.0) -> dict:
        self._request_id += 1
        request_id = self._request_id
        self._websocket.send(
            json.dumps(
                {"id": request_id, "method": method, "params": params or {}},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        deadline = time.monotonic() + max(0.1, timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Chrome did not answer {method} in time.")
            message = json.loads(self._websocket.recv(timeout=remaining))
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise RuntimeError(str(message["error"].get("message") or message["error"]))
            return dict(message.get("result") or {})


def prepare_upload(
    user_data_dir: str,
    video_path: str,
    post_text: str,
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float = 120.0,
    progress: ProgressCallback | None = None,
) -> StudioPreparationResult:
    """Attach one video and fill its post text while leaving final publishing to the user."""
    path = os.path.abspath(video_path)
    if not os.path.isfile(path):
        return StudioPreparationResult(False, False, "Video file is unavailable.")

    cancel = cancel_event or threading.Event()
    deadline = time.monotonic() + max(10.0, timeout_seconds)
    _report(progress, "Waiting for TikTok Studio")
    try:
        target = _wait_for_studio_target(user_data_dir, deadline, cancel)
        with connect(
            str(target["webSocketDebuggerUrl"]),
            open_timeout=5,
            close_timeout=1,
            max_size=4 * 1024 * 1024,
        ) as websocket:
            client = _CdpClient(websocket)
            file_input_id = _wait_for_file_input(client, deadline, cancel)
            client.call(
                "DOM.setFileInputFiles",
                {"files": [path], "objectId": file_input_id},
                timeout=10,
            )
            _report(progress, "Video added to TikTok Studio")
            if not post_text.strip():
                return StudioPreparationResult(True, True)
            caption_filled = _wait_and_fill_caption(client, post_text, deadline, cancel)
            if caption_filled:
                _report(progress, "Video and caption are ready for review")
                return StudioPreparationResult(True, True)
            return StudioPreparationResult(
                True,
                False,
                "The video was added, but TikTok did not retain the caption automatically. The text remains on the clipboard.",
            )
    except InterruptedError:
        return StudioPreparationResult(False, False, "TikTok preparation was cancelled.")
    except (ConnectionClosed, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return StudioPreparationResult(False, False, _friendly_error(exc))


def _wait_for_studio_target(user_data_dir: str, deadline: float, cancel: threading.Event) -> dict:
    target_deadline = min(deadline, time.monotonic() + 15.0)
    while time.monotonic() < target_deadline:
        _check_cancelled(cancel)
        port = _read_debug_port(user_data_dir)
        if port:
            try:
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1.0) as response:
                    targets = json.load(response)
                pages = [item for item in targets if item.get("type") == "page" and item.get("webSocketDebuggerUrl")]
                for page in pages:
                    if "tiktok.com" in str(page.get("url") or "").casefold():
                        return page
                if len(pages) == 1:
                    return pages[0]
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
        cancel.wait(0.25)
    raise TimeoutError(
        "TikTok Studio automation did not start. Close the HaizFlow Chrome window once, then try again."
    )


def _read_debug_port(user_data_dir: str) -> int:
    try:
        first_line = (Path(user_data_dir) / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()[0]
        port = int(first_line)
    except (FileNotFoundError, IndexError, OSError, TypeError, ValueError):
        return 0
    return port if 0 < port <= 65535 else 0


def _wait_for_file_input(client: _CdpClient, deadline: float, cancel: threading.Event) -> str:
    expression = "document.querySelector('input[type=file]')"
    while time.monotonic() < deadline:
        _check_cancelled(cancel)
        try:
            result = client.call(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": False},
                timeout=3,
            )
            remote = dict(result.get("result") or {})
            if remote.get("objectId"):
                return str(remote["objectId"])
        except (RuntimeError, TimeoutError):
            pass
        cancel.wait(0.25)
    raise TimeoutError("TikTok Studio did not expose its video upload control in time.")


def _wait_and_fill_caption(
    client: _CdpClient,
    post_text: str,
    deadline: float,
    cancel: threading.Event,
) -> bool:
    attempts = 0
    settle_until = 0.0
    while time.monotonic() < deadline:
        _check_cancelled(cancel)
        try:
            result = client.call(
                "Runtime.evaluate",
                {
                    "expression": _caption_editor_expression(),
                    "returnByValue": False,
                },
                timeout=3,
            )
            remote = dict(result.get("result") or {})
            object_id = str(remote.get("objectId") or "")
            if object_id:
                if settle_until <= 0.0:
                    # TikTok mounts the editor before the upload form has
                    # finished initializing. Typing immediately can be erased
                    # by its next Draft.js state update.
                    settle_until = time.monotonic() + 0.8
                if time.monotonic() < settle_until:
                    cancel.wait(min(0.2, max(0.0, settle_until - time.monotonic())))
                    continue

                attempts += 1
                if _type_caption_with_cdp(client, object_id, post_text):
                    return True
                if attempts >= 3:
                    return False
                # A failed verification means TikTok reset or rejected the
                # value. Re-query the current node and replace its whole value;
                # never append to the stale Draft.js node.
                cancel.wait(0.6)
        except (RuntimeError, TimeoutError):
            if attempts >= 3:
                return False
        cancel.wait(0.35)
    return False


def _type_caption_with_cdp(client: _CdpClient, object_id: str, post_text: str) -> bool:
    """Type into TikTok's controlled editor so its framework receives real edit events."""
    focused = client.call(
        "Runtime.callFunctionOn",
        {
            "objectId": object_id,
            "functionDeclaration": """function() {
                this.focus();
                if (!this.isContentEditable && typeof this.select === 'function') {
                    this.select();
                }
                return { focused: document.activeElement === this, contentEditable: this.isContentEditable };
            }""",
            "returnByValue": True,
        },
        timeout=3,
    )
    focus_state = dict((focused.get("result") or {}).get("value") or {})
    if not focus_state.get("focused"):
        return False
    content_editable = bool(focus_state.get("contentEditable"))
    if content_editable:
        # Draft.js owns its selection and content state. A DOM Range combined
        # with execCommand can duplicate hashtags or discard the caption when
        # Draft.js reconciles. Use the same native edit sequence as a user:
        # select all, delete, then type exactly once through CDP.
        _dispatch_editor_key(client, "keyDown", "a", "KeyA", 65, modifiers=2)
        _dispatch_editor_key(client, "keyUp", "a", "KeyA", 65, modifiers=2)
        _dispatch_editor_key(client, "rawKeyDown", "Backspace", "Backspace", 8)
        _dispatch_editor_key(client, "keyUp", "Backspace", "Backspace", 8)
        client.call("Input.insertText", {"text": post_text}, timeout=10)
    else:
        client.call("Input.insertText", {"text": post_text}, timeout=10)
        client.call(
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": """function() {
                    this.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
            },
            timeout=3,
        )

    if not _wait_for_fresh_caption_value(
        client,
        post_text,
        timeout_seconds=2.5,
        stable_samples=4,
    ):
        return False

    if content_editable:
        _caption, hashtags = _split_caption_and_hashtags(post_text)
        if hashtags:
            # TikTok leaves the final typed hashtag as plain text until its
            # matching suggestion is chosen. Select the first exact match so
            # Draft.js converts it into a real mention entity.
            if not _select_matching_hashtag_suggestion(client, hashtags[-1], timeout_seconds=3.0):
                return False
            return _wait_for_fresh_caption_value(
                client,
                post_text,
                timeout_seconds=1.5,
                stable_samples=2,
            )
    return True


def _split_caption_and_hashtags(post_text: str) -> tuple[str, list[str]]:
    """Split the normalized hashtag suffix produced by compose_post_text."""
    text = str(post_text or "").strip()
    if not text:
        return "", []
    head, separator, tail = text.rpartition("\n")
    candidate = tail if separator else text
    tokens = candidate.split()
    if not tokens or any(re.fullmatch(r"#[^\s#]+", token) is None for token in tokens):
        return text, []
    return (head if separator else ""), tokens


def _select_matching_hashtag_suggestion(
    client: _CdpClient,
    hashtag: str,
    *,
    timeout_seconds: float,
) -> bool:
    """Click TikTok's first visible exact-match hashtag suggestion."""
    wanted = str(hashtag or "").strip().casefold()
    if not wanted:
        return False
    encoded = json.dumps(wanted, ensure_ascii=False)
    expression = f"""
(() => {{
    const wanted = {encoded};
    const visible = element => {{
        const box = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return box.width > 0 && box.height > 0
            && style.visibility !== 'hidden' && style.display !== 'none';
    }};
    const option = Array.from(document.querySelectorAll('[role="option"]'))
        .filter(visible)
        .find(candidate => {{
            const topic = candidate.querySelector('.hash-tag-topic') || candidate;
            return (topic.textContent || '').trim().toLocaleLowerCase() === wanted;
        }});
    if (!option) return null;
    const box = option.getBoundingClientRect();
    return {{ x: box.x + box.width / 2, y: box.y + box.height / 2 }};
}})()
""".strip()
    deadline = time.monotonic() + max(0.5, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            result = client.call(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                timeout=3,
            )
            point = (result.get("result") or {}).get("value")
            if isinstance(point, dict) and point.get("x") is not None and point.get("y") is not None:
                x = float(point["x"])
                y = float(point["y"])
                client.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, timeout=3)
                client.call(
                    "Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
                    timeout=3,
                )
                client.call(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
                    timeout=3,
                )
                return _wait_for_confirmed_hashtag(client, hashtag, timeout_seconds=1.5)
        except (RuntimeError, TimeoutError, TypeError, ValueError):
            pass
        time.sleep(0.15)
    return False


def _wait_for_confirmed_hashtag(
    client: _CdpClient,
    hashtag: str,
    *,
    timeout_seconds: float,
) -> bool:
    encoded = json.dumps(str(hashtag or "").strip().casefold(), ensure_ascii=False)
    expression = f"""
(() => {{
    const editor = {_caption_editor_expression()};
    if (!editor) return false;
    const wanted = {encoded};
    return Array.from(editor.querySelectorAll('[data-testid="mentionText"], .mention'))
        .some(element => (element.textContent || '').trim().toLocaleLowerCase() === wanted);
}})()
""".strip()
    deadline = time.monotonic() + max(0.5, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            result = client.call(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                timeout=3,
            )
            if bool((result.get("result") or {}).get("value")):
                return True
        except (RuntimeError, TimeoutError):
            pass
        time.sleep(0.15)
    return False


def _dispatch_editor_key(
    client: _CdpClient,
    event_type: str,
    key: str,
    code: str,
    virtual_key: int,
    *,
    modifiers: int = 0,
) -> None:
    client.call(
        "Input.dispatchKeyEvent",
        {
            "type": event_type,
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": virtual_key,
            "nativeVirtualKeyCode": virtual_key,
            "modifiers": modifiers,
        },
        timeout=3,
    )


def _wait_for_fresh_caption_value(
    client: _CdpClient,
    post_text: str,
    *,
    timeout_seconds: float,
    stable_samples: int = 1,
) -> bool:
    """Verify through the current DOM node because Draft.js replaces the edited node."""
    deadline = time.monotonic() + max(0.5, timeout_seconds)
    consecutive_matches = 0
    required_matches = max(1, int(stable_samples))
    expression = f"""
(() => {{
    const element = {_caption_editor_expression()};
    if (!element) return null;
    return element.isContentEditable
        ? (element.innerText || element.textContent || '')
        : (element.value || '');
}})()
""".strip()
    while time.monotonic() < deadline:
        try:
            result = client.call(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                timeout=3,
            )
            current = (result.get("result") or {}).get("value")
            if current is not None and _same_editor_text(str(current), post_text):
                consecutive_matches += 1
                if consecutive_matches >= required_matches:
                    return True
            else:
                consecutive_matches = 0
        except (RuntimeError, TimeoutError):
            consecutive_matches = 0
        time.sleep(0.2)
    return False


def _same_editor_text(actual: str, expected: str) -> bool:
    def normalized(value: str) -> str:
        return " ".join(str(value or "").replace("\u200b", "").split())

    return bool(normalized(expected)) and normalized(actual) == normalized(expected)


def _caption_editor_expression() -> str:
    return r"""
(() => {
    const visible = element => {
        const box = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        // Draft.js renders TikTok's one-line description editor at about 21 px high.
        return box.width >= 180 && box.height >= 16 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const explicitSelectors = [
        '[data-e2e*="caption" i] [contenteditable="true"]',
        '[data-testid*="caption" i] [contenteditable="true"]',
        '[aria-label*="caption" i]',
        '[placeholder*="caption" i]',
        '.public-DraftEditor-content[contenteditable="true"]',
        '.ProseMirror[contenteditable="true"]'
    ];
    const explicit = explicitSelectors
        .map(selector => document.querySelector(selector))
        .find(element => element && visible(element));
    if (explicit) return explicit;

    const positive = /caption|description|describe|post text|chú thích|mô tả|nội dung/i;
    const negative = /search|filter|title|location|url|link|tìm kiếm|bộ lọc/i;
    const candidates = Array.from(document.querySelectorAll(
        'textarea, input[type="text"], [contenteditable="true"], [role="textbox"]'
    )).filter(visible).map(element => {
        const parentText = (element.parentElement && element.parentElement.innerText || '').slice(0, 180);
        const attributes = [
            element.getAttribute('aria-label'),
            element.getAttribute('placeholder'),
            element.getAttribute('name'),
            element.getAttribute('id'),
            element.getAttribute('data-e2e'),
            element.getAttribute('data-testid'),
            element.className,
            parentText
        ].filter(Boolean).join(' ');
        let score = positive.test(attributes) ? 20 : 0;
        if (negative.test(attributes)) score -= 20;
        if (element.isContentEditable) score += 6;
        if (element.tagName === 'TEXTAREA') score += 4;
        if ((element.maxLength || 0) >= 200) score += 3;
        score += Math.min(3, Math.floor(element.getBoundingClientRect().width / 300));
        return { element, score };
    }).sort((left, right) => right.score - left.score);
    return candidates.length && candidates[0].score >= 5 ? candidates[0].element : null;
})()
""".strip()


def _caption_fill_expression(post_text: str) -> str:
    encoded = json.dumps(str(post_text or ""), ensure_ascii=False)
    return f"""
(() => {{
    const text = {encoded};
    const element = {_caption_editor_expression()};
    if (!element) return false;
    element.focus();
    if (element.isContentEditable) {{
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(element);
        selection.removeAllRanges();
        selection.addRange(range);
        if (!document.execCommand('insertText', false, text)) {{
            element.replaceChildren(document.createTextNode(text));
            element.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: text }}));
        }}
    }} else {{
        const prototype = element.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
        setter.call(element, text);
        element.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: text }}));
        element.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }}
    return element.isContentEditable ? element.innerText === text : element.value === text;
}})()
""".strip()


def _friendly_error(error: Exception) -> str:
    message = str(error).strip()
    return message or "TikTok Studio could not be prepared automatically."


def _check_cancelled(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise InterruptedError


def _report(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)
