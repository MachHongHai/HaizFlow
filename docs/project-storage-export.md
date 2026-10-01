# Project storage and video export

The folder chooser remains part of project creation. A remembered default only suggests a location for future projects. Existing projects are not relocated automatically.

## Three ownership boundaries

| Data | Owner and lifetime |
| --- | --- |
| Inputs, metadata, checkpoints and intermediate files | Project-owned; removed only by validated project operations. |
| Current revision render | App-managed immutable artifact in `videos/<id>/cache/manual/export/<signature>`; completion marker and SHA-256 validated. |
| Save As output | User-owned independent copy, outside every registered project root and legacy workspace. Never a preview source or checkpoint dependency. |

Automatic processing completes when its internal render is published, not when an external file is saved. Manual uses the same artifact store. A matching render is reused for export; a missing or stale render requires rendering from valid saved checkpoints rather than rerunning unrelated AI tools. Quality presets do not upscale smaller inputs.

## Save As and batch export

Select a preset and destination, then confirm. The default is `<project-name>.mp4`. File replacement needs explicit approval; if the approved target changes before publication, the operation stops. Copy workers write a temporary file on the destination volume, verify size and hashes against the immutable artifact, flush, then publish atomically. Cancellation, insufficient space or a locked destination affects the export job only, not the processing result.

Batch chooses one folder and uses stable `<source-name>--<video-id>.mp4` names. Missing renders appear as individual failures rather than being silently omitted. Retry addresses failed/cancelled copies; completing missing processing remains a separate action. Changing an approved overwrite target requires new confirmation.

Social import pins an internal render until it has been copied to publishing-owned media. It does not depend on external export history. Rename changes the display name while retaining IDs, roots, files and checkpoints. Index writes are canonical; a failed manifest mirror is repaired on subsequent reading.

## Cleanup and compatibility

Inactive artifacts share bounded cache maintenance. Current artifacts, runtime pins and their dependencies are retained. Links, Windows junctions/reparse points, nested project manifests and ambiguous ownership stop destructive operations. Active copy/render leases prevent project deletion. External exports and shared models are not project deletion targets.

Legacy workspaces remain readable and writable in place. A provably project-owned legacy MP4 can be verified and copied into the artifact store; it is never moved. A missing legacy output is nonfatal. Missing/offline project roots remain indexed and opening reports the problem instead of creating an empty replacement. There is no automatic root relocation tool.

Video schema 19 adds presets/export history with defaults and a schema migration backup; newer unknown schemas are rejected. Project schema remains 4. Updates retain the full-installer mechanism, not delta patching.

## Verification and remaining limits

Regression tests cover cancellation, disk/lock errors, overwrite races, SHA tampering, stale revisions, deletion boundaries, stable rename, schema migration, offline roots, Windows junctions and sharing locks. A generated MP4 was probed for unchanged 320×180 dimensions and stereo 48 kHz audio after export. D: to C: copy and later project deletion were exercised. These tests do not measure perceptual quality on long real videos or verify every physical storage failure.

Abrupt process termination or drive disconnection can leave a hidden `.haizflow-export-*.partial` file. Normal cancellation removes it; no broad sweep of user folders is performed. Copy-job history is not a durable resumable transfer journal. Hard power loss, physical unplug, NAS/UNC storage, very long video render and installer upgrade rollback have not been exercised in this change. No installer was built or released.

Tests: [filesystem/export regressions](../tests/test_render_export_storage.py), [export dialog](../tests/qml/tst_VideoExportDialog.qml), [rename dialog](../tests/qml/tst_ProjectRenameDialog.qml). Test runners isolate runtime paths from real projects.
