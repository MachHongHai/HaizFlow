# Bundled subtitle typography

Caption fonts are selected from published subtitle language and actual script,
not the source video's language or only the next translation choice:

| Script | Primary | Whole-cue fallback |
| --- | --- | --- |
| Vietnamese / English / Spanish | Bangers | Existing Latin policy |
| Simplified Chinese | Noto Sans SC Black | Same bundled font |
| Traditional Chinese (`zh-TW`/`zh-Hant` context) | Noto Sans TC Black | Same bundled font |
| Japanese | Dela Gothic One | Noto Sans JP Black |
| Korean | Pretendard ExtraBold | Noto Sans KR Black |

The coverage index is generated offline from each font's cmap. If a caption
needs a glyph absent from the primary face (e.g. Korean Hanja), the whole cue
uses the regional Noto fallback rather than an uncontrolled mixture of system
fonts. No transliteration or subtitle text/timestamp changes occur. Unknown
legacy font names still normalize to the supported default; watermark and free
text overlay font choices are unaffected.

`core/subtitle_fonts.py` is the shared policy for ASS export, preview sprites,
width measurement and Qt's selection fallback. Japanese Kanji-only cues inherit
the document's Japanese context. Qt uses the font's typographic family and real
weight (900 for Noto Black, 800 for Pretendard ExtraBold); libass uses the static
face's legacy family. Qt fonts load on demand, not all at application startup.

The original, unmodified font files are pinned to upstream Git revisions in
`scripts/prepare-subtitle-fonts.ps1`. SHA-256, copyright strings and glyph ranges
are recorded in `src/haizflow/assets/subtitle-fonts.json`. Restore the font assets
with that script, and regenerate the index with `scripts/index-subtitle-fonts.py`
(fontTools is a development dependency, not loaded by the desktop policy).

Both setuptools package data and the desktop build include the fonts/index.
The three upstream OFL texts and copyright notices ship with release compliance
material. Font changes invalidate rendered-video and caption-sprite caches only,
not translation, speech separation, TTS clips or source media.
