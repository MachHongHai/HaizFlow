# Windows media build inputs

This is a developer document, not part of the installation steps for users.
The three media backends have different purposes and licenses; they must not
be treated as interchangeable binaries.

| Backend | Version | Delivery | Configuration |
| --- | --- | --- | --- |
| HaizFlow CLI | FFmpeg 8.1.2 | Core `bin/ffmpeg.exe`, `ffprobe.exe` and dependency DLLs | GPLv3, libass, x264, Rubber Band, libmp3lame, FreeType, Fontconfig, HarfBuzz, FriBidi; native audio/video filters; optional NVENC |
| Qt Multimedia | FFmpeg 7.1.3, zlib 1.3.1 | PySide6 DLL directory | Shared MSVC build, no GPL encoder library |
| PyAV engines | FFmpeg 8.1.2, PyAV 18.1.0 | CPU/CUDA `_internal/av.libs` | Shared LGPL-only build, native codecs, zlib and Schannel; no GPL/nonfree/version3 components |

## Native CLI and engine builds

The source bundle contains the signed upstream FFmpeg archive, exact MSYS2
package sources (including their PKGBUILDs and upstream tarballs), dependency
licenses, compiler/package inventory and `config.log`, `config.h`, `config.mak`.
The original FFmpeg source is unmodified. The scripts under `scripts/ffmpeg`
record the configure options and build commands.

Use a Windows x64 MSYS2 MINGW64 environment. Install the recorded package
versions rather than updating to current versions. Dependency packages were
verified by pacman signatures. Run `build-msys2.sh` for the CLI and
`build-engine-msys2.sh` for the engine backend. Collection uses the actual PE
imports and package ownership database, rejecting unresolved dependencies.
The baseline is x86-64, not an AVX-only build.

The PyAV wheel is still hash-locked at 18.1.0. Its packaged binding import names
are changed to the new DLL filenames only after all imported media symbols
are found in the replacement library exports. `AV-BACKEND.json` records both
binding hashes, import-name changes and all backend DLL hashes. The stock
vendor FFmpeg and its codec DLLs are not shipped in the replaced directory.

Run media regression tests and each frozen CPU/CUDA smoke test before archiving.
The engine smoke includes an in-memory WAV encode/decode/resample round-trip.
These checks do not establish compatibility with every possible media file.

## Qt Multimedia backend

The Qt 6.11.1 wheel's `avutil_configuration()` reports:

```text
--prefix=/c/FFmpeg-n7.1.3/build/msvc/installed
--disable-programs --disable-doc --disable-debug --enable-network
--disable-lzma --enable-pic --disable-vulkan --disable-v4l2-m2m
--disable-decoder=truemotion1 --enable-zlib
--extra-cflags=-IC:/zlib-1.3.1/build/amd64
--extra-ldflags=-LIBPATH:C:/zlib-1.3.1/build/amd64
--toolchain=msvc --enable-shared --disable-static
```

The bundle retains FFmpeg 7.1.3's upstream archive/signature and zlib 1.3.1
source. Build with MSVC 2022 and a Windows SDK as described by the FFmpeg
Windows build instructions. Paths above are vendor build paths, not required
installation paths. Preserve ABI-major DLL names when replacing the backend.

Qt's software OpenGL fallback reports Mesa 11.2.2 and LLVM 3.6.2. Their sources
and notices are retained independently; the permissive terms do not become
HaizFlow's application license.

## Source origins

- FFmpeg: https://ffmpeg.org/releases/
- MSYS2 exact package source archives: https://repo.msys2.org/mingw/sources/
- Qt/PySide 6.11.1: https://download.qt.io/official_releases/
- zlib 1.3.1: https://zlib.net/fossils/zlib-1.3.1.tar.gz
- Mesa 11.2.2: https://archive.mesa3d.org/older-versions/11.x/11.2.2/
- LLVM 3.6.2: https://releases.llvm.org/3.6.2/

See [library replacement](third-party-library-replacement.md) for the
standalone Qt replacement procedure and its relationship with official updates.
