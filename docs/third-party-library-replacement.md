# Rebuilding and replacing third-party libraries

This document is for developers modifying Qt, PySide or another independently
licensed component. It does not change the component's license or restrict its
modification, debugging, reverse-engineering or redistribution rights. HaizFlow's
application license expressly preserves those rights.

## Qt and PySide

HaizFlow uses dynamically linked Qt/PySide 6.11.1 on Windows x64, under the LGPLv3
option. Sources, component licenses and copyright/attribution records are
provided with the release. Qt's bundled third-party code keeps its own terms.

Use the supplied Qt module sources and `pyside-setup-everywhere-src-6.11.1.tar.xz`
to build a compatible Windows x64 release configuration with MSVC 2022.
[Qt's build instructions](https://doc.qt.io/qt-6/windows-building.html) and
[PySide's build instructions](https://doc.qt.io/qtforpython-6/building_from_source/index.html)
describe the supported compiler, Windows SDK, CMake and binding-generator setup.
Changing Qt APIs or ABI can require rebuilding PySide or HaizFlow as well.

The installed version has this structure:

```text
HaizFlow/versions/0.1.0/
  HaizFlowCore.exe
  _internal/PySide6/       Qt DLLs, Python bindings and plugins
  _internal/shiboken6/     Shiboken library
```

For a local modified build:

1. Close the application. Copy the **Core version directory**, not the entire
   installation or its runtime data, to a separate directory such as
   `D:\HaizFlow-Qt-Test`.
2. Replace the relevant DLLs, bindings and plugins in that copy with your
   compatible rebuilt components. Keep the original library filenames and
   architecture. Copy any additional dependencies required by your build.
3. Run `D:\HaizFlow-Qt-Test\HaizFlowCore.exe` directly. No HaizFlow publisher
   signature or secret key is required to run this standalone local copy.

The official launcher and updater check the inventory of official Core
versions. They are not the entry point for this standalone modified copy.
Do not apply official updates to a customized copy: a full update replaces
libraries with the official versions. Source builds can also be run directly
through `haizflow_desktop.py` using the modified PySide environment.

This procedure keeps the original installation and its projects unchanged.
Windows' own security policies and ABI compatibility still apply.

## FFmpeg

FFmpeg/FFprobe run as separate programs, not as GPL libraries linked into the
HaizFlow Python application. Their sources, linked-library sources, build
recipes and independent GPL/LGPL/permissive notices must be retained.
Qt Multimedia's separate LGPL FFmpeg backend is inventoried separately.

CPU and CUDA engines use a third, LGPL-only shared FFmpeg 8.1.2 backend. Its
recipe is `scripts/ffmpeg/build-engine-msys2.sh`. The frozen PyAV 18.1.0 binding
imports are redirected from vendor-hashed DLL names to compatible standard
DLL names by `scripts/package-engine-media.py`; `AV-BACKEND.json` records the
original and packaged binding hashes and verified imported symbols. No x264,
x265 or other GPL encoder library is linked into these Python engines.
Replace compatible DLLs in the engine's `_internal/av.libs` directory. The
stock wheel's bundled libraries are not the release backend; restoring them
would change the release's licensing and dependency inventory.

The self-built FFmpeg recipe is `scripts/ffmpeg/build-msys2.sh`. Its release
source inventory records the exact MSYS2 package versions, source archives,
hashes, configure line and compiler information. Use those versions rather
than silently upgrading dependencies while reproducing a release.

The application-required features include libass, x264, Rubber Band, drawtext,
audio mixing and tempo filters. A replacement must preserve the features used
by the application. Run `scripts/test-ffmpeg-runtime.py` and the application
tests after replacing a runtime; do not claim compatibility from its version
string alone.

## License references

- [Qt's LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations)
- [FFmpeg's legal information](https://ffmpeg.org/legal.html)
- [HaizFlow license and independent-rights exceptions](../LICENSE)
- [Third-party inventory](../THIRD_PARTY_NOTICES.md)
