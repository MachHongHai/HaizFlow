# CPU metadata and flat-Core engine failures

User reports concern HaizFlow 1.0.1; fixes below are source changes after 1.0.2,
not a claim that existing installed binaries have been repaired.

## Reproduced failures

- Hardware metadata used `monotonic() - 0 >= 24 hours` for an empty cache.
  When the monotonic clock reading was below one day, the first CIM query never
  ran (reproduced with a 20-second clock reading).
  Unexpected probe exceptions could also leave the refresh flag set forever.
- An engine receiving a flat app root unconditionally constructed `Layout(root)`.
  A standalone extracted Core payload (or legacy flat installation) has no
  `update-layout.json`, so inference failed even though the editor opened.

Hardware now reads cheap registry CPU identity immediately, schedules the first
CIM probe regardless of uptime, bounds retries, tolerates unavailable providers
and malformed fields, and transfers completed metadata to the GUI without a new
CUDA probe. PowerShell 5 no longer inherits PowerShell 7's module paths.

Engine roots now accept a local, non-reparse flat application containing the app
executable. They do not invent update markers or move/create project data. An
existing invalid marker or incomplete versioned installation still fails closed.

The four processing threads on a low-memory CPU profile are an inference budget,
not the detected hardware thread count. The existing RAM policy is unchanged.
Ryzen 4750G identity and 16 logical processors are covered by mocked tests, not
benchmarks on that user's machine.

## SciPy report: exact user cause remains unconfirmed

CPU engine 15 available locally contains
`_internal/scipy/linalg/_linalg_pythran.cp313-win_amd64.pyd`; its existing frozen
CPU smoke test passed, including WhisperX ASR/alignment imports. Without the
user's full log/pack inventory, an old, damaged or mixed installation cannot be
distinguished. This is not evidence that every user's CPU pack is intact.

A dedicated SciPy hook now explicitly collects the Pythran extension and keeps
the upstream Cython BLAS/LAPACK hidden imports. CPU/CUDA engine smoke tests
explicitly require the extension before model weights are loaded. RPC errors
retain their technical cause and explain how to verify/reinstall the engine pack.

For existing users, prefer the `HaizFlow-<version>-Setup.exe` installer rather
than treating an update Core ZIP as the complete installer. Keep the current
runtime/projects. For a SciPy error, verify and, if necessary, reinstall only the
CPU engine in Resource Packs; installing system Python/pip is not a repair for
the frozen engine.

Shipping these fixes requires rebuilding Core and the affected engine packs
(shared path code also belongs to the vision engine). No archive, catalog hash,
published asset or resource receipt was changed by this source-only fix.
