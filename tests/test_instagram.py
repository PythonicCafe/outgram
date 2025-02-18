"""End-to-end tests for the command-line interface main functions, which will run most part of the codebase"""

import csv
from zipfile import ZipFile

from outgram.cli import archive, collect_profile, collect_profile_posts, instagram_post
from outgram.instagram import Instagram

MIN_WAIT = 5.0
MAX_WAIT = 10.0
INSTAGRAM_USERNAME_ID = {
    "crio.cafe": "21057648761",
    "pythonbrasil": "1543793548",
    "estadao": "23456103",
}
INSTAGRAM_USERNAMES = list(INSTAGRAM_USERNAME_ID.keys())
INSTAGRAM_USER_IDS = list(INSTAGRAM_USERNAME_ID.values())
INSTAGRAM_USER_MIX = []
for index, (username, user_id) in enumerate(INSTAGRAM_USERNAME_ID.items()):
    if index < 2:
        INSTAGRAM_USER_MIX.append(username)
    else:
        INSTAGRAM_USER_MIX.append(user_id)
INSTAGRAM_POST_CODES = (
    "DEhf2uTJUs0",  # zuck
    "DF-rojvO4g-",  # oficialfernandatorres
    "C2SuqhGv3U0",  # crio.cafe
    "DGLQHNhOoke",  # oficialfernandatorres
    "COWY0ydHUrI",  # crio.cafe
    "DFWFT4LyfSJ",  # ficcoesespetaculo
)


def test_instagram_profile_with_usernames(temp_dir):
    output_filename = temp_dir / "instagram-profile-1.csv"
    assert not output_filename.exists()
    collect_profile(
        client_class=Instagram,
        usernames_or_ids=INSTAGRAM_USERNAMES,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == len(INSTAGRAM_USERNAMES)
    usernames_found = set(row["username"] for row in data)
    assert usernames_found == set(INSTAGRAM_USERNAMES)


def test_instagram_profile_with_user_ids(temp_dir):
    output_filename = temp_dir / "instagram-profile-2.csv"
    assert not output_filename.exists()
    collect_profile(
        client_class=Instagram,
        usernames_or_ids=INSTAGRAM_USER_IDS,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == len(INSTAGRAM_USER_IDS)
    user_ids_found = set(row["id"] for row in data)
    assert user_ids_found == set(INSTAGRAM_USER_IDS)


def test_instagram_profile_with_usernames_and_user_ids(temp_dir):
    output_filename = temp_dir / "instagram-profile-3.csv"
    assert not output_filename.exists()
    collect_profile(
        client_class=Instagram,
        usernames_or_ids=INSTAGRAM_USER_MIX,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == len(INSTAGRAM_USER_MIX)
    user_ids_found = set(row["id"] for row in data)
    assert user_ids_found == set(INSTAGRAM_USER_IDS)


def test_instagram_profile_posts(temp_dir):
    output_filename = temp_dir / "instagram-profile-posts-1.csv"
    assert not output_filename.exists()
    max_posts = 25
    max_posts_per_user = 10
    assert len(INSTAGRAM_USER_MIX) * max_posts_per_user > max_posts  # Guarantee the function will enforce `max_posts`
    collect_profile_posts(
        client_class=Instagram,
        usernames_or_ids=INSTAGRAM_USER_MIX,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        max_posts_per_user=max_posts_per_user,
        max_posts=max_posts,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    user_ids_found = set(row["author_id"] for row in data)
    # Test if it's a subset because user can share posts from others, so author will be another profile
    assert set(INSTAGRAM_USER_IDS).issubset(user_ids_found)
    assert len(data) == max_posts


def test_instagram_archive(temp_dir):
    output_filename = temp_dir / "instagram-archive.zip"
    assert not output_filename.exists()
    max_posts = 20
    max_posts_per_user = 5
    archive(
        client_class=Instagram,
        usernames_or_ids=INSTAGRAM_USER_MIX,
        output_zip=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        max_posts_per_user=max_posts_per_user,
        max_posts=max_posts,
        quiet=True,
    )
    assert output_filename.exists()
    zf = ZipFile(output_filename)
    filenames = [fileinfo.filename for fileinfo in zf.filelist]
    assert "profile.csv" in filenames
    assert "post.csv" in filenames
    assert sum(1 for filename in filenames if filename.startswith("media/profile_")) > 0
    assert sum(1 for filename in filenames if filename.startswith("media/post_")) > 0


def test_instagram_post(temp_dir):
    output_filename = temp_dir / "instagram-post-1.csv"
    assert not output_filename.exists()
    max_posts = 3
    assert len(INSTAGRAM_POST_CODES) > max_posts
    instagram_post(
        post_codes=INSTAGRAM_POST_CODES,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        max_posts=max_posts,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == max_posts
    user_ids_found = set(row["author_id"] for row in data)
    assert len(user_ids_found) == 3  # The first 3 post codes are from different user each one
