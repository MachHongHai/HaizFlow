# HaizFlow architecture

[Documentation](README.md) · [Repository](../README.md) · [Tiếng Việt](architecture.vi.md)

This document describes the current desktop application, its dependency boundaries, persisted data and execution model. It is intended for contributors who need to change HaizFlow without coupling the user interface to media-processing details.

## 1. System boundary

HaizFlow is a Windows desktop application. The main process hosts a PySide6/Qt Quick interface and coordinates local project data, model workers and FFmpeg processes. There is no HaizFlow web backend, browser client or hosted project database.

The core dubbing path can run on the user's machine without a paid API:

```text
QML desktop UI
  -> HaizFlowController facade
  -> focused desktop controller
  -> service or pipeline operation
  -> local project artifacts
  -> preview or final FFmpeg output
```

Network access is explicit and feature-specific. It is used to download verified model files, import public media, use Edge TTS when selected, and publish through a user-configured Zernio account. Local OmniVoice, Whisper/WhisperX, HY-MT2, Demucs and FFmpeg do not require a metered inference API after their assets are installed.

## 2. Architectural principles

- **Local ownership.** Source media, intermediate artifacts, settings and exports belong to a local project directory.
- **Narrow UI boundary.** QML reads observable state and invokes slots. It does not run model inference, FFmpeg or project filesystem mutations.
- **Explicit side effects.** A user command starts one named operation. Background work does not silently advance an unrelated Manual tool.
- **Content-addressed reuse.** Expensive Manual results are keyed by inputs and configuration rather than screen state.
- **Atomic publication.** A file becomes visible to the application only after validation and atomic promotion from staging.
- **Backward-readable data.** Schema changes provide defaults and migrations; newer unknown schemas are rejected rather than rewritten.
- **Bounded concurrency.** Model and media workers are limited to protect audio playback, GPU memory and project consistency.

## 3. Source layout and dependency direction

```text
src/haizflow/
  core/          runtime paths, hardware policy, diagnostics and shared events
  desktop/       Qt bootstrap, QML facade, controllers, models and presenters
    qml/         pages, workspaces, dialogs and shared controls
    assets/      branding and pre-rendered voice samples
    translations/ Qt translation catalogs
  pipeline/      transcription, speech, audio and rendering transforms
  schemas/       persisted and cross-layer Pydantic contracts
  services/      projects, storage, downloads, queues, caches and integrations
  utils/         small stateless media/process helpers
  vendor/        audited compatibility code retained with upstream licensing
tests/           Python, integration, QML creation and regression tests
scripts/         environment, verification and release tooling
installer/       Inno Setup definition
licenses/        third-party notices and license texts
```

Dependencies point inward from presentation to application services: QML uses the registered controller API; desktop controllers call services and pipeline entry points; services and pipelines use schemas and core policy. Services, pipelines, schemas and core modules must not import QML.

| Layer | Owns | Does not own |
| --- | --- | --- |
| QML | layout, direct manipulation, focus and presentation state | model inference, filesystem mutation, subprocesses |
| `qml_controller.py` | stable properties, signals, slots and controller wiring | long-running algorithms |
| desktop controllers | one UI workflow and its cancellation/lifecycle | codecs or persisted schema definitions |
| services | use cases, persistence, queues and cache manifests | visual state |
| pipeline | deterministic transforms with explicit inputs and outputs | navigation or project selection |
| schemas | validated persisted contracts | I/O orchestration |

## 4. Desktop composition

`haizflow_desktop.py` enters the project virtual environment when available and launches `haizflow.desktop.main`. The Qt bootstrap configures application identity, translations and runtime paths before loading `Main.qml`. It does not import an inference framework or start an engine.

`Main.qml` is the persistent shell. It owns route history, the top navigation bar, global dialogs and the bottom activity strip. `RouteHost.qml` loads the current page without rebuilding the shell. Project workspaces hide the navigation rail while retaining the same Back, Forward, Home, Projects, Settings and Help controls.

`HaizFlowController` is registered as the QML singleton facade. Focused desktop controllers separate catalog/project state, project commands, imports, processing lifecycle, preview rendering, audio preview, downloads, publishing, settings, resource packs, smart warm-up and diagnostics. List data is exposed through `QAbstractListModel` implementations in `desktop/models.py`.

Background model status belongs to the persistent activity strip. Dialogs are reserved for confirmation or errors that require a decision; transient action feedback uses the toast stack.

## 5. Projects and persisted state

`project_store` owns the project index and `.haizflow-project.json` manifests. `video_store` owns each video's `video.json`, log, media paths and checkpoints. Project and video IDs are immutable UUID-backed identifiers; readable folder names are labels, not identity.

Project metadata currently uses schema v4. Video metadata uses schema v17. Writes use an interprocess lock, temporary file, `fsync` and atomic replacement. The previous valid document is retained as a backup, and corrupt input is quarantined before recovery.

```text
<project-name>--<short-id>/
  .haizflow-project.json
  exports/
  videos/
    <source-name>--<short-id>/
      video.json
      logs.txt
      input/
      temp/
        editor-preview/
        cache/manual/
```

Download projects own `downloads/video`, `downloads/channel` and `downloads/audio`. Publishing projects own `publishing/media`, thumbnails and an atomic queue file. Deletion resolves the registered project root before removing project-owned content; it does not derive a target from the display name.

## 6. Automatic and batch execution

Automatic and Batch projects use the ordered pipeline in `pipeline/process_video.py`:

```text
managed video input
  -> source audio or Demucs separation
  -> Whisper/WhisperX recognition and timing
  -> HY-MT2 translation
  -> subtitle document and ASS materialization
  -> OmniVoice or Edge TTS clips
  -> timestamped audio mix
  -> FFmpeg render and mux
```

Each stage publishes a checkpoint signature derived from its inputs and relevant settings. Resume accepts a checkpoint only when the signature matches and every declared output exists and is non-empty. Batch adds queue ownership and per-video overrides; it does not maintain a separate media algorithm.

Only one heavy foreground pipeline runs at a time. Pause and cancellation propagate through the process registry. Completed artifacts remain reusable; partial output is never promoted as a checkpoint.

## 7. Manual editor and artifact graph

Manual projects are non-linear. The workspace exposes Source, Recognition & Translation, Subtitles, Image, Voice, Audio and Export as independent tools. Each command performs only the operation named by the tool.

- Recognition and translation create a subtitle document but do not synthesize speech.
- Image cleanup reuses a matching OCR-region artifact when switching between original, blur and patch modes.
- Voice synthesis creates only missing TTS clips.
- Audio settings assemble existing tracks and do not invoke a model.
- Export encodes the user's current state; optional layers may be absent.

```text
video -> source audio -> optional separation
selected audio -> recognition -> translation -> subtitle document
subtitle document + voice configuration -> TTS clips
video -> OCR region -> optional blur/patch layer
video + layout + subtitles + watermark -> visual proxy
source/no-vocals + TTS clips + music + levels -> audio mix
current visual state + current audio state -> export
```

Changing one subtitle invalidates that sentence's voice clip and descendants. Changing timing repositions cached clips without rerunning TTS. Changing music or a level invalidates only the mix. Returning to a previously used source mode, voice or cleanup mode reactivates its cache variant. Manual voice selection is transactional: dialog state is a draft, and only confirmation updates the requested manifest. Per-segment overrides participate in each clip signature, while playback remains attached to the last complete manifest until its replacement is published.

### Manual artifact store

`services/manual_artifacts.py` stores immutable artifacts below `temp/cache/manual`. `manifest.json` records each kind, signature, status, inputs, configuration fingerprint, outputs, timestamps, size and error state. Active signatures remain in `video.json`; historical variants stay in the manifest.

```text
cache/manual/
  manifest.json
  source-audio/<signature>/
  separation/<signature>/
  recognition/<signature>/
  translation/<signature>/
  subtitles/<signature>/
  ocr/<signature>/
  visual/<signature>/
  voice/clips/<signature>/
  voice/manifests/<signature>/
  audio/<signature>/
  export/<signature>/
```

A producer writes to staging. Publication validates required files, writes a completion marker and atomically renames the directory. Lookup rejects partial, missing, empty or mismatched output. Active artifacts and artifacts held by runtime consumers are pinned. Project and global limits evict least-recently-used inactive variants before active data.

`manual_completed_stages` remains a migration input for older metadata but has no authority in the current Manual UI.

## 8. Preview and direct manipulation

The editor uses a lightweight preview path rather than rebuilding the final video after every seek.

- Seeking updates media position and the subtitle clock without invalidating visual cache.
- Visual configuration and audio mix have independent signatures.
- TTS clips and source/background tracks are mixed from validated cached files.
- A completed A/V preview is published atomically; the player swaps source while preserving position and playback intent.
- Direct subtitle manipulation uses the renderer-resolved output dimensions, layout rectangle, font size, phrase partition and karaoke clock.
- When the matching render is ready, the transform overlay is dismissed and the rendered proxy becomes authoritative.
- Player source switching is serialized and old workers/players are released when leaving the workspace.

The result pane keeps the last valid frame while a replacement is prepared. Model warm-up and background activity use the bottom status strip instead of blocking the workspace.

## 9. Model and process isolation

Core never imports Torch, ONNX Runtime, WhisperX, Transformers, Demucs or llama.cpp. CPU, CUDA 12.8 and vision inference live in separately frozen, versioned engine processes. HY-MT2 and OmniVoice use persistent JSON-lines servers inside the selected engine. Recognition, OCR and Demucs file tasks reuse the same engine process warmed for their capability. FFmpeg remains a Core-managed external process with cancellation and timeout handling.

Resource Manager is the production path for installing optional engines and model payloads. Every pack declares its protocol version, immutable URL, exact size, and SHA-256. Downloads use resumable partial files; engines pass an isolated smoke test before atomic activation and retain a rollback version. Runtime loaders accept explicit local paths and never fall back to an unpinned network download.

`SmartWarmupController` starts only after the Core window is responsive. It predicts the next capability from the selected project and tool, warms only installed packs in a background worker, and yields to user-requested work. Warm state is independent from task progress: a resident model may reduce first-inference latency but never marks a video task complete. Under memory pressure, speculative residents are released before active work.

Startup pack inventory checks file presence and expected size only; it never hashes a multi-gigabyte checkpoint on
the UI thread. Full SHA-256 verification occurs during installation, repair, or immediately before the first
security-sensitive model load. Cleanup left by a cross-drive resource move also runs after the first frame in a
background maintenance worker.

Hardware policy in `core/hardware.py` selects supported CUDA precision, memory profile, warm-up behavior, inference batch size and CPU thread limits. FFmpeg hardware encoding is probed separately from AI inference; a failed hardware encode can fall back to `libx264`.

## 10. Network and privacy boundary

Network access is limited to features that require it:

- user-confirmed, checksum-verified resource-pack downloads;
- URL/channel media inspection and download;
- Edge TTS when explicitly selected;
- Zernio authentication, upload and publishing.

Credentials are stored through Windows Credential Manager. Media import validates supported hosts and writes to project-owned staging before promotion. Social upload requires explicit confirmation. Diagnostic bundles contain bounded, redacted runtime data and exclude project media and project metadata.

## 11. Observability and failure handling

Per-video `logs.txt` is the authoritative processing log. Pipeline events update persisted progress and a structured activity presentation. Raw technical logs are available on demand rather than occupying the normal workspace.

HY-MT2 diagnostics are bounded and record backend, device, memory snapshots and failures. The application log rotates at a fixed size and captures Python, thread and Qt failures. An error retains the failed tool, safe retry point and recovery action without discarding validated artifacts.

## 12. Runtime containment and packaging

Python 3.13 x64 is the supported source/build runtime. `pyproject.toml` declares direct dependencies. `requirements-lock-py313-win64.txt` is the PyPI-only, hash-locked Core set. The CPU, CUDA and vision engines each have a separate hash lock and reviewed lock manifest; `uv.lock` supports developer resolution and is not a release artifact.

PyInstaller uses an `onedir` Core artifact because Qt and media libraries require adjacent native files. AI engines, models and mutable runtime data are not embedded in the executable distribution. Resource Manager creates and owns the selected local resource root after installation:

```text
runtime/
  engines/  versioned CPU, CUDA or vision engines
  models/   verified model payloads
  packages/ resumable downloads and rollback metadata
  cache/    disposable third-party and application caches
  data/     durable settings, indexes and diagnostics
  tmp/      transient work
```

In source mode, `HAIZFLOW_HOME` can establish the same containment boundary. Runtime configuration redirects known third-party caches and temporary directories below that root to avoid unplanned writes to the system drive.

## 13. Change checklist

| Change | Primary location | Required follow-through |
| --- | --- | --- |
| QML component or screen | `desktop/qml` | focus/accessibility, translation, creation test, no media logic |
| Controller command | focused desktop controller | narrow facade slot, cancellation and state tests |
| Pipeline transform | `pipeline` | explicit inputs/outputs, progress, signature and cancellation |
| Persisted field | `schemas` and store migration | default, validation and old-metadata test |
| Manual artifact | artifact service and tool runner | signature, publication, dependency and eviction tests |
| External provider | `services` | trust boundary, credentials, retry/cancel and notices |

Run `scripts/test.ps1` before merging. Packaging or model-integrity changes also require the release checks in [release-readiness.md](release-readiness.md).
