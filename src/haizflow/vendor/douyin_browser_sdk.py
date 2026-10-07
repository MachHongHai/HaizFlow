"""Owned-browser SDK capture adapted from Evil0ctal's Cloak backend.

Source: Evil0ctal/Douyin_TikTok_Download_API, commit
4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2, docker/browser_rpc/backends/cloak.py.
Copyright 2021-2026 Evil0ctal and contributors. Apache-2.0.
Modified by HaizFlow 2026-10-08: Douyin-only matching, exact signed URL returned,
no RPC, no personal browser, no network request from the signing probe.
See licenses/DOUYIN-CHANNEL-IMPORT-NOTICE.md and licenses/Apache-2.0.txt.
"""

FINGERPRINT_READ = """() => ({userAgent: navigator.userAgent, platform: navigator.platform,
 width: screen.width, height: screen.height, language: navigator.language,
 cores: navigator.hardwareConcurrency, memory: navigator.deviceMemory})"""

CAPTURE_INIT_SCRIPT = """(() => {
  const nativeFetch = window.fetch;
  const nativeOpen = XMLHttpRequest.prototype.open;
  const state = {active: false, target: null, query: null, url: null};
  window.__haizflowDouyinSign = state;
  function captures(input) {
    if (!state.active) return false;
    let url;
    try { url = new URL(input, location.href); } catch (_) { return false; }
    if (url.origin !== 'https://www.douyin.com' || url.pathname !== state.target) return false;
    for (const [key, value] of Object.entries(state.query || {})) {
      if (url.searchParams.get(key) !== value) return false;
    }
    state.url = url.href;
    return true;
  }
  window.fetch = function(input) {
    const url = typeof input === 'string' || input instanceof URL ? String(input) : input && input.url;
    if (captures(url)) return Promise.reject(new DOMException('haizflow-sign', 'AbortError'));
    return nativeFetch.apply(this, arguments);
  };
  XMLHttpRequest.prototype.open = function(method, url) {
    if (captures(url)) throw new DOMException('haizflow-sign', 'AbortError');
    return nativeOpen.apply(this, arguments);
  };
})();"""

SIGN_SCRIPT = """async input => {
  const state = window.__haizflowDouyinSign;
  if (!state || state.active) return null;
  state.target = new URL(input.url).pathname;
  state.query = input.match;
  state.url = null;
  state.active = true;
  try { await window.fetch(input.url, {method: 'GET'}); } catch (_) {}
  finally { state.active = false; }
  return state.url;
}"""
