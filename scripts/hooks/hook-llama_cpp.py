"""Keep llama.cpp's ctypes-loaded libraries at their package-relative path."""

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs("llama_cpp")
