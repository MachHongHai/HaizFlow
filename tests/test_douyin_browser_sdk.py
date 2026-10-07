"""Run the actual capture shim against a deterministic fake page SDK in Node."""
import shutil
import subprocess

import pytest

from haizflow.vendor.douyin_browser_sdk import CAPTURE_INIT_SCRIPT, SIGN_SCRIPT


def test_capture_preserves_sdk_bytes_and_never_sends_probe_to_network():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is only required for the optional browser-shim regression test")
    setup = """
    const assert = require('node:assert/strict');
    const sent = [];
    global.window = global;
    global.location = {href: 'https://www.douyin.com/', origin: 'https://www.douyin.com'};
    global.XMLHttpRequest = function() {};
    XMLHttpRequest.prototype.open = function(method, url) { sent.push(url); };
    window.fetch = async function(url) { sent.push(String(url)); return {ok: true}; };
    """
    finish = """
    const belowSDK = window.fetch;
    window.fetch = async function(url, init) {
      // Simulate unrelated page background traffic while the SDK handles a probe.
      await belowSDK('https://www.douyin.com/background');
      return belowSDK(url + '&msToken=sealed%2B%2F&a_bogus=a%2Bb&uifid=visitor&timestamp=1&x-secsdk-web-signature=sig', init);
    };
    const input = {url: 'https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=42', match: {aweme_id: '42'}};
    (async () => {
      const signed = await sign(input);
      assert.equal(signed, input.url + '&msToken=sealed%2B%2F&a_bogus=a%2Bb&uifid=visitor&timestamp=1&x-secsdk-web-signature=sig');
      assert.deepEqual(sent, ['https://www.douyin.com/background']);
      assert.equal(window.__haizflowDouyinSign.active, false);
      // Both fetch and XHR are captured only for the selected endpoint and ID.
      const state = window.__haizflowDouyinSign;
      state.active = true;
      await belowSDK('https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=43');
      const xhr = new XMLHttpRequest();
      assert.throws(() => xhr.open('GET', input.url), {name: 'AbortError'});
      state.active = false;
      assert.equal(sent.length, 2);
      console.log('capture-ok');
    })().catch(() => process.exit(1));
    """
    script = setup + CAPTURE_INIT_SCRIPT + "\nconst sign = " + SIGN_SCRIPT + ";\n" + finish
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "capture-ok"
