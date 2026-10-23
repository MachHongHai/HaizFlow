# Startup verification optimization — 2026-10-23

## Finding

Normal versioned startup verified the active Core in `launch()` and immediately
verified the same complete tree again in `start_core()`. Each pass enumerates
all files, checks reparse points, and reads every file for SHA-256. This work
happens before Core process creation and the Qt window. It is unrelated to
loading an AI model.

The local 1.0.3 Core fixture has 4,338 payload files, totaling about 579 MiB.
On this Windows machine, a warm-cache serial inventory took 6.37–7.06 seconds;
a four-worker inventory took 4.71–4.76 seconds, with identical output. A separate
comparison of the complete verification boundary (including manifest and path
validation) measured 30.59 seconds for the old two serial passes and 16.85
seconds for the new single parallel pass. These are verification-stage timings,
not total click-to-window timings or promises for other machines. Windows file
caching, antivirus, concurrent disk traffic, and profiler overhead affect them.

## Changes

- Verify at the execution boundary only; direct `start_core()` calls still
  perform full validation. No caller can bypass verification with a flag.
- Distinguish pre-spawn payload verification failure from health-check failure,
  retaining the previous verified-version fallback and update rollback rules.
- Overlap at most four hash reads, in batches of at most 16 queued files.
  Inventory output remains sorted and deterministic; errors propagate.
- Retain full byte hashing, manifest/completion-marker checks, exact file-set
  checks, symlink/junction rejection, single-launcher lock, health handshake,
  and transactional pointer handling. No integrity result is cached across runs.
- Do not change project files, media caches, AI warm-up, or QML controls.

## Checks and distribution

Regression tests cover one verification on normal launch, same-size corruption
before spawning, previous-version fallback, update health rollback, no fallback
on known-good health failure, deterministic concurrent inventory, bounded
concurrency, read failure, changed/missing/extra files, and nested junctions.
The desktop offscreen smoke test uses an isolated runtime, not user projects.

The launcher change requires rebuilding/distributing the bootstrap launcher.
A Core-only update leaves an already installed old launcher unchanged; it must
not be advertised as including the full startup improvement. No executable was
built or published during this investigation.
