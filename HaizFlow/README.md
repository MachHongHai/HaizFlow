# HaizFlow

**Open-source, local-first desktop software for processing and repurposing videos in batches — without API fees.**

[Tiếng Việt](README.vi.md) · [Repository](https://github.com/MachHongHai/HaizFlow) · [Report an issue](https://github.com/MachHongHai/HaizFlow/issues) · [License](LICENSE)

HaizFlow helps you download public media, translate and dub videos, manage subtitles, and export ready-to-publish results from one desktop application. It is built for a straightforward workflow: create a project, choose the source and settings, then follow its progress in a clear, responsive interface.

> [!NOTE]
> HaizFlow is under active development. Review the terms of every source platform and use only media you are allowed to download, process, and publish.

## Highlights

- **Easy desktop workflow** — dedicated screens for single-video, batch, and download projects; consistent navigation, clear actions, live progress, and recoverable work.
- **Project-based organization** — keep source media, settings, outputs, logs, and recovery data together in an isolated project folder.
- **Batch-ready** — queue and manage multiple videos while retaining project state when returning to the application.
- **Download tools** — download public videos or channel media, and download or extract audio into a chosen output folder.
- **Translation, dubbing, and subtitles** — speech recognition, translation, text-to-speech, subtitle rendering, and final video export in one pipeline.
- **Better subtitle replacement** — automatically detects a likely burned-in subtitle area; masks it before placing the new subtitle. Videos without detected source subtitles use the standard subtitle layout.
- **Audio mixing controls** — choose original audio or vocal separation, add background music from a file or link, and preview the mix before processing.
- **Local-first runtime** — media processing, transcription, translation models, separation, and rendering run locally. Models download and verify only on the first required launch, then are reused.

## What runs locally?

HaizFlow uses local components such as WhisperX, HY-MT2, Demucs, OCR, and FFmpeg for its processing pipeline. Downloading from public links naturally connects to the selected platform. The default Edge TTS provider is an online service, so text submitted for voice synthesis is sent to that provider.

## Install

### Windows installer

When a release installer is available, download it from [Releases](https://github.com/MachHongHai/HaizFlow/releases), choose an installation directory, and launch HaizFlow. The installer does **not** bundle large language and media models. On the first launch that needs them, the application shows model download progress and verifies the downloaded files before use.

### Run from source

Requirements: Windows 10 (1809+) or later, Python 3.11–3.13 x64, Git, and `uv`.

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

By default, source mode stores runtime data under `runtime\`. Set `HAIZFLOW_HOME` in `.env` to place models, projects, caches, and logs elsewhere; see [.env.example](.env.example).

## Typical workflow

1. Create a **Single**, **Batch**, or **Download** project.
2. Add a local file, paste a supported public link, or choose a public channel/profile.
3. Choose output language, voice, audio treatment, optional background music, and output location.
4. Start processing and monitor status, logs, and output from the project screen.
5. Open the exported video or its output folder when complete.

## Development

Run the quality checks before submitting a change:

```powershell
.\scripts\test.ps1
.venv\Scripts\python.exe .\scripts\verify-runtime.py --for-build
.\scripts\audit-dependencies.ps1
```

To build the Windows executable and installer locally:

```powershell
.\scripts\build-exe.ps1
.\scripts\build-installer.ps1
```

Release builds validate tests, QML, runtime dependencies, compliance data, frozen-app smoke tests, and artifact checksums. See [release readiness](docs/release-readiness.md) for the current release checklist.

## Project layout

```text
src/haizflow/core/       paths, diagnostics, integrity, and hardware helpers
src/haizflow/desktop/    PySide6 desktop controllers and presentation layer
src/haizflow/desktop/qml Qt Quick interface
src/haizflow/pipeline/   transcription, translation, dubbing, subtitle, and render stages
src/haizflow/services/   projects, media import/download, queue, and storage services
src/haizflow/schemas/    versioned metadata schemas and migrations
scripts/                 setup, test, verification, and build tooling
installer/               Windows installer definition
test/                    unit, integration, UI, and release-regression tests
```

For architecture notes, see [docs/architecture.md](docs/architecture.md).

## Contributing

Contributions, issue reports, and UX feedback are welcome. Please open an [issue](https://github.com/MachHongHai/HaizFlow/issues) before large changes so the direction can be discussed first.

## Author and contact

Created by **Mạch Hồng Hải**.

- GitHub: [MachHongHai](https://github.com/MachHongHai)
- Email: machhonghaipr@gmail.com

## License

HaizFlow source code is licensed under the [Apache License 2.0](LICENSE). Third-party dependencies, models, and bundled binaries retain their own licenses; see [NOTICE](NOTICE) and `licenses/`.
