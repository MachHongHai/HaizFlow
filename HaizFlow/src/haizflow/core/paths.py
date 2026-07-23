import os
import sys
from pathlib import Path

APP_NAME = "HaizFlow"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_overrides_allowed() -> bool:
    """Whether test/source runs may redirect HaizFlow-owned runtime paths.

    A released executable is portable: the folder containing ``HaizFlow.exe``
    is the only root it may use for mutable data. Inherited machine variables
    must not redirect it back to ``C:\\Users\\...`` after a user selected a
    different installation drive. Frozen smoke tests deliberately opt out so
    they can use an isolated temporary directory.
    """
    return not is_frozen() or os.getenv("HAIZFLOW_SMOKE_TEST") == "1"


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return project_root()


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def source_root() -> Path:
    return package_root().parent


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return source_root().parent


def install_root() -> Path:
    """Directory selected for the application installation.

    Source builds and frozen smoke tests may use an explicit override. A real
    frozen release always uses the directory containing the executable, which
    is the folder selected in the installer.
    """
    override = os.getenv("HAIZFLOW_INSTALL_ROOT")
    if override and runtime_overrides_allowed():
        return Path(override).expanduser().resolve()
    return project_root()


def app_data_dir() -> Path:
    if not runtime_overrides_allowed():
        return project_root() / "runtime"
    override = os.getenv("HAIZFLOW_HOME") or os.getenv("APP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    # Portable-by-default layout: installer location determines where every
    # HaizFlow-owned mutable file is written. This also prevents silent writes
    # to the Windows system drive when the user installs on another drive.
    return install_root() / "runtime"


def runtime_data_dir() -> Path:
    """All mutable app-level data: settings, diagnostics, model caches, and project index."""
    if not runtime_overrides_allowed():
        return app_data_dir() / "data"
    override = os.getenv("RUNTIME_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        candidate = path.resolve() if path.is_absolute() else (app_data_dir() / path).resolve()
        home_override = os.getenv("HAIZFLOW_HOME")
        if (
            home_override
            and os.getenv("HAIZFLOW_SMOKE_TEST") != "1"
            and not candidate.is_relative_to(Path(home_override).expanduser().resolve())
        ):
            return app_data_dir() / "data"
        return candidate
    return app_data_dir() / "data"


def legacy_runtime_data_dir() -> Path:
    """Source-mode data directory used by versions before offline storage separation."""
    return project_root() / "data"


def models_dir() -> Path:
    if not runtime_overrides_allowed():
        return app_data_dir() / "models"
    override = os.getenv("MODELS_DIR")
    if override:
        path = Path(override).expanduser()
        candidate = path.resolve() if path.is_absolute() else (app_data_dir() / path).resolve()
        home_override = os.getenv("HAIZFLOW_HOME")
        if home_override and not candidate.is_relative_to(Path(home_override).expanduser().resolve()):
            return app_data_dir() / "models"
        return candidate
    return app_data_dir() / "models"


def storage_dir() -> Path:
    """Legacy pre-project-first video workspace location, retained for migration."""
    # Historical releases called processing records "jobs" and stored them in
    # this directory. The literal path must remain readable until migration.
    return runtime_data_dir() / "jobs"


def cache_dir() -> Path:
    return runtime_data_dir() / "cache"


def logs_dir() -> Path:
    return runtime_data_dir() / "logs"


def bin_dir() -> Path:
    if not runtime_overrides_allowed():
        # Bundled binaries are immutable release payload, beside the selected
        # installation directory. Do not prefer a machine-wide BIN_DIR value.
        return (bundle_root() / "bin").resolve()
    override = os.getenv("BIN_DIR")
    if override:
        return Path(override).expanduser().resolve()

    candidates = [
        project_root() / "runtime" / "bin",
        project_root() / "bin",
        bundle_root() / "bin",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()
