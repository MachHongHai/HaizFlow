"""Real stalled HTTP/TLS connections; no API key, inference, or user data."""

import datetime
import ipaddress
import json
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import pytest

from haizflow.pipeline import process_registry as registry
from haizflow.services import api_translation as api
from haizflow.services import cancellable_http
from haizflow.services import gemini_translation as gemini


@pytest.fixture
def tls_contexts(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "test-cert.pem", tmp_path / "test-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    return server_context, ssl.create_default_context(cafile=str(cert_path))


@pytest.mark.parametrize(
    "provider,phase",
    [
        (provider, phase)
        for provider in ("gemini", "openai", "deepseek", "openrouter", "custom")
        for phase in ("headers", "body", "error_body")
        if phase != "error_body" or provider in ("gemini", "openrouter")
    ],
)
@pytest.mark.parametrize("tls", [False, True], ids=["http", "https"])
def test_pause_interrupts_waiting_network_without_retry_or_late_result(
    monkeypatch,
    request,
    provider,
    phase,
    tls,
):
    entered, disconnected = threading.Event(), threading.Event()
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            received.append(self.path)
            if phase != "headers":
                self.send_response(429 if phase == "error_body" else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b'{"error":' if phase == "error_body" else b'{"candidates":')
                self.wfile.flush()
            entered.set()
            self.connection.settimeout(4)
            try:
                if self.connection.recv(1) == b"":
                    disconnected.set()
            except (ConnectionError, OSError):
                disconnected.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if tls:
        server_context, client_context = request.getfixturevalue("tls_contexts")
        server.socket = server_context.wrap_socket(server.socket, server_side=True)
        monkeypatch.setattr(ssl, "_create_default_https_context", lambda: client_context)
    server_thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    server_thread.start()
    url = f"{'https' if tls else 'http'}://127.0.0.1:{server.server_port}"
    key = "pause-network-fixture"
    registry.start_video(key)
    monkeypatch.setattr(gemini, "log_to_video", Mock())
    monkeypatch.setattr(api, "log_to_video", Mock())
    failures, values = [], []

    def translate():
        try:
            arguments = dict(
                key="not-a-real-key",
                model="gemini-3.1-flash-lite",
                source_language="English",
                target_language="Vietnamese",
                video_id=key,
            )
            if provider == "gemini":
                values.append(gemini._request_chunk([(0, "Hello")], **arguments))
            else:
                profile = dict(provider=provider, model="vendor/chat-probe", base_url=url, format="json_object")
                values.append(
                    api._request_chunk(
                        profile,
                        [(0, "Hello")],
                        **arguments,
                        _protocol={"supported_parameters": [], "output_format": "prompt"},
                    )
                )
        except Exception as exc:
            failures.append(str(exc))

    monkeypatch.setattr(gemini, "_ENDPOINT", url + "/{model}")
    worker = threading.Thread(target=translate)
    previous_http_workers = set(threading.enumerate())
    try:
        worker.start()
        assert entered.wait(3), failures
        started = time.perf_counter()
        registry.pause_video(key)
        worker.join(1)
        elapsed = time.perf_counter() - started
        assert not worker.is_alive()
        assert elapsed < 0.8, elapsed
        print(f"pause {provider} {phase} {'TLS' if tls else 'HTTP'}: {elapsed * 1000:.1f} ms")
        assert disconnected.wait(1), "Cancellation must close the real socket, not just hide the busy UI"
        for http_worker in set(threading.enumerate()) - previous_http_workers:
            if http_worker.name == "haizflow-translation-http":
                http_worker.join(0.1)
                assert not http_worker.is_alive()
        assert failures == ["Video cancelled by user."]
        assert values == []
        assert len(received) == 1
        registry.prepare_video_resume(key)
        time.sleep(0.06)
        assert len(received) == 1  # No old retry after a newer run clears the video flag.
    finally:
        registry.pause_video(key)
        worker.join(2)
        server.shutdown()
        server.server_close()
        server_thread.join(1)
        registry.clean_video(key)


def test_stop_while_connecting_prevents_a_late_post_even_after_resume(monkeypatch):
    started, release = threading.Event(), threading.Event()
    sent = []
    failures = []
    key = "pause-dns-fixture"
    registry.start_video(key)

    def delayed_connect(*_args, **_kwargs):
        started.set()
        release.wait(3)
        return Mock(spec=socket.socket)

    monkeypatch.setattr(socket, "create_connection", delayed_connect)

    def operation():
        connection = cancellable_http._HTTPConnection("example.invalid", control=cancellable_http._LOCAL.control)
        connection.connect()
        sent.append(True)

    def run():
        try:
            cancellable_http.run(key, operation)
        except Exception as exc:
            failures.append(str(exc))

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert started.wait(1)
        registry.pause_video(key)
        worker.join(1)
        assert not worker.is_alive()
        registry.prepare_video_resume(key)
        release.set()
        time.sleep(0.1)
        assert not sent
        assert failures == ["Video cancelled by user."]
    finally:
        release.set()
        worker.join(2)
        registry.clean_video(key)


def test_already_completed_response_is_kept_at_pause_boundary():
    paused = False

    def operation():
        nonlocal paused
        paused = True
        return ["Chào bạn"]

    def check():
        if paused:
            raise RuntimeError("Video cancelled by user.")

    assert cancellable_http.run("completed-fixture", operation, check=check) == ["Chào bạn"]


def test_pause_latency_compared_with_previous_blocking_transport(monkeypatch):
    gates = []
    entered = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            gate = gates[-1]
            entered.set()
            gate.wait(3)
            body = json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps({"translations": [{"id": 0, "text": "Chào bạn"}]})},
                        }
                    ]
                }
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    server_thread.start()
    monkeypatch.setattr(api, "log_to_video", Mock())
    profile = dict(
        provider="custom",
        model="local-fixture",
        format="json_object",
        base_url=f"http://127.0.0.1:{server.server_port}",
    )
    timings, failures = [], []
    try:
        for implementation in (api._request_chunk_sync, api._request_chunk):
            key = "pause-latency-fixture"
            registry.start_video(key)
            gate = threading.Event()
            gates.append(gate)
            entered.clear()

            def run():
                try:
                    implementation(
                        profile,
                        [(0, "Hello")],
                        key="dummy",
                        model="gemini-3.1-flash-lite",
                        source_language="English",
                        target_language="Vietnamese",
                        video_id=key,
                    )
                except RuntimeError as exc:
                    failures.append(str(exc))

            worker = threading.Thread(target=run)
            worker.start()
            assert entered.wait(2), failures
            release = threading.Timer(0.8, gate.set)
            release.start()
            started = time.perf_counter()
            registry.pause_video(key)
            worker.join(2)
            timings.append(time.perf_counter() - started)
            gate.set()
            release.cancel()
            release.join(1)
            assert not worker.is_alive()
            registry.clean_video(key)
        previous, improved = timings
        print(f"A/B pause same endpoint: blocking={previous * 1000:.1f} ms, cancellable={improved * 1000:.1f} ms")
        assert previous >= 0.6
        assert improved < 0.35
        assert previous > improved * 2.5
        assert failures == ["Video cancelled by user."]
    finally:
        for gate in gates:
            gate.set()
        server.shutdown()
        server.server_close()
        server_thread.join(1)
        registry.clean_video("pause-latency-fixture")
