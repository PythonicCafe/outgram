"""End-to-end tests for the command-line interface main functions, which will run most part of the codebase"""

import csv
import random
from collections import Counter
from zipfile import ZipFile

from outgram.cli import archive, collect_profile, collect_profile_posts
from outgram.threads import Threads

MIN_WAIT = 5.0
MAX_WAIT = 10.0
THREADS_USERNAME_ID = {
    "ayubionet": "5633396222",
    "diogocortiz": "197762208",
    "wsj": "18133069",
    "nonoinvestidor": "42799100757",
    "filosofia.liquida": "6828796459",
    "mulheresdocafemataotomazina": "3540507650",
}
THREADS_USERNAMES = list(THREADS_USERNAME_ID.keys())
THREADS_USER_IDS = list(THREADS_USERNAME_ID.values())
THREADS_USER_MIX = []
for index, (username, user_id) in enumerate(THREADS_USERNAME_ID.items()):
    if index < 3:
        THREADS_USER_MIX.append(username)
    else:
        THREADS_USER_MIX.append(user_id)
random.shuffle(THREADS_USERNAMES)
random.shuffle(THREADS_USER_IDS)
random.shuffle(THREADS_USER_MIX)


def test_threads_profile_with_usernames(temp_dir):
    output_filename = temp_dir / "threads-profile-1.csv"
    assert not output_filename.exists()
    collect_profile(
        client_class=Threads,
        usernames_or_ids=THREADS_USERNAMES,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == len(THREADS_USERNAMES)
    usernames_found = set(row["username"] for row in data)
    assert usernames_found == set(THREADS_USERNAMES)


def test_threads_profile_with_user_ids(temp_dir):
    output_filename = temp_dir / "threads-profile-2.csv"
    assert not output_filename.exists()
    collect_profile(
        client_class=Threads,
        usernames_or_ids=THREADS_USER_IDS,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == len(THREADS_USER_IDS)
    user_ids_found = set(row["id"] for row in data)
    assert user_ids_found == set(THREADS_USER_IDS)


def test_threads_profile_with_usernames_and_user_ids(temp_dir):
    output_filename = temp_dir / "threads-profile-3.csv"
    assert not output_filename.exists()
    collect_profile(
        client_class=Threads,
        usernames_or_ids=THREADS_USER_MIX,
        output_csv=output_filename,
        min_wait=MIN_WAIT,
        max_wait=MAX_WAIT,
        quiet=True,
    )
    assert output_filename.exists()
    with output_filename.open() as fobj:
        data = list(csv.DictReader(fobj))
    assert len(data) == len(THREADS_USER_MIX)
    user_ids_found = set(row["id"] for row in data)
    assert user_ids_found == set(THREADS_USER_IDS)


def test_threads_profile_posts(temp_dir):
    output_filename = temp_dir / "threads-profile-posts-1.csv"
    assert not output_filename.exists()
    max_posts = 50
    max_posts_per_user = 10
    collect_profile_posts(
        client_class=Threads,
        usernames_or_ids=THREADS_USER_MIX,
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
    counter = Counter(row["user_id"] for row in data)
    user_ids_found = set(counter.keys())
    assert user_ids_found.issubset(THREADS_USER_IDS)
    assert len(data) == max_posts
    assert set(counter.values()) == {max_posts_per_user}


def test_threads_archive(temp_dir):
    output_filename = temp_dir / "threads-archive.zip"
    assert not output_filename.exists()
    max_posts = 20
    max_posts_per_user = 5
    archive(
        client_class=Threads,
        usernames_or_ids=THREADS_USER_MIX,
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
