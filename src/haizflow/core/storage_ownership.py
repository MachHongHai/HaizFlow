"""Fail-closed filesystem ownership checks, including Windows junctions."""

import os
import stat
import threading
from pathlib import Path

# Serialize pin acquisition with destructive managed-storage operations. Never
# hold this for the duration of a media copy: the pin is the long-lived lease.
managed_storage_guard = threading.RLock()


def is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
    )


def owned_path(path, root, *, allow_root: bool = False) -> Path:
    """Require both lexical and physical containment, with no redirects below root.

    The user-selected parent may itself be a mapped location. The managed root
    and every child must be ordinary entries; metadata alone never grants ownership.
    """
    candidate, owner = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    try:
        relative = candidate.relative_to(owner)
        physical = candidate.resolve().relative_to(owner.resolve())
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValueError("Path is outside the managed storage root.") from exc
    if not allow_root and (not relative.parts or not physical.parts):
        raise ValueError("The managed root itself is not a file target.")
    current = owner
    for part in (None, *relative.parts):
        if part is not None:
            current /= part
        if is_reparse(current):
            raise ValueError("Managed storage contains a symlink or Windows reparse point.")
        if current != owner and current.is_dir() and (current / ".haizflow-project.json").is_file():
            raise ValueError("Path belongs to a nested project, not this storage owner.")
    return candidate


def safe_tree(root) -> Path:
    """Preflight a recursive removal without following links or nested projects."""
    owner = Path(os.path.abspath(root))
    owned_path(owner, owner, allow_root=True)
    pending = [owner]
    while pending:
        directory = pending.pop()
        if directory != owner:
            # Check directory ancestry again immediately before descending;
            # a queued directory must not have become a junction meanwhile.
            owned_path(directory, owner)
        with os.scandir(directory) as entries:
            for entry in entries:
                # The parent has already been checked. Re-resolving every
                # ancestor for every file made long-project cleanup O(N*depth)
                # in filesystem calls. Inspect each entry once, without ever
                # following a link or Windows junction.
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or bool(
                    getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
                ):
                    raise ValueError("Managed storage contains a symlink or Windows reparse point.")
                if entry.name == ".haizflow-project.json" and directory != owner:
                    raise ValueError("Cleanup blocked: another project is nested inside this storage root.")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
    return owner
