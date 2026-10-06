#!/usr/bin/env bash
# Build the application-required FFmpeg features with auditable MSYS2 inputs.
# Dependencies are installed separately; pacman enforces vendor signatures.
set -euo pipefail

if [[ "${MSYSTEM:-}" != MINGW64 ]]; then
    printf '%s\n' 'Run this script from a 64-bit MSYS2 MINGW64 shell.' >&2
    exit 1
fi
repository=$(cd "$(dirname "$0")/../.." && pwd)
work="${HAIZFLOW_FFMPEG_BUILD_DIR:-$repository/build/ffmpeg-source-build}"
[[ "$work" == "$repository"/build/* ]] || { printf '%s\n' 'Build output must stay below this repository build directory.' >&2; exit 1; }
source_archive="$repository/runtime/compliance/ffmpeg/ffmpeg-8.1.2.tar.xz"
mkdir -p "$work"
printf '%s  %s\n' \
  464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c \
  "$source_archive" | sha256sum --check
if [[ -e "$work/output/bin/ffmpeg.exe" ]]; then
    printf '%s\n' 'Output already exists. Choose a fresh build directory before rebuilding.' >&2
    exit 1
fi
tar -xf "$source_archive" -C "$work"
cd "$work/ffmpeg-8.1.2"
pacman -Q > "$work/toolchain-packages.txt"
gcc --version > "$work/compiler-version.txt"
./configure \
  --prefix="$work/output" \
  --arch=x86_64 --cpu=x86-64 --target-os=mingw32 \
  --extra-version=haizflow --disable-autodetect \
  --disable-debug --disable-doc --disable-ffplay \
  --disable-shared --enable-static \
  --enable-gpl --enable-version3 \
  --enable-libass --enable-libx264 --enable-librubberband --enable-libdav1d \
  --enable-libfreetype --enable-libfontconfig --enable-libharfbuzz --enable-libfribidi \
  --enable-zlib --enable-bzlib --enable-lzma \
  --enable-schannel --enable-d3d11va --enable-dxva2 --enable-nvenc --enable-ffnvcodec
make -j "${HAIZFLOW_BUILD_JOBS:-4}"
make install
cp ffbuild/config.log config.h ffbuild/config.mak "$work/"
printf '%s\n' 'FFmpeg build complete. Collect DLL/source closure and run regression tests before installation.'
