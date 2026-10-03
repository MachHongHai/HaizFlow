"""Independent launcher SOURCE entrypoint; not a standalone executable yet."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haizflow.update.launcher import launch

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path,
                        default=Path(sys.executable).parent if getattr(sys, "frozen", False) else None)
    parser.add_argument("--health-timeout", type=float, default=90)
    args = parser.parse_args()
    if args.install_root is None:
        parser.error("Source launcher requires --install-root")
    try:
        raise SystemExit(launch(args.install_root, timeout=args.health_timeout))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
