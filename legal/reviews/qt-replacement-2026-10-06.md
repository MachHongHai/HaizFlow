# Qt/PySide packaging — technical review, 2026-10-06

Reviewer: Codex. This records reproducible packaging checks, not legal advice.

The frozen Core uses dynamic Qt/PySide/Shiboken 6.11.1 DLLs. The actual module
set was inspected. GPL-only add-ons excluded by the Core builder are not
shipped, and qsb is not bundled as an executable. Official Qt/PySide source
archives, per-module licenses/attributions, software OpenGL notices/sources,
and the distinct Qt FFmpeg/zlib backend sources are included in the pinned
ThirdPartySources ZIP. Qt mirror SHA-256 values are verified by the collector.

LGPL license texts and prominent Qt/PySide notices are packaged. LICENSE
preserves independent rights to modification, replacement, relinking,
debugging/reverse engineering and redistribution to the extent required by
the component license. No publisher key or paid Qt license is required by the
standalone Core execution path.

A disposable copy of the frozen Core passed its UI smoke after Qt6Core.dll's
PE checksum was changed. No user installation was modified. This verifies
that a changed dynamic library can load through the documented standalone
path without publisher approval; it does not prove arbitrary rebuilt DLLs
are ABI-compatible. The replacement instructions explain matching ABI and
keeping customized copies separate from official updates.

Technical evidence: source inventory, module/license inventory and replacement
mechanism checked. No independent copyright verification, blanket legal
certification, or full Windows 10/11 machine matrix is claimed.
