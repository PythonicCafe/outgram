"""Export collected Instagram and Threads post metadata as Markdown or HTML."""

import csv
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

TIMING = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[.,]\d{3}")


NETWORKS = {
    "instagram": {"name": "Instagram", "profile_url": "https://instagram.com/{}"},
    "threads": {"name": "Threads", "profile_url": "https://www.threads.com/@{}"},
}


def post_url(post: Dict[str, str], network: str) -> str:
    """Return the canonical public URL for a collected post."""
    if network == "threads":
        return "https://www.threads.com/@{}/post/{}".format(post["username"], post["code"])
    kind = "reel" if post.get("type") == "video" else "p"
    return "https://www.instagram.com/{}/{}/".format(kind, post["code"])


def media_urls(media: str) -> List[str]:
    return [url.strip() for url in (media or "").splitlines() if url.strip()]


def is_video_url(url: str) -> bool:
    return Path(urlparse(url).path).suffix.lower() in {".mp4", ".mov", ".webm"}


def image_links(post: Dict[str, str], network: str) -> List[Tuple[int, str]]:
    """Return carousel image slide numbers and their public URLs."""
    if network != "instagram" or post.get("type") != "carousel":
        return []
    return [
        (index, "{}?img_index={}".format(post_url(post, network), index))
        for index, url in enumerate(media_urls(post.get("media", "")), start=1)
        if not is_video_url(url)
    ]


def read_transcription(post_id: str, transcriptions_dir: Optional[Path]) -> str:
    """Read the first external VTT transcription for a post, without VTT metadata."""
    if transcriptions_dir is None:
        return ""
    candidates = sorted(transcriptions_dir.glob("post_{}_*.vtt".format(post_id)))
    if not candidates:
        return ""

    lines = []
    for raw in candidates[0].read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or TIMING.match(line) or line.isdigit():
            continue
        lines.append(line)
    return "\n".join(lines)


def format_datetime(value: str) -> str:
    date = datetime.fromisoformat(value).astimezone(timezone.utc)
    return date.strftime("%Y-%m-%d %H:%M:%S UTC")


def author_label(post: Dict[str, str], network: str) -> str:
    username_key = "username" if network == "threads" else "author_username"
    username = post.get(username_key, "").strip()
    name = post.get("author_full_name", "").strip()
    if not username:
        return ""
    label = "@{}".format(username)
    if name and name.casefold() != username.casefold():
        label += " ({})".format(name)
    return label


def has_video(post: Dict[str, str]) -> bool:
    return post.get("type") == "video" or any(is_video_url(url) for url in media_urls(post.get("media", "")))


def markdown_document(
    posts: Iterable[Dict[str, str]],
    network: str,
    profile: str,
    collected_at: str,
    transcriptions_dir: Optional[Path],
) -> str:
    posts = list(posts)
    network_info = NETWORKS[network]
    network_name = network_info["name"]
    output = [
        "# {}: {}".format(network_name, profile),
        "",
        "Posts from [{} profile {}]({}) — collected at {}.".format(
            network_name, profile, network_info["profile_url"].format(profile), collected_at
        ),
        "",
        "Total catalogued posts: **{}**. Times are in **UTC**.".format(len(posts)),
    ]
    for post in posts:
        url = post_url(post, network)
        details = ["[View on {}]({})".format(network_name, url)]
        if post.get("type"):
            details.append("Type: {}".format(post["type"]))
        photos = image_links(post, network)
        if photos:
            details.append("Photos: " + " ".join("[{}]({})".format(index, link) for index, link in photos))
        if post.get("pinned", "").strip().lower() in {"1", "true", "yes"}:
            details.append("Pinned")
        output.extend(["", "## Post {}".format(format_datetime(post["published_at"])), "", " · ".join(details), ""])
        label = author_label(post, network)
        if label:
            username = post["username"] if network == "threads" else post["author_username"]
            output.append("**Original author:** [{}]({})".format(label, network_info["profile_url"].format(username.strip())))
        else:
            output.append("**Original author:** not provided")
        text = post.get("text", "").strip()
        if text:
            output.extend(["", text])
        transcription = read_transcription(post["id"], transcriptions_dir)
        if transcription:
            output.extend(["", "-----", "", "**Transcription:**", "", transcription])
        elif has_video(post):
            output.extend(["", "-----", "", "**Transcription:** unavailable in collected data."])
    return "\n".join(output) + "\n"


def html_document(
    posts: Iterable[Dict[str, str]],
    network: str,
    profile: str,
    collected_at: str,
    transcriptions_dir: Optional[Path],
) -> str:
    posts = list(posts)
    network_info = NETWORKS[network]
    network_name = network_info["name"]
    escaped_profile = html.escape(profile)
    output = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>{}: {}</title></head><body>".format(network_name, escaped_profile),
        "<h1>{}: {}</h1>".format(network_name, escaped_profile),
        '<p>Posts from <a href="{}">{} profile {}</a> — collected at {}.</p>'.format(
            html.escape(network_info["profile_url"].format(profile), quote=True),
            network_name,
            escaped_profile,
            html.escape(collected_at),
        ),
        "<p>Total catalogued posts: <strong>{}</strong>. Times are in <strong>UTC</strong>.</p>".format(len(posts)),
    ]
    for post in posts:
        url = post_url(post, network)
        output.append("<article><h2>Post {}</h2>".format(html.escape(format_datetime(post["published_at"]))))
        details = ['<a href="{}">View on {}</a>'.format(html.escape(url, quote=True), network_name)]
        if post.get("type"):
            details.append("Type: {}".format(html.escape(post["type"])))
        photos = image_links(post, network)
        if photos:
            details.append("Photos: " + " ".join('<a href="{}">{}</a>'.format(html.escape(link, quote=True), index) for index, link in photos))
        if post.get("pinned", "").strip().lower() in {"1", "true", "yes"}:
            details.append("Pinned")
        output.append("<p>{}</p>".format(" &middot; ".join(details)))
        label = author_label(post, network)
        if label:
            username = post["username"] if network == "threads" else post["author_username"]
            output.append(
                '<p><strong>Original author:</strong> <a href="{}">{}</a></p>'.format(
                    html.escape(network_info["profile_url"].format(username.strip()), quote=True), html.escape(label)
                )
            )
        else:
            output.append("<p><strong>Original author:</strong> not provided</p>")
        text = post.get("text", "").strip()
        if text:
            output.append("<p>{}</p>".format(html.escape(text).replace("\n", "<br>")))
        transcription = read_transcription(post["id"], transcriptions_dir)
        if transcription:
            output.append("<hr><h3>Transcription</h3><p>{}</p>".format(html.escape(transcription).replace("\n", "<br>")))
        elif has_video(post):
            output.append("<hr><p><strong>Transcription:</strong> unavailable in collected data.</p>")
        output.append("</article>")
    output.append("</body></html>")
    return "\n".join(output) + "\n"


def export_catalog(
    network: str,
    input_csv: Path,
    output: Path,
    profile: str,
    collected_at: str,
    transcriptions_dir: Optional[Path],
    output_format: Optional[str] = None,
) -> List[Path]:
    """Export a collected post CSV, returning the files written."""
    with input_csv.open(encoding="utf-8", newline="") as file_obj:
        posts = list(csv.DictReader(file_obj))
    documents = {
        "markdown": (".md", markdown_document(posts, network, profile, collected_at, transcriptions_dir)),
        "html": (".html", html_document(posts, network, profile, collected_at, transcriptions_dir)),
    }
    formats = ["markdown", "html"] if output_format is None else ["markdown" if output_format == "md" else output_format]
    written = []
    for current_format in formats:
        suffix, document = documents[current_format]
        destination = output if len(formats) == 1 else output.with_suffix(suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document, encoding="utf-8")
        written.append(destination)
    return written


def export_instagram_catalog(
    input_csv: Path,
    output: Path,
    profile: str,
    collected_at: str,
    transcriptions_dir: Optional[Path],
    output_format: Optional[str] = None,
) -> List[Path]:
    """Export a collected Instagram CSV, returning the files written."""
    return export_catalog(
        "instagram", input_csv, output, profile, collected_at, transcriptions_dir, output_format=output_format
    )


def export_threads_catalog(
    input_csv: Path,
    output: Path,
    profile: str,
    collected_at: str,
    transcriptions_dir: Optional[Path],
    output_format: Optional[str] = None,
) -> List[Path]:
    """Export a collected Threads CSV, returning the files written."""
    return export_catalog(
        "threads", input_csv, output, profile, collected_at, transcriptions_dir, output_format=output_format
    )
