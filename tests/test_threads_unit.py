from itertools import islice
from pathlib import Path

import pytest

from outgram.models import Picture
from outgram.threads import Threads

FIXTURES = Path(__file__).parent / "fixtures"


class DummyResponse:
    def __init__(self, text, status_code=200, content_type="text/html"):
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}


class GraphQLResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._data


def public_page():
    return (FIXTURES / "threads_public_profile_ssr.html").read_text()


def bare_client(response):
    client = Threads.__new__(Threads)
    client._user_id_cache = {}
    client.request = lambda **kwargs: response
    return client


def test_profile_from_username_reads_public_ssr_data():
    calls = []
    response = DummyResponse(public_page())
    client = bare_client(response)
    client.request = lambda **kwargs: calls.append(kwargs) or response

    profile = client.profile_from_username("example.person")

    assert profile.id == 101
    assert profile.username == "example.person"
    assert profile.pictures[-1].width == 640
    assert [(link.url, link.id) for link in profile.bio_links] == [
        ("https://example.invalid/", 55)
    ]
    assert client._user_id_cache == {"example.person": 101}
    assert calls == [
        {
            "method": "GET",
            "url": "https://www.threads.com/@example.person",
            "headers": {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.5",
                "origin": None,
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            },
        }
    ]


def test_profile_from_username_preserves_ssr_result_when_raw():
    result = bare_client(DummyResponse(public_page())).simple_profile(
        "example.person", raw=True
    )

    assert result["data"]["user"]["username"] == "example.person"


def test_profile_posts_from_username_reads_first_ssr_page():
    posts = list(
        islice(
            bare_client(DummyResponse(public_page())).profile_posts_from_username(
                "example.person"
            ),
            1,
        )
    )

    assert len(posts) == 1
    assert posts[0].id == "post-1"
    assert posts[0].text == "Hello site"
    assert posts[0].links[0].url == "https://example.invalid/"
    assert isinstance(posts[0].media[0], Picture)
    assert posts[0].media[0].width == 800


def test_profile_and_posts_reuse_one_public_page_navigation():
    calls = []
    response = DummyResponse(public_page())
    client = bare_client(response)
    client.request = lambda **kwargs: calls.append(kwargs) or response

    profile = client.profile_from_username("example.person")
    post = next(client.profile_posts_from_username("example.person"))

    assert profile.username == post.username == "example.person"
    assert len(calls) == 1


def test_profile_posts_follow_public_ssr_cursor():
    calls = []
    responses = [
        DummyResponse(public_page()),
        GraphQLResponse(
            {
                "data": {
                    "mediaData": {
                        "edges": [
                            {
                                "node": {
                                    "thread_items": [
                                        {
                                            "post": {
                                                "id": "post-2",
                                                "user": {
                                                    "pk": "101",
                                                    "username": "example.person",
                                                },
                                                "taken_at": 2,
                                                "like_count": 0,
                                            }
                                        }
                                    ]
                                }
                            }
                        ],
                        "page_info": {"has_next_page": False, "end_cursor": None},
                    }
                }
            }
        ),
    ]
    client = bare_client(None)

    def request(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    client.request = request
    posts = list(client.profile_posts_from_username("example.person"))

    assert [post.id for post in posts] == ["post-1", "post-2"]
    assert calls[1]["url"] == "https://www.threads.com/graphql/query"
    assert calls[1]["headers"]["x-csrftoken"] == "test-csrf"
    assert calls[1]["headers"]["x-bloks-version-id"] == "test-bloks"
    assert calls[1]["data"]["lsd"] == "test-lsd"
    assert calls[1]["data"]["__dyn"] == ""
    assert calls[1]["data"]["__csr"] == ""
    assert '"after": "sanitized-cursor"' in calls[1]["data"]["variables"]


@pytest.mark.parametrize(
    "response, message",
    [
        (DummyResponse("<html></html>"), "no SSR data"),
        (DummyResponse("{}", content_type="application/json"), "expected HTML"),
        (DummyResponse("", status_code=403), "blocked"),
    ],
)
def test_public_profile_reports_unavailable_responses(response, message):
    with pytest.raises(RuntimeError, match=message):
        bare_client(response).simple_profile("example.person")


def test_numeric_id_lookup_reports_current_public_limitation():
    with pytest.raises(RuntimeError, match="numeric ID"):
        bare_client(DummyResponse(public_page())).profile_from_user_id(101)


def test_model_urls_use_threads_canonical_domain():
    client = bare_client(DummyResponse(public_page()))
    profile = client.simple_profile("example.person")
    post = next(client.profile_posts_from_username("example.person"))

    assert profile.url == "https://www.threads.com/@example.person"
    assert post.url == "https://www.threads.com/@example.person/post/ABC"
