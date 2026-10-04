"""Independent launcher entrypoint with installer initialization and recovery UI."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haizflow.update.launcher import launch
from haizflow.update.bootstrap import initialize, report_error

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path,
                        default=Path(sys.executable).parent if getattr(sys, "frozen", False) else None)
    parser.add_argument("--health-timeout", type=float, default=90)
    parser.add_argument("--initialize", help="Initialize/upgrade to an installer-verified Core")
    parser.add_argument("--ui-smoke-test", action="store_true")
    args = parser.parse_args()
    if args.install_root is None:
        parser.error("Source launcher requires --install-root")
    try:
        if args.initialize:
            initialize(args.install_root, args.initialize)
            raise SystemExit(0)
        command_for = (lambda core: [str(core / "HaizFlowCore.exe"), "--ui-smoke-test"]) if args.ui_smoke_test else None
        raise SystemExit(launch(args.install_root, timeout=args.health_timeout, command_for=command_for))
    except (OSError, ValueError) as error:
        report_error(str(error))
        raise SystemExit(1)
