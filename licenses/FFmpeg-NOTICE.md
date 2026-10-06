# FFmpeg Distribution Notice

The Windows artifact bundles separately executed `ffmpeg.exe` and `ffprobe.exe`, built from unmodified FFmpeg 8.1.2 source for Windows x64. This CLI build enables GPL/version3, libass, x264 and Rubber Band and is distributed under GPL-3.0-or-later. Its external libraries are dynamically linked and retain their independent notices.

- Build recipe: `scripts/ffmpeg/build-msys2.sh`
- Exact executable and DLL hashes: `FFMPEG-MANIFEST.json`
- Upstream source: `ffmpeg-8.1.2.tar.xz`
- Source SHA-256: `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`
- Source signature: `ffmpeg-8.1.2.tar.xz.asc`
- FFmpeg legal information: https://ffmpeg.org/legal.html
- GPL-3.0 text included in this release: `GPL-3.0.txt`

The binary manifest, license, signed upstream source archive, signature, configure evidence and recipe are included under `sources/ffmpeg` in the Windows artifact. The release's `HaizFlow-0.1.0-ThirdPartySources.zip` supplies the exact linked-library source archives, MSYS2 PKGBUILDs, compiler/CRT sources and component notices. Obtain it from the same GitHub Releases page as the installer. The source bundle is separate so users do not need to install development material.

Qt Multimedia uses a separate FFmpeg 7.1.3 shared backend without GPL components. CPU/CUDA engines use a separately built FFmpeg 8.1.2 LGPL-only shared backend for PyAV. These backends are not the GPL CLI binaries. Their inventories, sources and build instructions are supplied separately in the same source bundle.
