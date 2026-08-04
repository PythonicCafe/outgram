import json
from pathlib import Path

import pytest

from outgram.models import Picture, Video
from outgram.threads import Threads

FIXTURES = Path(__file__).parent / "fixtures"


class DummyResponse:
    def __init__(self, data, status_code=200, content_type="application/json"):
        self._data = data
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self):
        if isinstance(self._data, ValueError):
            raise self._data
        return self._data


def fixture_data():
    return json.loads((FIXTURES / "threads_public_data.json").read_text())


def bare_client():
    client = Threads.__new__(Threads)
    client._user_id_cache = {}
    client.session = type("Session", (), {"headers": {"x-fb-lsd": "local"}})()
    return client


def test_extract_profile_preserves_complete_public_data():
    profile = bare_client()._extract_profile(fixture_data()["profile"])

    assert profile.id == 101
    assert profile.pictures[-1].width == 640
    assert [(link.url, link.id) for link in profile.bio_links] == [("https://example.invalid/", 55)]


def test_extract_profile_accepts_missing_optional_fields():
    profile = bare_client()._extract_profile(fixture_data()["minimal_profile"])

    assert profile.pictures == []
    assert profile.bio_links == []
    assert profile.is_verified is None


@pytest.mark.parametrize(
    ("name", "media_class"),
    [("text_post", None), ("photo_post", Picture), ("video_post", Video), ("carousel_post", None)],
)
def test_extract_post_supports_public_media_shapes(name, media_class):
    post = bare_client()._extract_post(fixture_data()[name])

    assert post.id
    assert post.published_at.tzinfo is not None
    if media_class:
        assert isinstance(post.media[0], media_class)
    if name == "text_post":
        assert post.text == "Hello site"
        assert post.links[0].url == "https://example.invalid/"
    if name == "video_post":
        assert post.media[0].thumbnail.url.endswith("thumb.jpg")
    if name == "carousel_post":
        assert [type(media) for media in post.media] == [Picture, Video]


def test_profile_requests_forward_raw_and_cache_username():
    client = bare_client()
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return DummyResponse(fixture_data()["profile"])

    client.request = request
    assert client.simple_profile("example.person").id == 101
    assert client.profile("101", raw=True)["data"]["user"]["username"] == "example.person"
    assert calls[0]["data"]["doc_id"] == Threads.public_username_query["doc_id"]
    assert calls[1]["data"]["doc_id"] == Threads.public_profile_query["doc_id"]


def test_profile_posts_follow_cursor_and_stop_at_last_page():
    client = bare_client()
    data = fixture_data()
    pages = [
        {"data": {"mediaData": {"edges": [{"node": {"thread_items": [{"post": data["text_post"]}]}}], "page_info": {"has_next_page": True, "end_cursor": "sanitized-cursor"}}}},
        {"data": {"mediaData": {"edges": [{"node": {"thread_items": [{"post": data["photo_post"]}]}}], "page_info": {"has_next_page": False, "end_cursor": None}}}},
    ]
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return DummyResponse(pages.pop(0))

    client.request = request
    assert [post.id for post in client.profile_posts_from_user_id(101)] == ["text-1", "photo-1"]
    assert json.loads(calls[1]["data"]["variables"])["after"] == "sanitized-cursor"


@pytest.mark.parametrize(
    "response, message",
    [
        (DummyResponse({}, status_code=403), "blocked"),
        (DummyResponse(ValueError(), content_type="application/json"), "invalid JSON"),
        (DummyResponse({"data": {}}, content_type="text/html"), "HTML response"),
        (DummyResponse({"unexpected": True}), "unexpected shape"),
    ],
)
def test_graphql_query_reports_blocked_and_invalid_responses(response, message):
    client = bare_client()
    client.request = lambda **kwargs: response

    with pytest.raises(RuntimeError, match=message):
        client._graphql_query(Threads.public_profile_query, {})


def test_model_urls_use_threads_canonical_domain():
    data = fixture_data()
    profile = bare_client()._extract_profile(data["profile"])
    post = bare_client()._extract_post(data["text_post"])

    assert profile.url == "https://www.threads.com/@example.person"
    assert post.url == "https://www.threads.com/@example.person/post/None"
