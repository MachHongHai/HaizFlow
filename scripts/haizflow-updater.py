"""Independent updater SOURCE entrypoint; no Authenticode/signing key required."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haizflow.update.state import Layout
from haizflow.update.updater import run_request

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--request-token")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    try:
        if args.recover:
            layout = Layout(args.install_root)
            with layout.lock():
                print(layout.recover())
        elif args.request_token:
            run_request(args.install_root, args.request_token)
        else:
            parser.error("--request-token or --recover is required")
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
