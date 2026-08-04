import argparse
import csv
import datetime
import io
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union
from zipfile import ZipFile, ZipInfo

from . import __version__
from .export import export_instagram_catalog, export_threads_catalog
from .instagram import Instagram
from .threads import Threads


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
            percent = 0 if not total else 100 * (current - 1 if current != 0 else 0) / total
        else:
            percent = 100 if not total else (100 * current) / total
        title_str = title or self.title or ""
        suffix_str = suffix if suffix is not None else ""
        line = f"\r{title_str}{current:03d}/{total:03d} ({percent:3.2f}%){suffix_str}"
        if self.last_line_length is not None and self.last_line_length > len(line):
            print("\r" + " " * self.last_line_length, end="", file=sys.stderr)
        print(line, flush=True, end=end, file=sys.stderr)
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
    with output_csv.open(mode="w", encoding="utf-8", newline="") as fobj:
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
        progress.update(index if usernames_or_ids else 0, done=True, end="\n")
    return output_csv


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
    with output_csv.open(mode="w", encoding="utf-8", newline="") as fobj:
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
        progress.update(index if usernames_or_ids else 0, done=True, end="\n")
    return output_csv


def _archive_member(
    archive: ZipFile, filename: str, date_time: Tuple[int, int, int, int, int, int]
):
    """Open an archive member with the archive creation timestamp."""
    return archive.open(ZipInfo(filename=filename, date_time=date_time), mode="w")


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
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    archive_date_time = datetime.datetime.now().timetuple()[:6]
    zf = ZipFile(output_zip, mode="w")

    profiles = []
    ProgressClass = ProgressBar if not quiet else QuietProgressBar
    progress = ProgressClass(title=f"{client_class.__name__} Profile ", total=len(usernames_or_ids))
    with io.TextIOWrapper(
        _archive_member(zf, "profile.csv", archive_date_time), encoding="utf-8", newline=""
    ) as fobj:
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
        progress.update(index if usernames_or_ids else 0, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile media (download) ", total=len(profiles))
    progress.update(0, done=True)
    if profiles:
        for index, media in enumerate(client.download_many(profiles), start=1):
            progress.update(index, done=True)
    progress.update(index if profiles else 0, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile media (save) ", total=len(profiles))
    for index, profile in enumerate(profiles, start=1):
        progress.update(index, done=False)
        picture = getattr(profile, "picture", None)
        if picture is not None and picture.content is not None and picture.content_type:
            extension = picture.content_type.split("/")[-1].lower()
            extension = {"jpeg": "jpg"}.get(extension, extension)
            with _archive_member(
                zf, f"media/profile_{profile.id}.{extension}", archive_date_time
            ) as fobj:
                fobj.write(picture.content)
        progress.update(index, done=True)
    progress.update(index if profiles else 0, done=True, end="\n")

    posts = []
    total_post_media = 0
    with io.TextIOWrapper(
        _archive_member(zf, "post.csv", archive_date_time), encoding="utf-8", newline=""
    ) as fobj:
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
        progress.update(index if profiles else 0, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile posts media (download) ", total=total_post_media)
    progress.update(0, done=True)
    if posts:
        for index, media in enumerate(client.download_many(posts), start=1):
            progress.update(index, done=True)
    progress.update(index if total_post_media else 0, done=True, end="\n")

    progress = ProgressClass(title=f"{client_class.__name__} Profile posts media (save) ", total=total_post_media)
    counter = 0
    for post in posts:
        for post_media_index, media in enumerate(post.get_media(), start=1):
            counter += 1
            progress.update(counter, done=False)
            extension = media.content_type.split("/")[-1].lower()
            extension = {"jpeg": "jpg"}.get(extension, extension)
            with _archive_member(
                zf,
                f"media/post_{post.id}_{post_media_index:03d}.{extension}",
                archive_date_time,
            ) as fobj:
                fobj.write(media.content)
            progress.update(counter, done=True)
    progress.update(counter, done=True, end="\n")

    zf.close()
    return output_zip


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
    with output_csv.open(mode="w", encoding="utf-8", newline="") as fobj:
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
        progress.update(index if post_codes else 0, done=True, end="\n")
    return output_csv


def _create_parser():
    max_posts = 96
    max_posts_per_user = 48
    parser = argparse.ArgumentParser(prog="outgram")
    parser.add_argument("--version", action="version", version="%(prog)s {}".format(".".join(map(str, __version__))))
    subparsers = parser.add_subparsers(dest="network", metavar="NETWORK", required=True, help="Social network")
    pacing_parser = argparse.ArgumentParser(add_help=False)
    pacing_parser.add_argument("-t", "--min-wait", metavar="MIN_SECONDS", type=float, default=0.5, help="Minimum wait between requests")
    pacing_parser.add_argument("-T", "--max-wait", metavar="MAX_SECONDS", type=float, default=2.0, help="Maximum wait between requests")
    collection_parser = argparse.ArgumentParser(add_help=False)
    collection_parser.add_argument("-q", "--quiet", action="store_true", help="Do not show progress")

    network_subparsers = {}
    for network in ("instagram", "threads"):
        network_parser = subparsers.add_parser(network, help="Collect {} public data".format(network.title()))
        network_subparsers[network] = network_parser.add_subparsers(dest="action", metavar="ACTION", required=True, help="Collection action")

    for network_subparser in network_subparsers.values():
        profile = network_subparser.add_parser("profile", parents=[pacing_parser, collection_parser], help="Collect profile metadata")
        profile.add_argument("username_or_id", metavar="USERNAME_OR_ID", nargs="+")
        profile.add_argument("output_csv", metavar="OUTPUT_CSV", type=Path)

        profile_posts = network_subparser.add_parser("profile-posts", parents=[pacing_parser, collection_parser], help="Collect latest profile posts")
        profile_posts.add_argument("-m", "--max-posts-per-user", metavar="LIMIT", type=int, default=max_posts_per_user, help="Maximum posts per profile")
        profile_posts.add_argument("-M", "--max-posts", metavar="LIMIT", type=int, default=max_posts, help="Maximum posts in total")
        profile_posts.add_argument("username_or_id", metavar="USERNAME_OR_ID", nargs="+")
        profile_posts.add_argument("output_csv", metavar="OUTPUT_CSV", type=Path)

        archive_parser = network_subparser.add_parser("archive", parents=[pacing_parser, collection_parser], help="Create a collection archive")
        archive_parser.add_argument("-m", "--max-posts-per-user", metavar="LIMIT", type=int, default=max_posts_per_user, help="Maximum posts per profile")
        archive_parser.add_argument("-M", "--max-posts", metavar="LIMIT", type=int, default=max_posts, help="Maximum posts in total")
        archive_parser.add_argument("username_or_id", metavar="USERNAME_OR_ID", nargs="+")
        archive_parser.add_argument("output_zip", metavar="OUTPUT_ZIP", type=Path)

        export_parser = network_subparser.add_parser("export", help="Export collected post metadata")
        export_parser.add_argument("input_csv", metavar="INPUT_CSV", type=Path, help="Collected post CSV file")
        export_parser.add_argument("username", metavar="USERNAME", help="Collected profile username")
        export_parser.add_argument("collected_at", metavar="COLLECTED_AT", help="Human-readable collection timestamp")
        export_parser.add_argument("output", metavar="OUTPUT", type=Path, help="Output path or prefix")
        export_parser.add_argument("-t", "--transcriptions-dir", metavar="DIRECTORY", type=Path, help="Directory containing external WebVTT transcription files")
        export_parser.add_argument("-f", "--format", dest="output_format", metavar="FORMAT", choices=("markdown", "md", "html"), default=None, help="Output format: markdown, md or html; default: Markdown and HTML")

    post = network_subparsers["instagram"].add_parser("post", parents=[pacing_parser, collection_parser], help="Collect posts by code")
    post.add_argument("-M", "--max-posts", metavar="LIMIT", type=int, default=max_posts, help="Maximum posts in total")
    post.add_argument("post_code", metavar="POST_CODE", nargs="+")
    post.add_argument("output_csv", metavar="OUTPUT_CSV", type=Path)
    return parser


def main(argv: Optional[List[str]] = None):
    class_map = {"instagram": Instagram, "threads": Threads}
    args = _create_parser().parse_args(argv)
    if args.action == "profile":
        return collect_profile(
            client_class=class_map[args.network], usernames_or_ids=args.username_or_id, output_csv=args.output_csv,
            min_wait=args.min_wait, max_wait=args.max_wait, quiet=args.quiet,
        )
    if args.action == "profile-posts":
        return collect_profile_posts(
            client_class=class_map[args.network], usernames_or_ids=args.username_or_id, output_csv=args.output_csv,
            min_wait=args.min_wait, max_wait=args.max_wait, max_posts_per_user=args.max_posts_per_user,
            max_posts=args.max_posts, quiet=args.quiet,
        )
    if args.action == "archive":
        return archive(
            client_class=class_map[args.network], usernames_or_ids=args.username_or_id, output_zip=args.output_zip,
            min_wait=args.min_wait, max_wait=args.max_wait, max_posts_per_user=args.max_posts_per_user,
            max_posts=args.max_posts, quiet=args.quiet,
        )
    if (args.network, args.action) == ("instagram", "post"):
        return instagram_post(
            post_codes=args.post_code, output_csv=args.output_csv, min_wait=args.min_wait, max_wait=args.max_wait,
            max_posts=args.max_posts, quiet=args.quiet,
        )
    exporters = {"instagram": export_instagram_catalog, "threads": export_threads_catalog}
    if args.action == "export":
        return exporters[args.network](
            input_csv=args.input_csv, output=args.output, profile=args.username, collected_at=args.collected_at,
            transcriptions_dir=args.transcriptions_dir, output_format=args.output_format,
        )
    raise RuntimeError("Unsupported outgram command: {} {}".format(args.network, args.action))


if __name__ == "__main__":
    main()
