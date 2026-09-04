# HaizFlow

**Free, local-first video translation and dubbing for Windows.**

HaizFlow turns a source video into a translated, voiced and publishable result from one desktop application. Speech recognition, translation, local voice synthesis, source separation and rendering can run on your own computer. The core workflow does not require a paid inference API.

The application is designed for people who want control over their media and operating costs: project files stay local, reusable work is cached, and every tool in the Manual editor can be used independently.

## Capabilities

- Transcribe speech with Whisper/WhisperX and translate subtitles with HY-MT2.
- Generate speech with local OmniVoice or the optional online Edge TTS provider.
- Separate vocals and background audio with Demucs.
- Render karaoke subtitles, original-subtitle cleanup, watermark and audio mix with FFmpeg.
- Process one video automatically, manage a batch queue, or work in a non-linear Manual editor.
- Import individual videos and public channel media from supported platforms.
- Publish through an optional user-configured Zernio connection.

## Local-first, without a paid API bill

The default architecture runs model inference on the user's CPU or supported NVIDIA GPU. After the required model assets have been downloaded and verified, the local pipeline does not send video, transcripts or voice data to a metered inference service.

Some features are intentionally online:

- first-run model and runtime downloads;
- importing media from a URL or channel;
- Edge TTS, when selected instead of local OmniVoice;
- social publishing through Zernio.

These network boundaries are tied to visible features. Credentials are stored with Windows Credential Manager.

## Project modes

### Automatic

Configure one video and let the ordered pipeline produce the final result. Checkpoints support safe resume and prevent valid completed work from being repeated.

### Batch

Apply the same processing model to multiple videos. Batch reuses the Automatic settings schema and adds queue state plus per-video overrides.

### Manual editor

Use Source, Recognition & Translation, Subtitles, Image, Voice, Audio and Export as independent tools. A project can be exported in its current state; optional work does not have to be completed to satisfy a fixed sequence.

Manual artifacts are content-addressed. Changing one subtitle can regenerate one voice clip instead of the whole soundtrack; changing timing reuses speech; changing music rebuilds the mix without rerunning translation or TTS.

### Downloads and publishing

Download projects keep imported media separate from processing projects. Publishing projects maintain their own queue and project-owned copies, so an upload cannot mutate an editor source.

## Requirements

- Windows 10 version 1809 or newer, x64.
- Python 3.13 x64 for a source installation.
- Sufficient free storage for selected models, project media and preview cache.
- CPU mode: approximately 6 GB or more available system RAM.
- GPU mode: a compatible CUDA GPU with at least 7 GB total VRAM and sufficient free VRAM.

GPU inference is optional. FFmpeg may still use NVENC, Intel Quick Sync or AMD AMF when AI inference runs on CPU.

## Run from source

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow\HaizFlow
.\scripts\install-desktop-env.ps1
.\scripts\run-desktop.ps1
```

The setup script creates `.venv`, installs the hash-locked Windows/Python 3.13 dependency set and installs HaizFlow in editable mode. To place dependency downloads and temporary builds on another drive, set `HAIZFLOW_HOME` or the cache paths documented in `.env.example` before installation.

The first application launch verifies the selected runtime and downloads only the model set required by the chosen CPU/GPU configuration. Model files are checked by size and SHA-256 before use.

## Development checks

Run the complete source gate from the inner `HaizFlow` directory:

```powershell
.\scripts\test.ps1
```

The gate compiles Python modules, runs Ruff, checks QML diagnostics and executes the unit and regression suite. Release work has additional dependency, runtime, FFmpeg and frozen-artifact checks; see [Release readiness](HaizFlow/docs/release-readiness.md).

Useful entry points:

```powershell
.\.venv\Scripts\python.exe .\scripts\verify-runtime.py
.\scripts\audit-dependencies.ps1
.\scripts\build-exe.ps1
```

Do not run the build scripts merely to start development. `run-desktop.ps1` is the source launcher.

## Repository map

```text
HaizFlow/
  src/haizflow/
    desktop/    PySide6 controllers, QML UI, translations and desktop assets
    pipeline/   recognition, speech, audio and rendering transforms
    services/   projects, persistence, downloads, caches and integrations
    schemas/    validated project and video contracts
    core/       runtime paths, hardware policy, logging and integrity policy
  test/         Python and QML regression tests
  scripts/      environment, verification and release tooling
  docs/         architecture, security and release notes
  licenses/     third-party notices and license texts
```

For component boundaries, Manual cache semantics, concurrency and persisted layouts, read [Architecture](HaizFlow/docs/architecture.md).

## Data, cache and recovery

Every project owns its source copy, metadata, intermediates and exports. Metadata is written atomically with a backup. Manual cache entries are immutable and are published only after their outputs validate.

Preview data is disposable; source files and user exports are not. Cache eviction protects active artifacts and open media. The runtime root can be placed outside the system drive so models, logs, caches and temporary files remain under a directory chosen by the user.

## Security and reproducibility

- Production dependencies are pinned and installed from a SHA-256 hash lock.
- Downloaded model repositories, revisions, required files and hashes are fixed in source.
- Model loaders use explicit verified local paths and reject missing or corrupt payloads.
- External URLs and redirects are restricted to hosts required by the selected feature.
- Diagnostic exports are bounded and exclude project media.

Reviewed dependency advisories and compensating controls are documented in [Dependency security](HaizFlow/docs/dependency-security.md).

## License

HaizFlow source code is available under the [Apache License 2.0](HaizFlow/LICENSE). Bundled and downloadable components keep their own licenses; see [NOTICE](HaizFlow/NOTICE) and the [`licenses`](HaizFlow/licenses) directory.

A model or voice runtime may impose terms that differ from the HaizFlow source license. Review the applicable notices before redistribution or commercial use.

## Contributing

Bug reports should include the affected project mode, the operation that was running, whether CPU or GPU mode was selected, and a minimal reproducible sequence. Do not attach private source video, credentials or an entire runtime directory unless it is explicitly required and safe to share.

Code changes should preserve layer boundaries, add a regression test for behavior changes and pass `scripts/test.ps1`.
