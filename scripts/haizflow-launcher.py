"""Independent launcher entrypoint with installer initialization and recovery UI."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haizflow.update.launcher import launch
from haizflow.update.bootstrap import check_install, initialize, uninstall_cores, report_error

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path,
                        default=Path(sys.executable).parent if getattr(sys, "frozen", False) else None)
    parser.add_argument("--health-timeout", type=float, default=90)
    parser.add_argument("--initialize", help="Initialize/upgrade to an installer-verified Core")
    parser.add_argument("--check-install", help="Check an existing installation before copying any files")
    parser.add_argument("--ui-smoke-test", action="store_true")
    parser.add_argument("--uninstall-cores", action="store_true")
    args = parser.parse_args()
    if args.install_root is None:
        parser.error("Source launcher requires --install-root")
    from haizflow.startup_splash import start, finish, opening_interface
    if not (args.check_install or args.uninstall_cores or args.initialize or args.ui_smoke_test):
        start(settings_path=args.install_root / "runtime/data/desktop-settings.json",
              icon_path=Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "haizflow.ico")
    try:
        if args.check_install:
            check_install(args.install_root, args.check_install)
            raise SystemExit(0)
        if args.uninstall_cores:
            uninstall_cores(args.install_root)
            raise SystemExit(0)
        if args.initialize:
            initialize(args.install_root, args.initialize)
            raise SystemExit(0)
        command_for = (lambda core: [str(core / "HaizFlowCore.exe"), "--ui-smoke-test"]) if args.ui_smoke_test else None
        raise SystemExit(launch(args.install_root, timeout=args.health_timeout, command_for=command_for,
                                on_ready=finish, on_starting=opening_interface))
    except (OSError, ValueError) as error:
        finish()
        report_error(str(error), show_dialog=not (args.ui_smoke_test or args.initialize or args.uninstall_cores or args.check_install))
        raise SystemExit(1)
    finally:
        finish()
