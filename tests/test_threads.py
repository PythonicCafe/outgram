"""Live smoke tests for the public Threads profile page."""

import csv
import os

import pytest

from outgram.cli import collect_profile_posts
from outgram.threads import Threads

pytestmark = [
    pytest.mark.threads_smoke,
    pytest.mark.skipif(
        os.getenv("OUTGRAM_RUN_THREADS_SMOKE") != "1",
        reason="set OUTGRAM_RUN_THREADS_SMOKE=1 to run live Threads smoke tests",
    ),
]

THREADS_USERNAME = "zuck"


def test_threads_profile_from_username():
    client = Threads(min_wait=1.0, max_wait=1.0)

    profile = client.profile_from_username(THREADS_USERNAME)

    assert profile.id
    assert profile.username == THREADS_USERNAME


def test_threads_first_profile_page_with_post_limit(temp_dir):
    output_filename = temp_dir / "threads-profile-posts.csv"
    collect_profile_posts(
        client_class=Threads,
        usernames_or_ids=[THREADS_USERNAME],
        output_csv=output_filename,
        min_wait=1.0,
        max_wait=1.0,
        max_posts_per_user=1,
        max_posts=1,
        quiet=True,
    )

    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == 1
    assert data[0]["username"] == THREADS_USERNAME
