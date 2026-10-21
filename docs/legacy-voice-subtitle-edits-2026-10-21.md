# Speech preservation after subtitle merge/delete

## Reproduction: lol

Read-only inspection found an intact, complete 26-sentence voice manifest
whose source subtitle document predates stable sentence IDs. The working
document contains 25 sentences after merging the second and third sentences.
Only its first voice clip was still enabled; later unchanged clips had been
marked stale. No MP3 had been removed.

The editor's reconciliation and PCM preview both fell back to row positions
for ID-less voice source documents. Merging/deleting a row shifts all later
positions, so matching by text at that new position incorrectly silenced
unchanged speech. Regeneration/export fallback had the same missing link.

## Fix

- Share the exact legacy deterministic sentence-ID contract between the
  editor and backend, without depending on Qt from backend services.
- Reconstruct original IDs from immutable voice-source rows, then match them
  to current rows without depending on current order or timestamps.
- Keep explicit IDs authoritative. For older documents with other IDs, allow
  only an unambiguous legacy text/time match, not text-only/index guessing.
- Use the same mapping for editor repair, PCM preview, export fallback and
  incremental TTS generation.
- Do not revive a merged/edited clip from an older subtitle publication while
  its asynchronous save is pending. Unchanged clips remain available.
- Keep the last published voice manifest and source files untouched.

Applying reconciliation to an in-memory copy of the real project restores
24 unchanged voice clips and leaves only the merged sentence stale. Hashes
and modification times of video metadata, editor document, artifact manifest
and all 26 voice MP3s remain unchanged. The diagnostic does not save its copy.

## UI

The expand action is now an always-visible fullscreen icon beside the subtitle
actions button, not a menu entry. It opens the existing expanded editor with
the current draft. The existing theme, tooltip, keyboard focus and compact
footer layout are retained. QML tests cover 300/380/460px panel widths and
150% display scaling.

## Regression coverage

Tests cover merge/delete before repeated lines, unchanged speaker identity,
reordering/retiming, Undo/Redo, pending subtitle publication, repair of disabled
clips, correct preview file selection, and incremental generation of only the
merged sentence. The broader suite also covers subtitle import, export guards,
IME editing, voice notices, navigation cache and crop-cache identity.

No build, push or publish was performed, and user project data was not edited.
