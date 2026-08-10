import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from haizflow.services import zernio


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


class _UploadResponse:
    status = 200

    @staticmethod
    def read():
        return b""


class _Connection:
    instances = []

    def __init__(self, host, port=None, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.target = ""
        self.headers = {}
        self.body = bytearray()
        self.closed = False
        self.__class__.instances.append(self)

    def putrequest(self, method, target):
        self.method = method
        self.target = target

    def putheader(self, name, value):
        self.headers[name] = value

    def endheaders(self):
        pass

    def send(self, chunk):
        self.body.extend(chunk)

    @staticmethod
    def getresponse():
        return _UploadResponse()

    def close(self):
        self.closed = True


class ZernioClientTests(unittest.TestCase):
    def setUp(self):
        self.key = "sk_" + "a" * 64

    def test_create_post_uses_bearer_auth_idempotency_and_tiktok_consent(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response({"data": {"post": {"id": "post-1", "status": "publishing"}}})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            result = zernio.ZernioClient(self.key).create_tiktok_post(
                account_id="account-1",
                content="Caption\n#tag",
                media_url="https://media.example/video.mp4",
                privacy_level="PUBLIC_TO_EVERYONE",
                publish_now=True,
                request_id="request-1",
                allow_comment=False,
            )

        request = captured["request"]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://zernio.com/api/v1/posts")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.key}")
        self.assertEqual(request.get_header("X-request-id"), "request-1")
        self.assertEqual(body["platforms"], [{"platform": "tiktok", "accountId": "account-1"}])
        self.assertEqual(body["mediaItems"][0]["type"], "video")
        self.assertTrue(body["publishNow"])
        self.assertFalse(body["tiktokSettings"]["allow_comment"])
        self.assertTrue(body["tiktokSettings"]["content_preview_confirmed"])
        self.assertTrue(body["tiktokSettings"]["express_consent_given"])
        self.assertEqual(result["post"]["id"], "post-1")

    def test_upload_streams_file_to_the_presigned_url(self):
        _Connection.instances.clear()
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "clip.mp4")
            source.write_bytes(b"video-bytes")
            with patch("haizflow.services.zernio.http.client.HTTPConnection", _Connection):
                zernio.ZernioClient(self.key).upload_file(
                    "http://upload.example/media?signature=private",
                    str(source),
                    content_type="video/mp4",
                    progress=lambda sent, total: progress.append((sent, total)),
                )

        connection = _Connection.instances[0]
        self.assertEqual(connection.method, "PUT")
        self.assertEqual(connection.target, "/media?signature=private")
        self.assertEqual(connection.headers["Content-Type"], "video/mp4")
        self.assertEqual(bytes(connection.body), b"video-bytes")
        self.assertEqual(progress[-1], (11, 11))
        self.assertTrue(connection.closed)

    def test_list_accounts_accepts_a_data_array_response(self):
        payload = {
            "data": [
                {"id": "tik-1", "platform": "tiktok"},
                {"id": "other-1", "platform": "youtube"},
            ]
        }
        with patch("haizflow.services.zernio.urlopen", return_value=_Response(payload)):
            accounts = zernio.ZernioClient(self.key).list_tiktok_accounts()

        self.assertEqual([account["id"] for account in accounts], ["tik-1"])

    def test_http_error_is_safe_and_does_not_include_the_api_key(self):
        response = HTTPError(
            "https://zernio.com/api/v1/accounts",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"error":{"message":"Invalid API key"}}'),
        )
        with patch("haizflow.services.zernio.urlopen", side_effect=response):
            with self.assertRaises(zernio.ZernioError) as raised:
                zernio.ZernioClient(self.key).list_tiktok_accounts()

        self.assertIn("HTTP 401", str(raised.exception))
        self.assertIn("Invalid API key", str(raised.exception))
        self.assertNotIn(self.key, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
