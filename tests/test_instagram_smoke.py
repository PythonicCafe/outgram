"""Opt-in live smoke tests for Instagram public endpoints.

Run explicitly, never as part of the default unit suite:
OUTGRAM_RUN_SMOKE=1 pytest -m instagram_smoke tests/test_instagram_smoke.py
"""

import csv
import itertools
import os
from zipfile import ZipFile

import pytest

from outgram import Instagram
from outgram.cli import archive
from outgram.models import Picture, Video

pytestmark = [
    pytest.mark.instagram_smoke,
    pytest.mark.skipif(not os.environ.get("OUTGRAM_RUN_SMOKE"), reason="set OUTGRAM_RUN_SMOKE=1 to run live tests"),
]

RAFICOMEDY = {"username": "raficomedy", "id": 9189949402}
RAFICOMEDY_VIDEO = "DblUK2chk_-"
RAFICOMEDY_CAROUSEL = "DZYhO1CD9au"
GOVBR_PHOTO = "DaWbJ6psWfA"


def make_client():
    return Instagram(min_wait=1.0, max_wait=2.0)


def assert_profile(profile, expected):
    assert profile.id == expected["id"]
    assert profile.username == expected["username"]
    assert profile.full_name
    assert profile.followers is not None and profile.followers > 0
    assert profile.followees is not None and profile.followees >= 0
    assert profile.posts is not None and profile.posts > 0
    assert isinstance(profile.picture, Picture)
    assert profile.picture.url.startswith("https://")
    assert profile.bio_links is not None
    assert all(link.url.startswith("https://") for link in profile.bio_links)
    assert profile.url == f"https://www.instagram.com/{expected['username']}/"


def assert_post(post, code, expected_type, expected_username, minimum_media=1):
    assert post.code == code
    assert post.pk > 0
    assert post.type == expected_type
    assert post.author.username == expected_username
    assert post.author.id > 0
    assert post.published_at.tzinfo is not None
    assert post.text is None or isinstance(post.text, str)  # Captions are optional.
    assert len(post.media) >= minimum_media
    assert all(media.url.startswith("https://") for media in post.media)
    assert post.url.startswith("https://www.instagram.com/")


def test_profile_by_username_and_cached_id_match_stable_fields():
    client = make_client()
    by_username = client.profile(RAFICOMEDY["username"])
    by_cached_id = client.profile(RAFICOMEDY["id"])

    assert_profile(by_username, RAFICOMEDY)
    assert_profile(by_cached_id, RAFICOMEDY)
    assert (by_username.id, by_username.username, by_username.full_name) == (
        by_cached_id.id,
        by_cached_id.username,
        by_cached_id.full_name,
    )
    assert {link.url for link in by_username.bio_links} == {
        "https://www.rafibastos.com",
        "https://melanvies.com/rafibastos/",
    }
    assert by_username.is_verified is True
    assert by_username.is_private is False


def test_profile_by_uncached_id_when_public_user_info_is_available():
    try:
        profile = make_client().profile(RAFICOMEDY["id"])
    except RuntimeError as exc:
        if "require_login" in str(exc) or "Please wait" in str(exc):
            pytest.skip("Instagram temporarily rate-limited the public user-info endpoint")
        raise
    assert_profile(profile, RAFICOMEDY)


def test_timeline_by_username_and_id_have_valid_and_matching_posts():
    client = make_client()
    by_username = list(itertools.islice(client.profile_posts(RAFICOMEDY["username"]), 13))
    by_id = list(itertools.islice(client.profile_posts(RAFICOMEDY["id"]), 13))

    assert len(by_username) == len(by_id) == 13  # Forces public-query pagination beyond the first 12.
    assert {post.code for post in by_username} == {post.code for post in by_id}
    for post in by_username + by_id:
        assert post.pk > 0
        assert post.type in {"photo", "video", "carousel"}
        assert post.author.username
        assert post.published_at.tzinfo is not None
        assert post.media
        assert all(media.url.startswith("https://") for media in post.media)


def test_individual_posts_and_timeline_agree_on_stable_fields():
    client = make_client()
    video = client.post(RAFICOMEDY_VIDEO)
    carousel = client.post(RAFICOMEDY_CAROUSEL)
    photo = client.post(GOVBR_PHOTO)

    assert_post(video, RAFICOMEDY_VIDEO, "video", RAFICOMEDY["username"])
    assert isinstance(video.media[0], Video)
    assert video.thumbnail is not None
    assert_post(carousel, RAFICOMEDY_CAROUSEL, "carousel", RAFICOMEDY["username"], minimum_media=2)
    assert carousel.thumbnail is not None
    assert_post(photo, GOVBR_PHOTO, "photo", "govbr")
    assert isinstance(photo.media[0], Picture)
    assert photo.thumbnail is None

    timeline = list(itertools.islice(client.profile_posts(RAFICOMEDY["username"]), 48))
    timeline_by_code = {post.code: post for post in timeline}
    for detailed in (video, carousel):
        summary = timeline_by_code[detailed.code]
        assert (summary.pk, summary.code, summary.type, summary.author.username) == (
            detailed.pk,
            detailed.code,
            detailed.type,
            detailed.author.username,
        )
        assert summary.text == detailed.text
        assert len(summary.media) == len(detailed.media)


def test_download_and_archive_smoke(temp_dir):
    client = make_client()
    photo = client.post(GOVBR_PHOTO)
    downloaded = list(client.download(photo, parallel=1))
    assert len(downloaded) == 1
    assert downloaded[0].content
    assert downloaded[0].content_type.startswith("image/")

    output = temp_dir / "instagram-smoke.zip"
    archive(
        client_class=Instagram,
        usernames_or_ids=[RAFICOMEDY["username"]],
        output_zip=output,
        min_wait=1.0,
        max_wait=2.0,
        max_posts_per_user=1,
        max_posts=1,
        quiet=True,
    )
    with ZipFile(output) as zip_file:
        names = zip_file.namelist()
        assert "profile.csv" in names
        assert "post.csv" in names
        assert any(name.startswith("media/profile_") for name in names)
        assert any(name.startswith("media/post_") for name in names)
        with zip_file.open("post.csv") as file_obj:
            rows = list(csv.DictReader(line.decode("utf-8") for line in file_obj))
        assert len(rows) == 1
        assert rows[0]["code"]
        assert rows[0]["media"]
