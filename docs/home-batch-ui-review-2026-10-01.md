# Home, workspace navigation and Batch UI

## Changes

- Home now reuses the complete project browser, retaining the Home/Trang chủ label. Search, type and sort filters map through the same proxy model; the old recent-project layout is removed.
- The status dropdown is removed. Automatic, Manual and Batch project collections have dedicated sidebar entries, alongside Downloads and Publishing.
- Outside pointer presses clear search focus and selection without consuming the underlying button, card or context-menu click.
- Sidebar controls and project cards use Qt Controls' keyboard-only visual focus. Pointer focus uses `MouseFocusReason`; Tab and keyboard activation remain available. Repeated right-click/menu-close cycles do not leave a focus outline.
- Batch uses neutral import and progress surfaces, narrower adaptive import controls, a clearer empty state, and video drag/drop across the queue. Empty queues do not show a redundant 0/0 progress strip.

## Deletion and navigation

Browser deletion resolves the persisted project before confirmation. It does not open the browser row or modify its activity order. Deleting an unselected project refreshes the models without emitting the workspace-deletion signal. For the selected project, state cleanup is preserved; the UI deletion handlers only leave a workspace, never redirect a project browser or Home.

## Verification

- Pointer, keyboard and popup runtime tests cover search blur, New Project activation, card activation, repeated context-menu open/close and focus outlines.
- Main-window smoke checks emit deletion signals on Home, the all-project browser and the Automatic, Manual and Batch collections; each keeps its current route.
- Home and Batch were rendered and visually inspected at 1120×720 and 1440×900, using an isolated runtime without touching user projects.
- Regression results: 1,059 Python tests and 121 subtests passed; 60 existing Qt Quick tests passed. QML lint and Ruff F checks passed. The existing Pyannote/TorchCodec DLL warning remains; no test failed.
- This change does not modify the processing pipeline or export behavior. No installer/executable was built, and no changes were committed or pushed.
