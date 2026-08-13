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

    def test_instagram_reel_uses_platform_specific_payload(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _Response({"post": {"id": "post-instagram"}})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            zernio.ZernioClient(self.key).create_video_post(
                platform="instagram",
                account_id="ig-1",
                content="Caption #tag",
                media_url="https://media.example/reel.mp4",
                publish_now=True,
                request_id="request-instagram",
                share_to_feed=False,
                ai_generated=True,
                first_comment="More details",
            )

        target = captured["body"]["platforms"][0]
        self.assertEqual(target["platform"], "instagram")
        self.assertEqual(target["platformSpecificData"], {
            "contentType": "reels",
            "shareToFeed": False,
            "isAiGenerated": True,
            "firstComment": "More details",
        })

    def test_facebook_reel_supports_title_and_first_comment(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _Response({"post": {"id": "post-facebook"}})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            zernio.ZernioClient(self.key).create_video_post(
                platform="facebook",
                account_id="fb-1",
                content="Caption",
                media_url="https://media.example/reel.mp4",
                publish_now=True,
                request_id="request-facebook",
                title="Reel title",
                first_comment="First comment",
            )

        data = captured["body"]["platforms"][0]["platformSpecificData"]
        self.assertEqual(data, {
            "contentType": "reel",
            "title": "Reel title",
            "firstComment": "First comment",
        })

    def test_youtube_video_uses_title_and_visibility(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _Response({"post": {"id": "post-youtube"}})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            zernio.ZernioClient(self.key).create_video_post(
                platform="youtube",
                account_id="yt-1",
                content="Description",
                media_url="https://media.example/short.mp4",
                publish_now=True,
                request_id="request-youtube",
                title="My Short",
                privacy_level="unlisted",
            )

        target = captured["body"]["platforms"][0]
        self.assertEqual(target["platform"], "youtube")
        self.assertEqual(target["platformSpecificData"], {"title": "My Short", "visibility": "unlisted"})

    def test_list_supported_accounts_keeps_all_requested_platforms(self):
        payload = {"accounts": [
            {"id": "tik-1", "platform": "tiktok"},
            {"id": "yt-1", "platform": "youtube"},
            {"id": "ignored", "platform": "linkedin"},
        ]}
        with patch("haizflow.services.zernio.urlopen", return_value=_Response(payload)):
            accounts = zernio.ZernioClient(self.key).list_accounts(platforms=("tiktok", "youtube"))

        self.assertEqual([account["id"] for account in accounts], ["tik-1", "yt-1"])

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

    def test_list_accounts_requests_only_connected_tiktok_accounts(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            return _Response({"data": []})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            zernio.ZernioClient(self.key).list_tiktok_accounts("profile-1")

        self.assertIn("platform=tiktok", captured["url"])
        self.assertIn("status=connected", captured["url"])
        self.assertIn("includeOverLimit=true", captured["url"])
        self.assertIn("profileId=profile-1", captured["url"])

    def test_list_accounts_can_sync_all_profiles_without_profile_filter(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            return _Response({"accounts": []})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            zernio.ZernioClient(self.key).list_tiktok_accounts()

        self.assertIn("platform=tiktok", captured["url"])
        self.assertNotIn("profileId=", captured["url"])

    def test_disconnect_account_uses_delete_and_escapes_the_account_id(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response({"message": "Account disconnected successfully"})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            result = zernio.ZernioClient(self.key).disconnect_account("account/id")

        request = captured["request"]
        self.assertEqual(request.method, "DELETE")
        self.assertEqual(
            request.full_url,
            "https://zernio.com/api/v1/accounts/account%2Fid",
        )
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.key}")
        self.assertEqual(result["message"], "Account disconnected successfully")

    def test_list_profiles_includes_profiles_over_the_plan_limit_for_setup_visibility(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            return _Response({"profiles": []})

        with patch("haizflow.services.zernio.urlopen", side_effect=fake_urlopen):
            zernio.ZernioClient(self.key).list_profiles()

        self.assertIn("includeOverLimit=true", captured["url"])

    def test_creator_info_normalizes_privacy_values_and_interactions(self):
        payload = {
            "data": {
                "creator": {"canPostMore": False},
                "privacyLevels": [
                    {"value": "PUBLIC_TO_EVERYONE", "label": "Public"},
                    {"value": "SELF_ONLY", "label": "Only me"},
                ],
                "postingLimits": {
                    "interactionSettings": {"comment": True, "duet": False, "stitch": True}
                },
            }
        }
        with patch("haizflow.services.zernio.urlopen", return_value=_Response(payload)):
            info = zernio.ZernioClient(self.key).get_tiktok_creator_info("tik-1")

        self.assertEqual(info["privacyLevels"], ["PUBLIC_TO_EVERYONE", "SELF_ONLY"])
        self.assertEqual(info["interactionSettings"], {"comment": True, "duet": False, "stitch": True})
        self.assertFalse(info["canPostMore"])

    def test_tiktok_post_result_prefers_platform_status_over_stale_root_status(self):
        result = zernio.tiktok_post_result({
            "status": "publishing",
            "platforms": [{
                "platform": "tiktok",
                "status": "published",
                "platformPostUrl": "https://www.tiktok.com/@creator/video/123",
            }],
        })

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["url"], "https://www.tiktok.com/@creator/video/123")
        self.assertEqual(result["error"], "")

    def test_post_result_reads_wrapped_platform_mapping_and_permalink(self):
        result = zernio.post_result(
            {
                "data": {
                    "post": {
                        "status": "publishing",
                        "platformResults": {
                            "youtube": {
                                "platform": "youtube",
                                "status": "published",
                                "result": {
                                    "platformPostUrl": "https://www.youtube.com/shorts/abc123"
                                },
                            }
                        },
                    }
                }
            },
            "youtube",
        )

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["url"], "https://www.youtube.com/shorts/abc123")

    def test_tiktok_post_result_does_not_guess_url_from_temporary_publish_id(self):
        result = zernio.tiktok_post_result({
            "status": "published",
            "platforms": [{
                "platform": "tiktok",
                "status": "published",
                "platformPostId": "v_pub_url~v2-1.7672661563752450049",
                "platformPostUrl": "",
                "accountId": {"username": "@creator"},
            }],
        })

        self.assertEqual(result["url"], "")

    def test_post_result_rejects_generic_media_or_dashboard_urls(self):
        for invalid_url in (
            "https://media.zernio.com/media/video.mp4",
            "https://zernio.com/dashboard/posts/post-1",
            "https://www.tiktok.com/tiktokstudio/upload",
        ):
            with self.subTest(url=invalid_url):
                result = zernio.tiktok_post_result({
                    "status": "published",
                    "url": invalid_url,
                    "platforms": [{
                        "platform": "tiktok",
                        "status": "published",
                        "url": invalid_url,
                    }],
                })
                self.assertEqual(result["url"], "")

    def test_public_post_url_accepts_supported_platform_permalinks(self):
        self.assertEqual(
            zernio.public_post_url("https://www.tiktok.com/@creator/video/123", "tiktok"),
            "https://www.tiktok.com/@creator/video/123",
        )
        self.assertEqual(
            zernio.public_post_url("https://www.youtube.com/shorts/abc", "youtube"),
            "https://www.youtube.com/shorts/abc",
        )

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
