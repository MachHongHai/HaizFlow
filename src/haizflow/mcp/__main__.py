"""Run with python -m haizflow.mcp or HaizFlowCore.exe --mcp-server."""

from __future__ import annotations

import argparse
import errno
import os
import stat
import sys


def _windows_pipe_tasks() -> set[str]:
    if sys.platform != "win32":
        return set()
    tasks = set()
    for stream, task in ((sys.stdin, "stdin_reader"), (sys.stdout, "stdout_writer")):
        try:
            if stat.S_ISFIFO(os.fstat(stream.fileno()).st_mode):
                tasks.add(task)
        except (AttributeError, OSError, ValueError):
            continue
    return tasks


def _closed_stdio_pipe(error: BaseException, windows_pipe_tasks: set[str]) -> bool:
    if not isinstance(error, OSError):
        return False
    traceback = error.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        task = frame.f_code.co_name
        # Only the SDK transport's I/O tasks can turn a broken pipe into a
        # successful exit. The same errno in a tool or during startup is real.
        if frame.f_globals.get("__name__") == "mcp.server.stdio" and task in {"stdin_reader", "stdout_writer"}:
            return (error.errno == errno.EPIPE
                    or getattr(error, "winerror", None) in {109, 232, 233}
                    # Windows CRT reports EINVAL when flushing an abandoned pipe.
                    or (task in windows_pipe_tasks and error.errno == errno.EINVAL))
        traceback = traceback.tb_next
    return False


def _run_stdio(server) -> None:
    windows_pipe_tasks = _windows_pipe_tasks()
    try:
        server.run()
    except ExceptionGroup as errors:
        closed, other = errors.split(lambda error: _closed_stdio_pipe(error, windows_pipe_tasks))
        if closed is None:
            raise
        if other is not None:
            raise other from None
    except OSError as error:
        if not _closed_stdio_pipe(error, windows_pipe_tasks):
            raise


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
    _run_stdio(server)
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
