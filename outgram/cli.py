import argparse
import csv
import io
from pathlib import Path
from typing import Any, List, Optional, Union
from zipfile import ZipFile

from . import __version__
from .instagram import Instagram
from .threads import Threads

# TODO: implement threads-archive


class ProgressBar:
    """Simple and easy-to-user progress bar for the command-line interface"""

    def __init__(self, total: Optional[int] = None, title: Optional[str] = None):
        self.last_line_length = None
        self.title = title
        self.total = total

    def update(
        self,
        current: int,
        done: bool = False,
        total: Optional[int] = None,
        title: Optional[str] = None,
        suffix: Optional[str] = None,
        end="",
    ):
        if total is None:
            total = self.total
        if not done:  # The `current` item was started but not done yet
            percent = 100 * (current - 1 if current != 0 else 0) / total
        else:
            percent = (100 * current) / total
        title_str = title or self.title or ""
        suffix_str = suffix if suffix is not None else ""
        line = f"\r{title_str}{current:03d}/{total:03d} ({percent:3.2f}%){suffix_str}"
        if self.last_line_length is not None and self.last_line_length > len(line):
            print("\r" + " " * self.last_line_length, end="")
        print(line, flush=True, end=end)
        self.last_line_length = len(line)


class QuietProgressBar(ProgressBar):
    """A ProgressBar that does nothing, but has the same API"""

    def update(
        self,
        current: int,
        done: bool = False,
        total: Optional[int] = None,
        title: Optional[str] = None,
        suffix: Optional[str] = None,
        end="",
    ):
        pass


def collect_profile(
    client_class: Any,
    usernames_or_ids: List[Union[str, int]],
    output_csv: Path,
    min_wait: float,
    max_wait: float,
    quiet: bool = False,
):
    client = client_class(min_wait=min_wait, max_wait=max_wait)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open(mode="w") as fobj:
        writer = None
        ProgressClass = ProgressBar if not quiet else QuietProgressBar
        progress = ProgressClass(title=f"{client_class.__name__} Profile ", total=len(usernames_or_ids))
        for index, username_or_id in enumerate(usernames_or_ids, start=1):
            progress.update(index, done=False)
            profile = client.profile(username_or_id)
            row = profile.serialize()
            if writer is None:
                writer = csv.DictWriter(fobj, fieldnames=list(row.keys()))
                writer.writeheader()
            writer.writerow(row)
            progress.update(index, done=True)
        progress.update(index, done=True, end="\n")


def collect_profile_posts(
    client_class: Any,
    usernames_or_ids: List[Union[str, int]],
    output_csv: Path,
    min_wait: float,
    max_wait: float,
    max_posts_per_user: Optional[int] = None,
    max_posts: Optional[int] = None,
    quiet: bool = False,
):
    client = client_class(min_wait=min_wait, max_wait=max_wait)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open(mode="w") as fobj:
        writer = None
        ProgressClass = ProgressBar if not quiet else QuietProgressBar
        progress = ProgressClass(title=f"{client_class.__name__} Profile ", total=len(usernames_or_ids))
        downloaded_posts = 0
        finished = False
        for index, username_or_id in enumerate(usernames_or_ids, start=1):
            progress.update(index, done=False)
            for post_index, post in enumerate(client.profile_posts(username_or_id), start=1):
                row = post.serialize()
                if writer is None:
                    writer = csv.DictWriter(fobj, fieldnames=list(row.keys()))
                    writer.writeheader()
                writer.writerow(row)
                progress.update(index, suffix=f" Post {post_index:03d}", done=False)
                downloaded_posts += 1
                if max_posts is not None and downloaded_posts == max_posts:
                    finished = True
                    break
                elif max_posts_per_user is not None and post_index == max_posts_per_user:
                    break
            progress.update(index, done=True)
            if finished:
                break
        progress.update(index, done=True, end="\n")


def archive(
    client_class: Any,
    usernames_or_ids: List[Union[str, int]],
    output_zip: Path,
    min_wait: float,
    max_wait: float,
    max_posts_per_user: Optional[int] = None,
    max_posts: Optional[int] = None,
    quiet: bool = False,
):
    client = client_class(min_wait=min_wait, max_wait=max_wait)
    zf = ZipFile(output_zip, mode="w")

    profiles = []
    ProgressClass = ProgressBar if not quiet else QuietProgressBar
    progress = ProgressClass(title=f"{client_class.__name__} Profile ", total=len(usernames_or_ids))
    with io.TextIOWrapper(zf.open("profile.csv", mode="w"), encoding="utf-8") as fobj:
        writer = None
        for index, username_or_id in enumerate(usernames_or_ids, start=1):
            progress.update(index, done=False)
            profile = client.profile(username_or_id)
            profiles.append(profile)
            row = profile.serialize()
            if writer is None:
                writer = csv.DictWriter(fobj, fieldnames=list(row.keys()))
                writer.writeheader()
            writer.writerow(row)
            progress.update(index, done=True)
        progress.update(index, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile media (download) ", total=len(profiles))
    progress.update(0, done=True)
    for index, media in enumerate(client.download_many(profiles), start=1):
        progress.update(index, done=True)
    progress.update(index, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile media (save) ", total=len(profiles))
    for index, profile in enumerate(profiles, start=1):
        progress.update(index, done=False)
        extension = profile.picture.content_type.split("/")[-1].lower()
        extension = {"jpeg": "jpg"}.get(extension, extension)
        with zf.open(f"media/profile_{profile.id}.{extension}", mode="w") as fobj:
            fobj.write(profile.picture.content)
        progress.update(index, done=True)
    progress.update(index, done=True, end="\n")

    posts = []
    total_post_media = 0
    with io.TextIOWrapper(zf.open("post.csv", mode="w"), encoding="utf-8") as fobj:
        writer = None
        progress = ProgressClass(title=f"{client_class.__name__} Profile posts ", total=len(profiles))
        downloaded_posts = 0
        finished = False
        for index, profile in enumerate(profiles, start=1):
            progress.update(index, done=False)
            for post_index, post in enumerate(client.profile_posts(profile.username), start=1):
                posts.append(post)
                total_post_media += len(post.get_media())
                row = post.serialize()
                if writer is None:
                    writer = csv.DictWriter(fobj, fieldnames=list(row.keys()))
                    writer.writeheader()
                writer.writerow(row)
                progress.update(index, suffix=f" Post {post_index:03d}", done=False)
                downloaded_posts += 1
                if max_posts is not None and downloaded_posts == max_posts:
                    finished = True
                    break
                elif max_posts_per_user is not None and post_index == max_posts_per_user:
                    break
            progress.update(index, done=True)
            if finished:
                break
        progress.update(index, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile posts media (download) ", total=total_post_media)
    progress.update(0, done=True)
    for index, media in enumerate(client.download_many(posts), start=1):
        progress.update(index, done=True)
    progress.update(index, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile posts media (save) ", total=total_post_media)
    counter = 0
    for post in posts:
        for post_media_index, media in enumerate(post.get_media(), start=1):
            counter += 1
            progress.update(counter, done=False)
            extension = media.content_type.split("/")[-1].lower()
            extension = {"jpeg": "jpg"}.get(extension, extension)
            with zf.open(f"media/post_{post.id}_{post_media_index:03d}.{extension}", mode="w") as fobj:
                fobj.write(media.content)
            progress.update(counter, done=True)
    progress.update(counter, done=True, end="\n")

    zf.close()


def instagram_post(
    post_codes: List[str],
    output_csv: Path,
    min_wait: float,
    max_wait: float,
    max_posts: Optional[int] = None,
    quiet: bool = False,
):
    client = Instagram(min_wait=min_wait, max_wait=max_wait)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open(mode="w") as fobj:
        writer = None
        ProgressClass = ProgressBar if not quiet else QuietProgressBar
        progress = ProgressClass(title="Post ", total=len(post_codes))
        progress.update(0, done=False)
        for index, post_code in enumerate(post_codes, start=1):
            post = client.post(post_code)
            row = post.serialize()
            if writer is None:
                writer = csv.DictWriter(fobj, fieldnames=list(row.keys()))
                writer.writeheader()
            writer.writerow(row)
            progress.update(index, done=True)
            if max_posts is not None and index == max_posts:
                break
        progress.update(index, done=True, end="\n")


def main():
    MAX_POSTS = 96
    MAX_POSTS_PER_USER = 48
    class_map = {"instagram": Instagram, "threads": Threads}

    parser = argparse.ArgumentParser(prog="outgram")
    parser.add_argument("--version", action="version", version=f"%(prog)s {'.'.join(map(str, __version__))}")
    parser.add_argument(
        "--min-wait", "-t", type=float, default=0.5, help="Minimum time (in seconds) to wait between requests"
    )
    parser.add_argument(
        "--max-wait", "-T", type=float, default=2.0, help="Maximum time (in seconds) to wait between requests"
    )
    subparsers = parser.add_subparsers(dest="network", required=True)

    instagram_parser = subparsers.add_parser("instagram")
    threads_parser = subparsers.add_parser("threads")
    network_subparsers = {
        "instagram": instagram_parser.add_subparsers(dest="action", required=True),
        "threads": threads_parser.add_subparsers(dest="action", required=True),
    }

    for network in class_map.keys():
        network_subparser = network_subparsers[network]
        parser_profile = network_subparser.add_parser(
            "profile",
            description="Get information regarding one or more profiles. Only the biggest picture URL is exported. Only the URLs of bio_links are exported (separated by \\n)",
        )
        parser_profile.add_argument("--quiet", "-q", action="store_true", help="Do not show a progress bar")
        parser_profile.add_argument("username_or_id", nargs="+")
        parser_profile.add_argument("output_csv", type=Path)

        parser_profile_posts = network_subparser.add_parser(
            "profile-posts",
            description="Get latests posts of a list of profiles. A list of usernames or user IDs can be passed (it takes one more request per username, since we need to figure out the user ID). Only the URLs of links, pictures and videos are exported (separated by \\n)",
        )
        parser_profile_posts.add_argument("--quiet", "-q", action="store_true", help="Do not show a progress bar")
        parser_profile_posts.add_argument(
            "--max-posts-per-user", "-m", type=int, default=MAX_POSTS_PER_USER, help="Maximum posts to get per user"
        )
        parser_profile_posts.add_argument(
            "--max-posts", "-M", type=int, default=MAX_POSTS, help="Maximum posts to get (total)"
        )
        parser_profile_posts.add_argument("username_or_id", nargs="+")
        parser_profile_posts.add_argument("output_csv", type=Path)

        parser_archive = network_subparser.add_parser(
            "archive",
            description="Get all posts and media metadata and download media for a list of profiles and save into a ZIP file. A list of usernames or user IDs can be passed.",
        )
        parser_archive.add_argument("--quiet", "-q", action="store_true", help="Do not show a progress bar")
        parser_archive.add_argument(
            "--max-posts-per-user", "-m", type=int, default=MAX_POSTS_PER_USER, help="Maximum posts to get per user"
        )
        parser_archive.add_argument(
            "--max-posts", "-M", type=int, default=MAX_POSTS, help="Maximum posts to get (total)"
        )
        parser_archive.add_argument("username_or_id", nargs="+")
        parser_archive.add_argument("output_zip", type=Path)

    parser_instagram_post = network_subparsers["instagram"].add_parser(
        "post",
        description="Get posts from a list of post codes (the code is found in the URL: <https://www.instagram.com/p/CODE/>).",
    )
    parser_instagram_post.add_argument("--quiet", "-q", action="store_true", help="Do not show a progress bar")
    parser_instagram_post.add_argument(
        "--max-posts", "-M", type=int, default=MAX_POSTS, help="Maximum posts to get (total)"
    )
    parser_instagram_post.add_argument("post_code", nargs="+")
    parser_instagram_post.add_argument("output_csv", type=Path)

    args = parser.parse_args()

    if args.action == "profile":
        collect_profile(
            client_class=class_map[args.network],
            usernames_or_ids=args.username_or_id,
            output_csv=args.output_csv,
            min_wait=args.min_wait,
            max_wait=args.max_wait,
            quiet=args.quiet,
        )

    elif args.action == "profile-posts":
        collect_profile_posts(
            client_class=class_map[args.network],
            usernames_or_ids=args.username_or_id,
            output_csv=args.output_csv,
            min_wait=args.min_wait,
            max_wait=args.max_wait,
            max_posts_per_user=args.max_posts_per_user,
            max_posts=args.max_posts,
            quiet=args.quiet,
        )

    elif args.action == "archive":
        archive(
            client_class=class_map[args.network],
            usernames_or_ids=args.username_or_id,
            output_zip=args.output_zip,
            min_wait=args.min_wait,
            max_wait=args.max_wait,
            max_posts_per_user=args.max_posts_per_user,
            max_posts=args.max_posts,
            quiet=args.quiet,
        )

    elif (args.network, args.action) == ("instagram", "post"):
        instagram_post(
            post_codes=args.post_code,
            output_csv=args.output_csv,
            min_wait=args.min_wait,
            max_wait=args.max_wait,
            max_posts=args.max_posts,
            quiet=args.quiet,
        )

    # TODO: implement threads-post


if __name__ == "__main__":
    main()
