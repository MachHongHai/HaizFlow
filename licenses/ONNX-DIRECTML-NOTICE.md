# ONNX Runtime / DirectML vision-engine distribution

The Windows vision engine uses the unmodified official `onnxruntime-directml`
1.24.4 CPython 3.13 Windows x64 wheel, pinned with hashes in
`requirements-lock-engine-vision-py313-win64.txt`. Core and speech engines keep
their own CPU ONNX Runtime distribution; the distributions must not be mixed.

ONNX Runtime's MIT license and the wheel's complete `ThirdPartyNotices.txt`
are collected from its recorded package files by the engine notice generator.
The native `DirectML.dll` is separately licensed, not covered merely by the
ONNX Runtime MIT metadata or the DirectML GitHub sample-source MIT license.

- DLL file/product version: `1.15.4+241025-1615.1.dml-1.15.fac7597`
- DLL SHA-256: `9f7d19ab3bec5488bbcd572942c202c8ad2cd23d4f6ecf00000a2200e574b6c9`
- Official binary package: <https://www.nuget.org/packages/Microsoft.AI.DirectML/1.15.4>
- Binary terms source: <https://www.nuget.org/packages/Microsoft.AI.DirectML/1.15.4/License>
- Full terms retained: `DirectML-1.15.4-LICENSE.txt` (HTML decoded, line endings normalised)

Section 1(a) describes copying/distribution in developed Windows/Xbox
applications and services; the integration is a Windows OCR dependency, not a
standalone browser or ML-runtime product. Keep native files and supplier notices
unmodified. The full terms, restrictions and privacy provisions remain applicable.
This scope record is technical provenance, not independent legal certification.

Before releasing a changed wheel or DLL, re-check its own exact binary license,
not only package metadata, and retain its original third-party notices.
