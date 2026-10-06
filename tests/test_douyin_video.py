from unittest.mock import Mock

import pytest

from haizflow.services.douyin_video import (
    ACCESS_MESSAGE, PUBLIC_METADATA_AGENT, HaizFlowDouyinIE, share_page_detail, video_id_from_url,
)
from haizflow.services.video_download import _extract_video_info, _friendly_error, validate_video_url


@pytest.mark.parametrize("url", [
    "https://www.douyin.com/jingxuan?modal_id=768495470663049704",
    "https://www.douyin.com/user/creator?modal_id=768495470663049704&from=share",
    "https://www.iesdouyin.com/share/video/768495470663049704/",
    "https://www.douyin.com/video/768495470663049704?from=share",
])
def test_douyin_browser_and_mobile_urls_identify_same_video(url):
    assert validate_video_url(url) == ("https://www.douyin.com/video/768495470663049704", "Douyin")
    assert video_id_from_url(url) == "768495470663049704"


@pytest.mark.parametrize("url", [
    "https://douyin.com.evil.example/video/768495470663049704",
    "file:///video/768495470663049704",
    "https://user:password@douyin.com/video/768495470663049704",
    "https://douyin.com/jingxuan?modal_id=bad",
    "https://douyin.com/jingxuan?modal_id=123456789012&modal_id=123456789013",
])
def test_invalid_or_ambiguous_douyin_ids_are_rejected(url):
    with pytest.raises(Exception):
        video_id_from_url(url)
    with pytest.raises(ValueError):
        validate_video_url(url)


def test_short_share_url_resolves_modal_id_before_extraction():
    ie = HaizFlowDouyinIE()
    ie._download_webpage_handle = Mock(return_value=("", Mock(url=(
        "https://www.douyin.com/jingxuan?modal_id=768495470663049704"))))
    detail = {"aweme_id": "768495470663049704", "video": {}}
    ie._download_json = Mock(return_value={"aweme_detail": detail})
    ie._parse_aweme_video_app = Mock(return_value={"formats": [{"url": "https://example.com/public.mp4"}]})
    result = ie._real_extract("https://v.douyin.com/demo/")
    assert result["webpage_url"] == "https://www.douyin.com/video/768495470663049704"
    assert ie._download_json.call_args.kwargs["query"]["aweme_id"] == detail["aweme_id"]


def test_public_hydration_only_accepts_matching_video_and_never_executes_js():
    page = 'window._ROUTER_DATA = {"loaderData":{"video_(id)/page":{"videoInfoRes":' \
           '{"item_list":[{"aweme_id":"123456789012","video":{}}]}}}}; dangerous();'
    assert share_page_detail(page, "123456789012")["aweme_id"] == "123456789012"
    assert share_page_detail(page, "999999999999") is None
    assert share_page_detail('window._ROUTER_DATA = dangerous()', "123456789012") is None


def test_browser_link_uses_public_metadata_when_normal_api_is_empty():
    ie = HaizFlowDouyinIE()
    video = "7692729822069443859"
    detail = {"aweme_id": video, "video": {}}
    ie._download_json = Mock(side_effect=[None, {"aweme_detail": detail}])
    ie._download_webpage = Mock()
    ie._parse_aweme_video_app = Mock(return_value={"formats": [{"url": "https://example.com/public.mp4"}]})
    result = ie._real_extract(f"https://www.douyin.com/video/{video}")
    assert result["formats"]
    assert result["webpage_url"] == f"https://www.douyin.com/video/{video}"
    assert ie._download_json.call_args.kwargs["headers"] == {"User-Agent": PUBLIC_METADATA_AGENT}
    ie._download_webpage.assert_not_called()


def test_public_metadata_for_another_video_is_not_downloaded():
    ie = HaizFlowDouyinIE()
    ie._download_json = Mock(side_effect=[None, {"aweme_detail": {
        "aweme_id": "123456789013", "video": {}}}])
    ie._parse_aweme_video_app = Mock()
    with pytest.raises(Exception, match="Douyin did not provide"):
        ie._real_extract("https://www.douyin.com/video/123456789012")
    ie._parse_aweme_video_app.assert_not_called()


def test_verification_pages_produce_actionable_error_without_retries():
    ie = HaizFlowDouyinIE()
    ie._download_json = Mock(return_value=None)
    ie._download_webpage = Mock(return_value="<html>verification required</html>")
    with pytest.raises(Exception, match="Douyin did not provide") as error:
        ie._real_extract("https://www.douyin.com/video/123456789012")
    assert _friendly_error(error.value) == ACCESS_MESSAGE


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=BaW_jenozKc",
    "https://www.tiktok.com/@creator/video/123456789012",
    "https://www.bilibili.com/video/BV1xx411c7mD",
    "https://www.instagram.com/reel/example",
    "https://www.facebook.com/watch/?v=123456789012",
    "https://x.com/creator/status/123456789012",
    "https://vimeo.com/123456789",
    "https://www.dailymotion.com/video/x123abc",
    "https://www.twitch.tv/videos/123456789",
    "https://www.reddit.com/r/videos/comments/example/title",
    "https://streamable.com/example",
    "https://vk.com/video-123_456",
])
@pytest.mark.parametrize("download", [False, True])
def test_other_sources_keep_their_existing_extractor(url, download):
    downloader = Mock()
    _extract_video_info(downloader, url, download=download)
    downloader.add_info_extractor.assert_not_called()
    downloader.extract_info.assert_called_once_with(url, download=download)
