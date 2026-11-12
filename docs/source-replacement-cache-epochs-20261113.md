# Explicit Manual source replacement invalidates source-bound caches

## Root causes

1. Selecting the current managed `input/video.*` returned immediately, bypassing
   the replacement transaction and every reset.
2. Selecting an external copy of the same video used `copy2`, preserving size and
   modification time at the same managed path. Some immutable artifact keys
   included only that file state and could rediscover historical OCR or voice
   results after active metadata had been cleared.

## Retained semantics and fix

- Every successful explicit replacement advances the existing durable `source`
  generation, including selection of the current input itself. The original
  input is staged before its directory is retired, so selecting it is safe.
  Its original display filename is preserved.
- Replacements remain transactional: input, temp outputs, metadata and editor
  document are restored on failure. Source generation advances only on commit.
- Source audio already carries this generation; separation and ordinary
  recognition/translation inherit it through their dependency signatures.
- Add a separately namespaced source-generation token to OCR, imported-SRT
  recognition, subtitle documents, single/multiple-speaker voice clips and
  manifests, audio mix and export signatures. Source replacement cannot alias
  an old explicit image/voice rerun counter.
- Preview source identity and newly created editor source-asset/waveform
  fingerprints also include the replacement generation. Equal file metadata
  cannot resurrect an old preview or waveform after replacement.
- Imported SRT inspection checks the generation again before publication, so a
  same-file replacement during inspection cannot attach subtitles to the new
  source accidentally. Existing persisted SRT record formats remain readable.
- Generation-zero keys are unchanged, preserving caches in untouched projects.
  Reusable model/language/style preferences and installed model/resource caches
  are not purged. Text/content-specific source guidance still resets on an
  explicit replacement; ordinary Restart preserves it.

Historical immutable artifacts may remain on disk for normal cleanup. They are
not active and their old keys cannot satisfy the new source generation. Canonical
old temporary outputs are quarantined outside lookup paths by the existing
replacement transaction; UI drafts/history and playback readers retain their
existing source-replacement teardown.

## Verification

`tests/test_source_replacement_cache_epochs.py` covers real immutable-cache
publication with a mocked detector, not merely key comparison: OCR is invoked
twice after replacing the same external or managed input, even with exactly
matching path/size/mtime, and the second result is activated. It also tests an old
image-rerun collision, persisted-metadata reopening, failed same-input replacement,
all processing signatures with separation on/off, five voice backends in single
and multiple modes, SRT import/replacement races, preview and waveform identities.

Related suites cover existing incremental sentence reuse, artifact ownership,
rollback, source guidance, imported SRT, editor documents and legacy cache
migration. No real user projects were changed and no models/API were invoked.
No build, push or publish was performed.

## Reopening compatibility regression

Adding the source epoch to preview identity also changed keys in existing
projects whose source counter was already positive. Reopening those projects
therefore missed their completed pre-epoch picture proxies. Preview lookup now
tries the exact current key first, then compatible pre-epoch spellings with all
other source, crop, mask, timing and encoding fields unchanged.

Compatibility lookup stays inside canonical `temp/editor-preview`. Explicit
replacement transactionally retires that tree, so it cannot resurrect a proxy
from an older source, including when deferred cleanup leaves quarantine files.
This adds no encoding, large-file copying, FFprobe or completion-marker writes.

Read-only checks against `w3`, `HOI1`, `d`, `testocrdev` and `w2` all recovered
their existing completed proxies with FFprobe forbidden. Regression tests cover
repeated reopening, exact-key priority, changed source/treatment rejection and
same-source replacement with deferred quarantine cleanup.
