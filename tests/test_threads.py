"""Live smoke tests for the public Threads profile page."""

import os
from itertools import islice

import pytest

from outgram.threads import Threads

pytestmark = [
    pytest.mark.threads_smoke,
    pytest.mark.skipif(
        os.getenv("OUTGRAM_RUN_THREADS_SMOKE") != "1",
        reason="set OUTGRAM_RUN_THREADS_SMOKE=1 to run live Threads smoke tests",
    ),
]

THREADS_PAGINATION_USERNAME = "lulaoficial"


def test_threads_profile_posts_follow_public_cursor():
    client = Threads(min_wait=1.0, max_wait=1.0)

    posts = list(
        islice(
            client.profile_posts_from_username(THREADS_PAGINATION_USERNAME),
            5,
        )
    )

    assert len(posts) == 5
    assert len({post.id for post in posts}) == 5
    assert {post.username for post in posts} == {THREADS_PAGINATION_USERNAME}
