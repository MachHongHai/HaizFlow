# CPU/GPU settings and model warm-up

## Device selection

- The user's CPU/GPU preference is persisted as an explicit choice. Restarting or changing interface language does not replace it with hardware auto-detection.
- New Auto, Manual and Batch projects share device defaults: Whisper Small CPU, HY-MT2 Q4 and OmniVoice CPU in CPU mode; Whisper Small GPU, HY-MT2 full and OmniVoice GPU in GPU mode.
- Existing video settings and Batch overrides remain intact. GPU mode allows an explicit CPU model choice. CPU mode disables GPU options and blocks incompatible saved selections at execution preflight, with an explanation.
- Empty projects opened after another project reset their unsaved model defaults, rather than inheriting the previous project's settings.

## Warm-up

- Startup predicts one Whisper Small model using the app's selected device, without requiring a project or video.
- Project prediction uses the video's saved model/device choice. Explicit Whisper CPU selections use the CPU engine even in GPU app mode, including the direct development fallback.
- Changing devices waits for runtime switching to finish before speculative loading. Foreground tasks retain priority. Memory thresholds and sequential handoff remain enforced; warm-up does not guarantee every model stays resident.
- Missing resource packs are reported; speculative warm-up does not install or download models.
- This change does not claim a measured improvement to full-video generation throughput. The full user project was not rerun during verification.

## Related fixes

- The latest inspected automatic run failed with `WinError 5` while replacing an advisory engine progress file. Atomic replacement now retries transient permission errors; an unavailable progress update does not abort inference. Mandatory task results still surface write failures.
- Whisper worker initialization and each Gemini text batch emit stage logs before the blocking operation begins.
- Auto shows Process again after pause/completion/failure, Resume retains checkpoint semantics, and active processing shows Pause instead of a restart command.

## Verification

Generic unit tests cover CPU/GPU defaults, explicit CPU overrides, startup prediction, persistence, blocked device switches and configuration round trips. A Qt runtime test checks Auto command visibility and labels across empty, paused, completed and running states. Targeted QML lint and Python undefined-name/syntax checks pass. Tests use isolated workspace storage on D: and do not modify the user's projects.
