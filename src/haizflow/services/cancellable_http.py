"""Request-local HTTP interruption; never install a process-wide urllib opener."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from http.client import HTTPConnection, HTTPSConnection
from urllib import request

from haizflow.pipeline.process_registry import check_cancellation

_LOCAL = threading.local()
_POLL_SECONDS = 0.05


class _RequestControl:
    def __init__(self):
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.sockets: list[socket.socket] = []

    def check(self):
        if self.stopped.is_set():
            raise RuntimeError("Video cancelled by user.")

    @staticmethod
    def _close(sock):
        # close() alone can leave another thread's buffered read blocked.
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def watch(self, sock):
        if sock is None:
            return
        with self.lock:
            stopped = self.stopped.is_set()
            if not stopped:
                self.sockets.append(sock)
        if stopped:
            self._close(sock)
            self.check()

    def abort(self):
        with self.lock:
            self.stopped.set()
            sockets, self.sockets = self.sockets, []
        for sock in sockets:
            self._close(sock)


class _TrackedConnection:
    def __init__(self, *args, control, **kwargs):
        self._request_control = control
        super().__init__(*args, **kwargs)
        create_connection = self._create_connection

        def connect_socket(*connect_args, **connect_kwargs):
            control.check()
            sock = create_connection(*connect_args, **connect_kwargs)
            control.watch(sock)
            return sock

        self._create_connection = connect_socket

    def connect(self):
        self._request_control.check()
        super().connect()
        # HTTPS wraps/detaches the original TCP socket. Track its TLS owner too.
        self._request_control.watch(self.sock)


class _HTTPConnection(_TrackedConnection, HTTPConnection):
    pass


class _HTTPSConnection(_TrackedConnection, HTTPSConnection):
    pass


class _HTTPHandler(request.HTTPHandler):
    def __init__(self, control):
        super().__init__()
        self.control = control

    def http_open(self, req):
        return self.do_open(lambda *args, **kwargs: _HTTPConnection(*args, control=self.control, **kwargs), req)


class _HTTPSHandler(request.HTTPSHandler):
    def __init__(self, control):
        super().__init__()
        self.control = control

    def https_open(self, req):
        return self.do_open(
            lambda *args, **kwargs: _HTTPSConnection(*args, control=self.control, **kwargs), req, context=self._context
        )


def handlers() -> list:
    """Preserve proxy/TLS/redirect policy; track only this operation's sockets."""
    control = getattr(_LOCAL, "control", None)
    return [_HTTPHandler(control), _HTTPSHandler(control)] if control is not None else []


def check_active() -> None:
    """A stopped attempt stays stopped even if a newer run clears the video flag."""
    control = getattr(_LOCAL, "control", None)
    if control is not None:
        control.check()


def run[T](video_id: str, operation: Callable[[], T], *, check: Callable[[], None] | None = None) -> T:
    """Interrupt waiting headers/body/backoff without waiting for the provider timeout.

    The worker only produces an in-memory result, never publishes checkpoints.
    DNS/TLS setup may finish later on some platforms; its request-local stop flag
    prevents it from sending a late POST. No retries or provider switching here.
    """
    if not video_id:
        return operation()
    check = check or (lambda: check_cancellation(video_id))
    check()
    control = _RequestControl()
    done = threading.Event()
    outcome: list[tuple[bool, object]] = []

    def execute():
        _LOCAL.control = control
        try:
            outcome.append((True, operation()))
        except BaseException as exc:
            outcome.append((False, exc))
        finally:
            control.abort()
            del _LOCAL.control
            done.set()

    worker = threading.Thread(target=execute, name="haizflow-translation-http", daemon=True)
    worker.start()
    try:
        while not done.wait(_POLL_SECONDS):
            try:
                check()
            except Exception:
                # A fully received batch wins the race: its caller can save
                # the paid result before honoring Pause at the next boundary.
                if done.is_set():
                    break
                raise
    except BaseException:
        control.abort()
        worker.join(timeout=0.2)
        raise
    succeeded, value = outcome[0]
    if not succeeded:
        raise value
    return value
