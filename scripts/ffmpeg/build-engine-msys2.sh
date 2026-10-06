#!/usr/bin/env bash
# LGPL-only shared media libraries for the CPU and CUDA Python engines.
set -euo pipefail
[[ "${MSYSTEM:-}" == MINGW64 ]] || { printf '%s\n' 'Use MSYS2 MINGW64.' >&2; exit 1; }
repository=$(cd "$(dirname "$0")/../.." && pwd)
work="$repository/build/engine-ffmpeg-source-build"
archive="$repository/runtime/compliance/ffmpeg/ffmpeg-8.1.2.tar.xz"
printf '%s  %s\n' 464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c "$archive" | sha256sum --check
[[ ! -e "$work/output/bin/avutil-60.dll" ]] || { printf '%s\n' 'Output already exists.' >&2; exit 1; }
mkdir -p "$work"
tar -xf "$archive" -C "$work"
cd "$work/ffmpeg-8.1.2"
pacman -Q > "$work/toolchain-packages.txt"
gcc --version > "$work/compiler-version.txt"
./configure --prefix="$work/output" --arch=x86_64 --cpu=x86-64 --target-os=mingw32 \
  --extra-version=haizflow-engine --disable-autodetect --disable-debug --disable-doc \
  --disable-programs --disable-static --enable-shared --disable-gpl --disable-nonfree \
  --disable-version3 --enable-zlib --enable-schannel
make -j "${HAIZFLOW_BUILD_JOBS:-4}"
make install
cp ffbuild/config.log config.h ffbuild/config.mak "$work/"
