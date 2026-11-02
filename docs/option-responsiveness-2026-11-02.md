# Option interaction responsiveness

Audited Manual, Auto, Batch, API/settings, resource management, downloads and
social-publishing controls. The existing palette, layout, processing queue,
media cache identities, pause/resume and explicit render behavior are retained.

## Confirmed hot paths and changes

- Reasoning choices previously rebuilt their own options model after each
  selection. Supported capabilities now depend on the selected model/guidance,
  not the selected effort. Only the selected index changes. The API controller
  keeps a bounded public-capability memo, invalidated on connection/catalogue
  notifications. Credentials are not memoized by this change.
- Choosing a voice previously notified the entire voice-options list, resolving
  samples and recreating delegates. Selection now has its own notification;
  catalogue changes still notify the list and selected index. Known published
  subtitle languages do not require a full subtitle copy on each lookup.
- Missing library preview samples unnecessarily loaded project metadata once per
  voice. Only clone-reference resolution reads the project. Media checks use one
  stat and tolerate files disappearing during navigation.
- Recognition/translation option clicks called resource integrity inventory on
  the GUI thread. They now use the resource controller's background inventory
  snapshot. Unknown/in-progress inventory is not misreported as a missing pack.
  Hardware guards remain; job admission/inference still verifies resources.
- Every selected-video metadata notification used to emit a complete editor
  document change, rebuilding clips, subtitles, overlays and audio. Metadata
  notifications now update OCR-layer metadata separately. Actual document edits
  still notify all affected views normally.
- Manual tool-state presentation calculated cache signatures synchronously in a
  QML property getter. A single worker now coalesces requests: one running and
  only the latest pending snapshot. Old-project results are ignored. The getter
  returns already-computed rows. This worker is read-only; runners retain their
  own authoritative readiness and artifact validation. Repeated structural
  artifact observations are shared only within one calculation, never carried
  over as persistent cache-validity decisions.
- The debounced save for next-run translation/voice settings no longer requests
  an unrelated preview rebuild. Changes to visuals/audio retain their preview
  refresh path.

Downloads already debounce workspace-form saves; social publishing already
separates account, post-option and progress notifications. These mechanisms were
retained and covered by regression tests instead of replacing their persistence
or queue semantics.

## Verification

Native Qt tests cover stable dropdown models, independent choices, narrow UI,
100 metadata changes without timeline resets, capability invalidation, missing
preview samples, inventory-only option reads, worker exceptions, rapid project
switching and shutdown with work in flight. A deliberately blocked tool-state
calculation leaves the Qt timer/event loop responsive and coalesces 100 requests
to the first plus the latest; it does not launch 100 background calculations.

These are controlled responsiveness and regression tests, not a universal FPS
guarantee or a benchmark of the user's currently running app/GPU workloads.
No paid translation requests, video processing or social posts are triggered.
