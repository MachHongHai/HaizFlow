"""Shared storage limits used by runtime caches and release packaging."""

from __future__ import annotations


GIB_BYTES = 1024**3

# Manual artifacts are reusable, but must not consume the space Windows and
# FFmpeg need to complete a render safely.
MANUAL_PROJECT_SOFT_LIMIT_BYTES = 4 * GIB_BYTES
MANUAL_GLOBAL_SOFT_LIMIT_BYTES = 16 * GIB_BYTES
# Resource-pack installation and normal editor operations keep this reserve
# after their own staging/output estimates have been accounted for.
MINIMUM_OPERATIONAL_FREE_BYTES = 2 * GIB_BYTES

# The installer recommendation includes room for one Manual project's normal
# cache budget. Source media and exports remain user-owned data and are not
# bounded by this allowance.
INSTALLER_PROJECT_RESERVE_BYTES = 0
