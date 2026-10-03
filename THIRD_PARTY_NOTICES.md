# Third-party components

This repository inventory is not a substitute for the version-specific
`THIRD_PARTY_NOTICES.md` generated inside each release. The existing generator
copies license texts from the exact locked environment and curated `licenses/`.
HaizFlow's source license does not replace any component's independent terms.

| Component | Delivery | Evidence and required review |
| --- | --- | --- |
| PySide6 6.11.1 / Qt / Shiboken | Core DLLs and Python bindings | Installed wheel metadata declares LGPL-3.0-only or GPL alternatives. Select a valid path, audit actual Qt modules, retain notices and corresponding source, prove replacement/relinking and required debugging rights. No Qt commercial license is evidenced. |
| FFmpeg / FFprobe 8.1.2 Essentials | Core, separate executables | Actual `runtime/bin/ffmpeg.exe -buildconf` includes GPL/version3/static/x264/x265. [GPL build notice](licenses/FFmpeg-NOTICE.md); complete source/build closure for static libraries remains required, not just upstream FFmpeg tarball. |
| OmniVoice SDK 0.2.1 | Downloaded SDK / AI engine | Apache-2.0; [notice](licenses/OMNIVOICE-NOTICE.md). |
| OmniVoice checkpoint | Separate pinned model pack | CC-BY-NC-4.0; commercial workflow and generated bundled preview/sample provenance need clearance. The SDK's Apache terms do not clear the checkpoint. |
| HY-MT2 CPU/GPU | Separate pinned model packs | Apache-2.0 declared at pinned revisions; retain [notice](licenses/HY-MT2-NOTICE.md) and license text. |
| Whisper / WhisperX / faster-whisper / CTranslate2 | Separate model and engine packs | Audit every pinned checkpoint including VAD and alignment models, not just the recognition SDK. Engine inventories must be generated from their own locks. |
| Demucs / audio libraries / OCR | Separate engines and model packs; light audio dependencies in Core | Demucs checkpoint, alignment/VAD and OCR provenance must be documented per pack. Python notices cannot infer checkpoint rights. |
| WeSpeaker VoxCeleb ResNet34 | Optional checksum-pinned speaker-identification model pack | Publisher declares Apache-2.0 at the pinned revision; retain [model notice](licenses/WESPEAKER-NOTICE.md) and license text. This is not the separate ResNet34-LM checkpoint. |
| Bangers font | Bundled font | [SIL OFL text](licenses/Bangers-OFL.txt), [copyright notice](licenses/Bangers-NOTICE.md); no HaizFlow ownership claim. |
| Fluent System Icons | Curated bundled SVGs | [Microsoft MIT notice](licenses/FLUENT-SYSTEM-ICONS-NOTICE.md). |
| Douyin helper | Adapted bundled source, isolated process | [Original author and Apache notice](licenses/DOUYIN-CHANNEL-IMPORT-NOTICE.md); retain independently. |
| PyInstaller bootloader | Build tool and frozen distribution | GPL with bundling exception; inspect installed-version COPYING text and preserve required notices. The exception is not a license for other bundled dependencies. |
| Python / other locked wheels | Core and respective engine packs | Generated inventory with license texts; missing direct-dependency evidence fails the strict generator. Transitive evidence still needs review; metadata is not inferred permission. |
| HaizFlow logo and voice samples | Bundled branding and preview audio | Ownership/provenance of artwork, reference voices and generated outputs must be confirmed separately. Creator attribution alone is not proof. |

See [licensing review](docs/licensing-review.md) for evidence, blockers and
activation decisions. No runtime component has been removed to bypass these
obligations. Users' video rights and component terms remain independent.
