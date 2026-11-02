"""Opt-in per-user named pipe. Every operation runs on the GUI thread."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Property, QLockFile, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from haizflow.mcp.protocol import (
    MAX_REQUEST,
    MAX_RESPONSE,
    PROTOCOL_VERSION,
    default_endpoint,
    encode_frame,
    launch_configuration,
)


class McpBridge(QObject):
    changed = Signal()
    _connectionResult = Signal(int, object)

    def __init__(self, host, *, endpoint=None, dispatcher=None):
        super().__init__(host)
        self.host = host
        self.endpoint = endpoint or default_endpoint()
        self._server = None
        self._endpoint_lock = None
        self._connections = {}
        self._replies = OrderedDict()
        self._dispatching = False
        self._permissions = {"write": False, "online": False, "delete": False, "publish": False}
        self._error = ""
        self._connection_state = "idle"
        self._connection_message = ""
        self._connection_generation = 0
        self._connection_cancel = None
        self._connectionResult.connect(self._connection_checked)
        if dispatcher is None:
            from haizflow.desktop.mcp_commands import McpCommands

            dispatcher = McpCommands(host, self).dispatch
        self._dispatcher = dispatcher

    @Property(bool, notify=changed)
    def enabled(self):
        return self._server is not None

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property("QVariantMap", notify=changed)
    def permissions(self):
        return dict(self._permissions)

    @Property(str, notify=changed)
    def connectionState(self):
        return self._connection_state

    @Property(str, notify=changed)
    def connectionMessage(self):
        return self._connection_message

    @Property("QVariantMap", notify=changed)
    def launchDetails(self):
        entry = json.loads(self.configuration("generic"))["mcpServers"]["haizflow"]
        return {"name": "haizflow", "transport": "STDIO", "command": entry["command"],
                "arguments": "\n".join(entry["args"])}

    @Property(str, notify=changed)
    def setupPrompt(self):
        return self.tr(
            "Hãy thêm máy chủ MCP cục bộ tên haizflow vào ứng dụng agent này bằng cấu hình stdio bên dưới. "
            "Giữ nguyên các server khác; nếu đã có haizflow thì chỉ cập nhật mục đó. "
            "Không gọi API, xử lý, xóa hay đăng video trong lúc kết nối. "
            "Sau khi kết nối, gọi haizflow_status để xác minh.\n\n"
        ) + self.configuration("generic")

    @Property("QVariantMap", notify=changed)
    def approval(self):
        return {}  # Compatibility for older status clients; no UI approval workflow.

    @Slot(bool, result=bool)
    def setEnabled(self, enabled):
        if enabled and self.enabled:
            # Refreshes must not restore permissions the user explicitly revoked.
            return True
        self.close()
        self._error = ""
        if enabled:
            self._open_endpoint()
        self.changed.emit()
        return self.enabled == bool(enabled)

    def _open_endpoint(self):
        from haizflow.config import RUNTIME_DATA_DIR

        # Windows named pipes allow multiple server instances with the same
        # name. QLocalServer.listen() alone does not enforce exclusive ownership.
        try:
            lock_path = Path(RUNTIME_DATA_DIR) / "mcp" / f"{self.endpoint}.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(lock_path))
            lock.setStaleLockTime(0)  # A live app can legitimately own this lock for hours.
            if not lock.tryLock(0):
                if lock.error() == QLockFile.LockError.LockFailedError:
                    self._error = self.tr("Không thể mở MCP. Kiểm tra cửa sổ HaizFlow khác đang dùng cùng dữ liệu.")
                else:
                    self._error = self.tr(
                        "Không thể tạo khóa MCP trong thư mục dữ liệu. Kiểm tra quyền ghi và dung lượng ổ đĩa."
                    )
                return
        except OSError:
            self._error = self.tr(
                "Không thể tạo khóa MCP trong thư mục dữ liệu. Kiểm tra quyền ghi và dung lượng ổ đĩa."
            )
            return
        self._endpoint_lock = lock
        probe = QLocalSocket()
        try:
            # Also detect an older HaizFlow build that does not use a lock file.
            probe.connectToServer(self.endpoint)
            occupied = probe.waitForConnected(100)
        finally:
            probe.abort()
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.UserAccessOption)
        server.setMaxPendingConnections(8)
        if occupied or not server.listen(self.endpoint):
            self._error = self.tr("Không thể mở MCP. Kiểm tra cửa sổ HaizFlow khác đang dùng cùng dữ liệu.")
            server.deleteLater()
            self._endpoint_lock.unlock()
            self._endpoint_lock = None
            return
        self._server = server
        self._permissions = dict.fromkeys(self._permissions, True)
        server.newConnection.connect(self._accept)

    @Slot(str, bool)
    def setPermission(self, name, enabled):
        if name not in self._permissions or not self.enabled:
            return
        self._permissions[name] = bool(enabled)
        if name == "write" and not enabled:
            self._permissions = dict.fromkeys(self._permissions, False)
        if name != "write" and enabled:
            self._permissions["write"] = True
        self.changed.emit()

    @Slot(str, result=str)
    def configuration(self, client):
        return launch_configuration(self.endpoint, client)

    @Slot(str)
    def copyConfiguration(self, client):
        QGuiApplication.clipboard().setText(self.configuration(client))

    @Slot(str)
    def copyLaunchField(self, field):
        if field in {"name", "command", "arguments"}:
            QGuiApplication.clipboard().setText(self.launchDetails[field])

    @Slot()
    def copySetupPrompt(self):
        QGuiApplication.clipboard().setText(self.setupPrompt)

    @Slot(result=bool)
    def testConnection(self):
        if self._connection_state == "checking":
            return False
        if not self.enabled:
            self._connection_state = "error"
            self._connection_message = self.tr("Bật MCP cục bộ trước khi kiểm tra kết nối.")
            self.changed.emit()
            return False
        self._connection_generation += 1
        generation, endpoint = self._connection_generation, self.endpoint
        cancelled = threading.Event()
        self._connection_cancel = cancelled
        self._connection_state = "checking"
        self._connection_message = self.tr("Đang kiểm tra giao thức MCP và kết nối tới HaizFlow…")
        self.changed.emit()

        def work():
            from haizflow.mcp.diagnostics import check_connection

            result = check_connection(endpoint, cancelled)
            try:
                self._connectionResult.emit(generation, result)
            except RuntimeError:
                pass  # The owning window was destroyed during shutdown.

        threading.Thread(target=work, name="HaizFlow MCP connection check", daemon=True).start()
        return True

    @Slot(int, object)
    def _connection_checked(self, generation, result):
        if generation != self._connection_generation or not self.enabled:
            return
        self._connection_cancel = None
        self._connection_state = "success" if result.get("ok") else "error"
        if result.get("ok"):
            self._connection_message = self.tr(
                "MCP cục bộ hoạt động · %1 công cụ. Đây là kiểm tra nội bộ; "
                "hãy gọi haizflow_status trong agent để xác minh kết nối từ agent."
            ).replace("%1", str(result["tools"]))
        elif result.get("reason") == "timeout":
            self._connection_message = self.tr("Kiểm tra MCP quá thời gian. Thử lại khi app đã phản hồi bình thường.")
        else:
            self._connection_message = self.tr(
                "Chưa kiểm tra được MCP. Giữ HaizFlow mở, kiểm tra đường dẫn bản app và thử lại."
            )
        self.changed.emit()

    def require(self, permission):
        if not self.enabled or not self._permissions.get(permission, False):
            raise ValueError(f"Enable MCP '{permission}' permission in HaizFlow Settings for this session.")


    def close(self):
        self._connection_generation += 1
        if self._connection_cancel:
            self._connection_cancel.set()
            self._connection_cancel = None
        self._connection_state = "idle"
        self._connection_message = ""
        for socket in tuple(self._connections):
            socket.abort()
        self._connections.clear()
        if self._server:
            self._server.close()
            self._server.deleteLater()
            self._server = None
        if self._endpoint_lock:
            self._endpoint_lock.unlock()
            self._endpoint_lock = None
        self._permissions = dict.fromkeys(self._permissions, False)
        self._replies.clear()
        self.changed.emit()

    def _accept(self):
        while self._server and self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if len(self._connections) >= 8:
                socket.abort()
                socket.deleteLater()
                continue
            socket.setReadBufferSize(MAX_REQUEST + 1)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.setInterval(5000)
            timer.timeout.connect(socket.abort)
            self._connections[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket, t=timer: self._read(s, t))
            socket.disconnected.connect(lambda s=socket: self._release(s))
            timer.start()
            self._read(socket, timer)

    def _release(self, socket):
        self._connections.pop(socket, None)
        socket.deleteLater()

    def _read(self, socket, timer):
        buffer = self._connections.get(socket)
        if buffer is None:
            return
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > MAX_REQUEST:
            socket.abort()
            return
        if b"\n" not in buffer:
            return
        timer.stop()
        request_id = ""
        try:
            if buffer.count(b"\n") != 1 or not buffer.endswith(b"\n"):
                raise ValueError("One request per connection is required.")
            request = json.loads(buffer)
            if not isinstance(request, dict) or set(request) != {"version", "id", "method", "params"}:
                raise ValueError("Invalid request envelope.")
            request_id = request["id"]
            if (
                request["version"] != PROTOCOL_VERSION
                or not isinstance(request_id, str)
                or not 1 <= len(request_id) <= 80
                or not isinstance(request["method"], str)
                or not isinstance(request["params"], dict)
            ):
                raise ValueError("Invalid request envelope.")
            digest = hashlib.sha256(buffer).digest()
            cached = self._replies.get(request_id)
            if cached:
                if cached[0] != digest:
                    raise ValueError("Request ID already used for another operation.")
                if cached[2] != self._permissions:
                    raise ValueError("MCP permissions changed since this request. Read app status first.")
                frame = cached[1]
            else:
                if self._dispatching or not self.enabled:
                    raise ValueError("HaizFlow is handling another MCP action. Check status before retrying.")
                self._dispatching = True
                try:
                    result = self._dispatcher(request["method"], request["params"])
                finally:
                    self._dispatching = False
                frame = encode_frame({"version": PROTOCOL_VERSION, "id": request_id, "result": result}, MAX_RESPONSE)
                self._replies[request_id] = (digest, frame, dict(self._permissions))
                while (
                    len(self._replies) > 128 or sum(len(reply[1]) for reply in self._replies.values()) > 8 * MAX_REQUEST
                ):
                    self._replies.popitem(last=False)
        except ValueError as exc:
            frame = encode_frame(
                {"version": PROTOCOL_VERSION, "id": request_id, "error": str(exc)[:2000]}, MAX_RESPONSE
            )
        except Exception:
            # Do not leak credentials embedded in exception messages or URL query strings.
            frame = encode_frame(
                {
                    "version": PROTOCOL_VERSION,
                    "id": request_id,
                    "error": "HaizFlow could not perform the action. Review the app's technical log.",
                },
                MAX_RESPONSE,
            )
        socket.write(frame)
        socket.disconnectFromServer()
        self._connections.pop(socket, None)
