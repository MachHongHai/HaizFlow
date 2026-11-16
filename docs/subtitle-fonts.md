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
The upstream OFL texts and copyright notices ship with release compliance
material. Font changes invalidate rendered-video and caption-sprite caches only,
not translation, speech separation, TTS clips or source media.

## Additional regional choices

The curated catalogue includes 22 additional static faces from the same pinned
Google Fonts revision, with an individual OFL notice for every family:

| Language | Additional families |
| --- | --- |
| Korean | Black Han Sans, Jua, Do Hyeon, Gowun Dodum, Gowun Batang Bold, Sunflower Bold, Gugi, Gaegu Bold |
| Japanese | Zen Maru Gothic Black, Zen Kaku Gothic New Black, Yusei Magic, Reggae One, Klee One SemiBold, Hachi Maru Pop, RocknRoll One |
| Simplified Chinese | ZCOOL KuaiLe, Zhi Mang Xing, Ma Shan Zheng, ZCOOL QingKe HuangYou |
| Traditional Chinese | Iansui, LXGW WenKai TC Bold, Huninn |

These are selectable alternatives, not new automatic defaults. The picker only
offers faces for the requested region whose indexed glyphs cover its sample.
For any later caption containing unsupported characters, the existing whole-cue
Noto fallback still applies. Existing project choices and media/translation/TTS
caches are unchanged. Font registration is memoized for the finite bundled
catalogue so browsing more than 32 families does not repeatedly register faces.
