# Responsive project deletion

## Findings

Delete used to enumerate the disk catalog before displaying confirmation.
After Yes, it synchronously validated the complete tree, deleted each video
workspace, and then deleted the project root on Qt's GUI thread. Deep-path
ownership checks were repeated for every file and for multiple deletion passes.
The recursive purge also held the project-index and shared artifact-pin locks.

## Changes

- Use the existing project/card video snapshot to open confirmation promptly.
- Keep that confirmation open after Yes, changing its button to “Đang xóa…”.
  Disable repeated confirmation, Cancel, X and Escape during deletion. Close
  only after the physical purge finishes, not merely after catalog detachment.
  Do not emit a separate deletion-in-progress alert. Preparation/worker failures
  release the dialog and retain the existing actionable error notification.
- Run ownership validation and recursive deletion in a background worker.
- Delete modern project-owned video/export/cache directories as one tree;
  retain explicit cleanup for legacy video workspaces outside that root.
- Briefly detach the exact owned directory into a uniquely named sibling.
  Validate before unlinking, commit the index, then purge without catalog/pin
  locks. Other projects remain accessible during file deletion.
- Journal the move before it happens. If interrupted before commit, startup
  restores the original directory; after commit it resumes the exact purge.
  Filesystem identity, containment, manifests, nested-project and reparse-point
  protections remain in force. Failed validation/commit does not delete data.
- Avoid duplicate commands, guard edits/processing for the deleting project,
  retry short Windows preview-handle locks in the worker, and clear busy state
  on failure. Completion updates Qt models only through the GUI dispatcher.
- Validate a tree in one traversal. Each parent is already verified, so there
  is no need to resolve/stat all its ancestors again for every child.

## Verification

Disposable benchmark: 1,500 small files under six cache levels. Old validation
was about 1.9–2.8 seconds; the new traversal was 0.006–0.007 seconds on this machine. This
measures validation only, not a universal full-deletion speedup. Actual removal
still depends on storage and Windows locks.

Delete also requests download/channel cancellation without waiting in the Qt
slot (the channel path previously waited up to ten seconds). Live workers keep
their files; the user can retry deletion once cancellation has finished.

Tests cover a blocked worker with prompt confirmation return, cancel/X,
duplicate clicks, a 1,000-video project requiring only one root removal,
concurrent catalog/pin access, nested projects/reparse points, external export
preservation, rollback, forced interruption, locked purge/recovery and replaced
cleanup-target identity. All destructive tests use disposable directories;
no real user project was deleted during development.

No build, push or publish was performed.
