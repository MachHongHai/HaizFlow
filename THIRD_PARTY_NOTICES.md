# Third-party components

This repository inventory is not a substitute for the version-specific
`THIRD_PARTY_NOTICES.md` generated inside each release. The existing generator
copies license texts from the exact locked environment and curated `licenses/`.
HaizFlow's source license does not replace any component's independent terms.

| Component | Delivery | Evidence and required review |
| --- | --- | --- |
| PySide6 6.11.1 / Qt / Shiboken | Core DLLs and Python bindings | Installed wheel metadata declares LGPL-3.0-only or GPL alternatives. Select a valid path, audit actual Qt modules, retain notices and corresponding source, prove replacement/relinking and required debugging rights. No Qt commercial license is evidenced. |
| FFmpeg / FFprobe 8.1.2 HaizFlow CLI build | Core, separate executables | GPL/version3 CLI with dynamically linked libass/x264/Rubber Band/libmp3lame. Exact native DLL/source closure, PKGBUILDs and build evidence are collected separately. [GPL build notice](licenses/FFmpeg-NOTICE.md). |
| FFmpeg 7.1.3 / zlib 1.3.1 | Qt Multimedia shared backend | LGPL backend from the Qt 6.11.1 wheel, without GPL encoders. Exact upstream source and reported MSVC configuration are retained separately from the GPL CLI. |
| FFmpeg 8.1.2 / PyAV 18.1.0 | CPU/CUDA engine shared backend | LGPL-only FFmpeg built from unmodified source, with BSD PyAV bindings. Vendor GPL encoder libraries are replaced at packaging time; imported symbols and binding transformations are inventoried and tested. |
| OmniVoice SDK 0.2.1 | Downloaded SDK / AI engine | Apache-2.0; [notice](licenses/OMNIVOICE-NOTICE.md). |
| edge-tts 7.3.1 | Optional online speech client in Core | LGPL-3.0; unmodified upstream client. Retain the exact wheel's license and corresponding source, and verify library replacement for any future frozen release. Microsoft service access and output terms are separate from the client's license. [Integration scope](docs/edge-tts.md). |
| MCP Python SDK / MCP types 2.3.0 | Core, loaded only in the stdio adapter process | Official MCP SDK; exact dependency metadata and license texts are collected by the release notices generator. No agent-specific SDK or hosted MCP service is bundled. [Integration scope](docs/mcp.md). |
| OmniVoice checkpoint | Separate pinned model pack | CC-BY-NC-4.0; commercial workflow and generated bundled preview/sample provenance need clearance. The SDK's Apache terms do not clear the checkpoint. |
| HY-MT2 CPU/GPU | Separate pinned model packs | Apache-2.0 declared at pinned revisions; retain [notice](licenses/HY-MT2-NOTICE.md) and license text. |
| Whisper / WhisperX / faster-whisper / CTranslate2 | Separate model and engine packs | Audit every pinned checkpoint including VAD and alignment models, not just the recognition SDK. Engine inventories must be generated from their own locks. |
| Demucs / audio libraries / OCR | Separate engines and model packs; light audio dependencies in Core | Demucs checkpoint, alignment/VAD and OCR provenance must be documented per pack. Python notices cannot infer checkpoint rights. |
| ONNX Runtime DirectML 1.24.4 | Separate Windows vision engine only | ONNX Runtime MIT license and the exact wheel's `ThirdPartyNotices.txt` are retained by the engine notice collector. Native DirectML 1.15.4 has separate Microsoft binary terms, retained in [binary notice](licenses/ONNX-DIRECTML-NOTICE.md) and full license text. CPU ONNX Runtime in Core and speech engines remains separate. [OCR GPU integration](docs/subtitle-ocr-gpu.md). |
| WeSpeaker VoxCeleb ResNet34 | Checksum-pinned speaker-identification model bundled with Core | Publisher declares Apache-2.0 at the pinned revision; retain [model notice](licenses/WESPEAKER-NOTICE.md) and license text. This is not the separate ResNet34-LM checkpoint. |
| Bangers font | Bundled font | [SIL OFL text](licenses/Bangers-OFL.txt), [copyright notice](licenses/Bangers-NOTICE.md); no HaizFlow ownership claim. |
| Fluent System Icons | Curated bundled SVGs | [Microsoft MIT notice](licenses/FLUENT-SYSTEM-ICONS-NOTICE.md). |
| Douyin native signing | Adapted a_bogus / SM3 / web-signature source; local adapter | [Pinned source, changes and Apache-2.0 notice](licenses/DOUYIN-CHANNEL-IMPORT-NOTICE.md); retain independently. |
| Douyin guest browser | Playwright 1.63.0 driver bundled; unmodified Chromium snapshot 1714059 installed as an optional Resource Pack directly from Google's official upstream, not redistributed by HaizFlow | Playwright Apache-2.0 and original driver notices; Chromium base BSD reference is not complete third-party closure. [Delivery scope](docs/douyin-distribution.md). |
| PyInstaller bootloader | Build tool and frozen distribution | GPL with bundling exception; inspect installed-version COPYING text and preserve required notices. The exception is not a license for other bundled dependencies. |
| yt-dlp 2026.8.19 | Core downloader | Unlicense for upstream Python source. `services/download_control.py` adapts FFmpeg command assembly from `yt_dlp/postprocessor/ffmpeg.py` to support cancellation; upstream encoder options are preserved. Wheel and executable dependency notices remain independent. |
| Python / other locked wheels | Core and respective engine packs | Generated inventory with license texts; missing direct-dependency evidence fails the strict generator. Transitive evidence still needs review; metadata is not inferred permission. |
| HaizFlow logo and voice samples | Bundled branding and preview audio | Ownership/provenance of artwork, reference voices and generated outputs must be confirmed separately. Creator attribution alone is not proof. |
| VieNeu 3.8.3 / sea-g2p 0.10.0 / kaldi-native-fbank 1.22.3 | Optional, checksum-pinned VieNeu resource pack; no installation into Core | Apache-2.0 notices and license texts retained in the original wheel dist-info directories. [Backend and pinned-model delivery scope](docs/vieneu-backend.md). MOSS codec source retains its original Apache-2.0 headers. Model and voice rights remain independent. |

See the [Douyin distribution decision](docs/douyin-distribution.md) for the
separation between the bundled driver and direct upstream browser download.
The Chromium base license and Playwright notice are
retained with pinned-source/hash evidence in
[BROWSER-BINARY-LICENSES.json](licenses/BROWSER-BINARY-LICENSES.json).
These documents do not grant redistribution rights or replace the supplier's
complete, exact-binary third-party notice set.
See [licensing review](docs/licensing-review.md) for evidence, blockers and
activation decisions. No runtime component has been removed to bypass these
obligations. Users' video rights and component terms remain independent.
