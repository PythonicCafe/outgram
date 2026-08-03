import json
from pathlib import Path

import pytest

from outgram.instagram import Instagram
from outgram.models import Picture, Video

FIXTURES = Path(__file__).parent / "fixtures"


class DummyResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def bare_client():
    client = Instagram.__new__(Instagram)
    client._user_id_cache = {}
    return client


def load_nodes():
    return json.loads((FIXTURES / "instagram_media_nodes.json").read_text())


def test_public_profile_html_parser_handles_attribute_order_and_entities():
    page = (FIXTURES / "instagram_public_profile.html").read_text()
    profile = Instagram._extract_public_profile_from_html(page, "example.person", 123)

    assert profile.id == 123
    assert profile.username == "example.person"
    assert profile.full_name == "Example Person"
    assert profile.followers == 11000
    assert profile.followees == 3165
    assert profile.posts == 1483
    assert profile.biography == "Sanitized biography & contact"
    assert profile.picture.url == "https://cdn.example.invalid/profile.jpg"
    assert profile.bio_links == []


def test_public_profile_html_parser_prefers_ssr_graphql_data_and_bio_links():
    page = (FIXTURES / "instagram_public_profile_ssr.html").read_text()
    profile = Instagram._extract_public_profile_from_html(page, "example.person", 123)

    assert profile.id == 123
    assert profile.full_name == "Example Person"
    assert profile.picture.url == "https://cdn.example.invalid/ssr-profile.jpg"
    assert profile.biography == "Structured sanitized biography"
    assert profile.is_verified is True
    assert profile.is_private is False
    assert profile.followers == 11000
    assert profile.followees == 3165
    assert profile.posts == 1483
    assert [(link.title, link.url) for link in profile.bio_links] == [
        ("Example site", "https://example.invalid/"),
        ("Second link", "https://second.example.invalid/"),
    ]


@pytest.mark.parametrize(
    ("code", "expected"),
    [("DblUK2chk_-", 3955656554300461054), ("DaWbJ6psWfA", 3933450753262315456)],
)
def test_media_id_from_shortcode(code, expected):
    assert Instagram._media_id_from_code(code) == expected


@pytest.mark.parametrize("code", ["", "invalid+code"])
def test_media_id_from_invalid_shortcode(code):
    with pytest.raises(ValueError):
        Instagram._media_id_from_code(code)


def test_extract_public_timeline_video_node():
    post = bare_client()._extract_post_from_graphql_node(load_nodes()["public_timeline_video"])

    assert post.code == "VideoCode_1"
    assert post.type == "video"
    assert post.author.username == "example.person"
    assert post.text == "Sanitized video caption"
    assert post.likes is None  # Compact public timeline does not provide likes.
    assert post.thumbnail.url == "https://cdn.example.invalid/video-thumb.jpg"
    assert len(post.media) == 1
    assert isinstance(post.media[0], Video)
    assert post.media[0].url == "https://cdn.example.invalid/video.mp4"


def test_extract_media_id_carousel_with_children_without_media_type():
    post = bare_client()._extract_post_from_xdt_timeline_node(load_nodes()["media_id_carousel"])

    assert post.code == "Carousel_1"
    assert post.type == "carousel"
    assert post.author.username == "example.person"
    assert post.likes == 10
    assert post.comments == 2
    assert isinstance(post.thumbnail, Picture)
    assert post.thumbnail.url == "https://cdn.example.invalid/carousel-cover.jpg"
    assert len(post.media) == 2
    assert isinstance(post.media[0], Picture)
    assert isinstance(post.media[1], Video)
    assert post.media[1].width == 720
    assert post.media[1].height == 1280


def test_profile_from_user_id_uses_user_info_then_public_page():
    client = bare_client()
    calls = []

    def request(method, url, headers=None, **kwargs):
        calls.append((method, url, headers))
        return DummyResponse({"user": {"id": "123", "username": "example.person"}})

    client.request = request
    client.profile_from_public_page = lambda username, user_id: (username, user_id)

    assert client.profile_from_user_id(123) == ("example.person", 123)
    assert client.profile_from_user_id(123, raw=True)["username"] == "example.person"
    assert calls == [
        (
            "GET",
            "https://www.instagram.com/api/v1/users/123/info/",
            {"x-requested-with": "XMLHttpRequest"},
        ),
        (
            "GET",
            "https://www.instagram.com/api/v1/users/123/info/",
            {"x-requested-with": "XMLHttpRequest"},
        ),
    ]


def test_profile_posts_by_id_uses_public_timeline_query_and_validates_response():
    client = bare_client()
    node = load_nodes()["public_timeline_video"]
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return DummyResponse(
            {
                "data": {
                    "user": {
                        "edge_owner_to_timeline_media": {
                            "edges": [{"node": node}],
                            "page_info": {"has_next_page": False, "end_cursor": None},
                        }
                    }
                }
            }
        )

    client.request = request
    posts = list(client.profile_posts_from_user_id(200))

    assert [post.code for post in posts] == ["VideoCode_1"]
    assert calls[0]["method"] == "GET"
    assert calls[0]["params"]["doc_id"] == Instagram.public_timeline_query["doc_id"]
    assert json.loads(calls[0]["params"]["variables"])["id"] == "200"


def test_model_urls():
    profile = Instagram._extract_public_profile_from_html(
        (FIXTURES / "instagram_public_profile.html").read_text(), "example.person", 123
    )
    assert profile.url == "https://www.instagram.com/example.person/"

    video = bare_client()._extract_post_from_graphql_node(load_nodes()["public_timeline_video"])
    carousel = bare_client()._extract_post_from_xdt_timeline_node(load_nodes()["media_id_carousel"])
    assert video.url == "https://www.instagram.com/reel/VideoCode_1/"
    assert carousel.url == "https://www.instagram.com/p/Carousel_1/"
