# Project browser stability after deletion

## Cause and change

- `ProjectListModel.set_projects()` reset the entire model when a project key disappeared. Qt discarded the browser's visible delegates and scroll position. This reset also exists in the source tagged `v1.0.4`; no claim is made that packaging alone explains the user's different experience in the installed EXE.
- Deletion-only catalog changes now emit contiguous `rowsRemoved` ranges, keeping surviving persistent indexes, role snapshots, proxy filters and cards intact. Creation/reordering retains its existing behavior.
- Catalog refresh no longer emits `selectedVideoChanged` when the selected video's metadata is unchanged. Actual selection/data changes still notify normally.
- Background storage deletion, confirmation behavior, ownership validation and stale catalog revision checks are unchanged.

## Verification

- A Qt Quick GridView test with 100 projects was run against the `v1.0.4` model method in an isolated Python process: removing an off-screen project reset `contentY` from `500` to `0`.
- The same test against the updated model preserves `contentY=500` and creates no replacement visible delegates.
- Tests include first/middle/last/noncontiguous/all-row removal, persistent indexes, typed models, filtered/sorted proxies, surviving role updates, unchanged versus changed editor metadata, and rejection of a stale in-flight catalog snapshot.
- Focused suite: **70 passed, 1 skipped** (`build/project-deletion-focused-20261113.xml`).
- Wider suite: **184 passed, 1 skipped, 1 failed**, plus 2 passing subtests (`build/project-deletion-catalog-20261113.xml`). The failure is an unrelated existing string assertion in `test_batch_page_exposes_settings_resume_and_bottom_progress`, expecting the old batch-card height expression `+64` instead of the current `+78` used for its delete action. No batch UI changes were made for this fix.
- Ruff undefined/import checks and `git diff --check` pass.

Tests use synthetic models and isolated temporary storage. No real user project was deleted. No build, push or publish was performed.
