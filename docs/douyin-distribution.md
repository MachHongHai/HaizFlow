# Douyin distribution decision

Review date: 2026-10-08. Published terms, not a legal opinion or an OEM grant.

| Component | Evidence | Decision |
| --- | --- | --- |
| Adapted Evil0ctal signing/capture | [Pinned Apache-2.0 source](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/LICENSE) | Source distribution with license, attribution and modification notice; see `DOUYIN-CHANNEL-IMPORT-NOTICE.md` |
| CloakBrowser wrapper 0.5.10 | [MIT](https://github.com/CloakHQ/cloakbrowser/blob/v0.5.10/LICENSE) | Optional dependency; preserve `licenses/CloakBrowser-MIT.txt` |
| Playwright 1.58.0 | [Apache-2.0](https://github.com/microsoft/playwright/blob/v1.58.0/LICENSE) | Preserve its license/notice if packaged |
| Cloak Chromium 146.0.7680.177.5 | [Binary License v1.3](https://github.com/CloakHQ/cloakbrowser/blob/v0.5.10/BINARY-LICENSE.md) | Local development cache only; no binary upload/bundling |

## Binary rights are separate

Free/older binaries remain restricted. Ordinary subscriptions do not grant
redistribution rights. Dependency listing is permitted when users obtain the
binary directly from official channels; this does not grant binary bundling.
The same terms require OEM rights for customer-facing browser functionality/control.

Our assessment: HaizFlow's Create/Refresh session controls require written
CloakHQ clarification or suitable OEM permission before customer delivery.
Do not assume dependency listing resolves that integration question.
No such permission has been supplied to this project.

## Next release decision

Seek written scope confirmation from `info@cloakbrowser.dev`, or replace this
backend with a suitably licensed alternative and revalidate compatibility.
No provider contact, backend replacement, build or release is performed here.

Source-only commit/push retains notices and excludes binaries, cookies, profiles,
cache and license credentials. Runtime browser directories are Git-ignored.
Before distribution, retain the applicable permission/evidence and review the
actual component inventory. Video rights and platform terms remain independent.
