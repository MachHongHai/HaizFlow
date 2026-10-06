# Media packaging — 0.1.2 technical review

Reviewer: Codex. Scope: native media packaging, not independent legal or patent
clearance. The owner has authorized this patch release and retained the existing
application-license and asset permissions.

The 0.1.0 media review still applies to the unchanged Qt and CPU/CUDA PyAV
backends. The 0.1.2 CLI recipe additionally enables libmp3lame for narration MP3
encoding. FFmpeg remains an unmodified, separate GPL/version3 CLI executable;
LAME is a separately linked library with its independent LGPL terms. No GPL
encoder is added to the Qt or PyAV shared backends.

The updated CLI closure must include the exact LAME binary/source package,
all non-system DLL dependencies, compiler/CRT inputs, upstream FFmpeg source,
configuration and build recipe. The 0.1.2 corresponding-source ZIP and inventory
are pinned by runtime/third-party-sources-manifest.json. Public release requires
verification of this exact uploaded asset together with the binaries.

The previous 0.1.0 sources and resource-engine assets remain available and are
not overwritten, because installed older versions reference their immutable
URLs and hashes.

Regression acceptance includes actual MP3 encoding/decoding, H.264/AAC export,
AV1 decoding, Bangers subtitles, mixing and time stretching. Installer and
frozen delta-update checks must pass before publication. Hardware NVENC and
other machines' audio quality are not certified by these checks.
