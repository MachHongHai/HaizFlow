# Media packaging — technical review, 2026-10-06

Reviewer: Codex. Scope: the pinned native media payload and source asset for
0.1.0, not patent clearance or a lawyer's certification.

The command-line FFmpeg/FFprobe executables are built from unmodified FFmpeg
8.1.2 with the checked-in MSYS2 recipe. This is a separate GPL-3.0-or-later
command-line process, not a GPL library linked into the application. The
runtime manifest pins both executable hashes and the complete non-system DLL
closure. The source collection contains exact MSYS2 source packages, upstream
FFmpeg, recipes, configure/build logs, licenses and an SHA-256 inventory.

The stock PyAV wheel's patched vendor FFmpeg contains x264/x265 despite its
reported LGPL label. It is not shipped unchanged: the packaging script
replaces that backend with an unmodified, shared LGPL-2.1-or-later FFmpeg 8.1.2
build without GPL/nonfree components. All imported symbols are checked before
redirecting PyAV binding DLL import names. The exact transformations and
original/packaged hashes are recorded in AV-BACKEND.json. No x264/x265 binaries
remain in the resulting engine backend. CPU and CUDA media round trips pass.

Qt's distinct FFmpeg 7.1.3 backend is shared and its source/configuration is
included separately. The source ZIP includes Qt's zlib source and notices too.

`runtime/third-party-sources-manifest.json` pins the complete ZIP. Verification
checks every inventory entry, source closure and the no-GPL engine build
configuration. Sources must be uploaded alongside the public binary channel
before binaries are made public. Local ZIP validation is not proof of remote
availability; publication must verify the uploaded size and digest.

Media regression coverage: H.264/AAC, synthetic AV1 via dav1d, Bangers ASS,
audio extraction, mixing, blur/drawtext and Rubber Band time stretching.
Hardware NVENC encoding is not claimed by these CPU regressions.

Source packaging technical evidence: complete for these pinned inputs.
Patent rights and all jurisdictions' legal compatibility: not independently
assessed. Independent GPL/LGPL rights remain applicable under LICENSE.
