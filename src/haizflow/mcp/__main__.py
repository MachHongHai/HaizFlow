"""Run with python -m haizflow.mcp or HaizFlowCore.exe --mcp-server."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HaizFlow local MCP stdio server")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--tool-profile", choices=("full", "compact"), default="full")
    args = parser.parse_args(argv)
    from PySide6.QtCore import QCoreApplication

    from .client import DesktopClient
    from .server import create_server

    app = QCoreApplication.instance() or QCoreApplication(["HaizFlow MCP"])
    server = create_server(DesktopClient(args.endpoint), tool_profile=args.tool_profile)
    server.run()
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
