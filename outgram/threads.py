import datetime
import json
from html.parser import HTMLParser
from typing import Any, Dict, Generator, List, Union

from .client import BaseClient
from .models import Link, Picture, ThreadsPost, ThreadsProfile, Video


class ThreadsPublicPageHTMLParser(HTMLParser):
    """Collect JSON script contents from a public Threads profile page."""

    def __init__(self):
        super().__init__()
        self.scripts = []
        self._script_parts = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._script_parts = []

    def handle_data(self, data):
        if self._script_parts is not None:
            self._script_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script_parts is not None:
            self.scripts.append("".join(self._script_parts))
            self._script_parts = None


class Threads(BaseClient):
    main_url = "https://www.threads.com/"

    # TODO: implement authentication
    # TODO: list post comments (needs authentication)

    def __post_init__(self):
        self.session.headers.update({"origin": self.main_url.rstrip("/")})
        self._user_id_cache = {}

    @staticmethod
    def _public_page_headers() -> Dict[str, str]:
        return {
            "accept": "text/html",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
        }

    @staticmethod
    def _relay_results(value: Any) -> Generator[Dict[str, Any], None, None]:
        if isinstance(value, dict):
            for item in value.values():
                yield from Threads._relay_results(item)
            return
        if not isinstance(value, list):
            return
        if (
            len(value) == 4
            and value[0] == "RelayPrefetchedStreamCache"
            and value[1] == "next"
            and isinstance(value[3], list)
            and len(value[3]) == 2
            and isinstance(value[3][1], dict)
        ):
            bbox = value[3][1].get("__bbox")
            result = bbox.get("result") if isinstance(bbox, dict) else None
            if isinstance(result, dict) and isinstance(result.get("data"), dict):
                yield result
        for item in value:
            yield from Threads._relay_results(item)

    def _public_page_results(self, username: str) -> List[Dict[str, Any]]:
        response = self.request(
            method="GET",
            url=f"{self.main_url}@{username}",
            headers=self._public_page_headers(),
        )
        if response.status_code in (401, 403, 429):
            raise RuntimeError(
                f"Public Threads collection was blocked for @{username} (HTTP {response.status_code}); try again later"
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Public Threads profile request failed for @{username} (HTTP {response.status_code})"
            )
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            raise RuntimeError(
                f"Public Threads profile response was unavailable for @{username} (expected HTML)"
            )
        parser = ThreadsPublicPageHTMLParser()
        parser.feed(response.text)
        results = []
        for script in parser.scripts:
            if "RelayPrefetchedStreamCache" not in script:
                continue
            try:
                payload = json.loads(script)
            except ValueError:
                continue
            results.extend(self._relay_results(payload))
        if not results:
            raise RuntimeError(
                f"Public Threads profile response had no SSR data for @{username}"
            )
        return results

    @staticmethod
    def _result_with(data_name: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        for result in results:
            if isinstance(result["data"].get(data_name), dict):
                return result
        raise RuntimeError(
            f"Public Threads profile response had no {data_name} SSR data"
        )

    def _extract_profile(self, json_data: Dict[str, Any]) -> ThreadsProfile:
        user = json_data["data"].get("user")
        if not isinstance(user, dict):
            raise RuntimeError("Public Threads profile response had no user data")
        pictures = []
        profile_picture_url = user.get("profile_pic_url")
        if profile_picture_url:
            pictures.append(Picture(url=profile_picture_url, width=150, height=150))
        pictures.extend(
            Picture(url=pic["url"], width=pic.get("width"), height=pic.get("height"))
            for pic in user.get("hd_profile_pic_versions") or []
            if pic.get("url")
        )
        bio_links = [
            Link(
                url=link["url"],
                is_verified=link.get("is_verified"),
                id=int(link["link_id"]) if link.get("link_id") is not None else None,
            )
            for link in user.get("bio_links") or []
            if link.get("url")
        ]
        return ThreadsProfile(
            id=int(user["id"]),
            username=user["username"],
            full_name=user.get("full_name") or "",
            biography=user.get("biography") or "",
            is_verified=user.get("is_verified"),
            followers=user.get("follower_count"),
            pictures=pictures,
            is_private=user.get("text_post_app_is_private"),
            bio_links=bio_links,
            is_threads_only_user=user.get("is_threads_only_user"),
        )

    def _profile_from_public_page(
        self, username: str, raw: bool = False
    ) -> Union[ThreadsProfile, Dict[str, Any]]:
        result = self._result_with("user", self._public_page_results(username))
        if raw:
            return result
        profile = self._extract_profile(result)
        self._user_id_cache[profile.username] = profile.id
        return profile

    def simple_profile(
        self, username: str, raw: bool = False
    ) -> Union[ThreadsProfile, Dict[str, Any]]:
        """Get public profile information from the profile page SSR payload."""
        return self._profile_from_public_page(username, raw=raw)

    def profile_from_user_id(
        self, user_id: int, raw: bool = False
    ) -> Union[ThreadsProfile, Dict[str, Any]]:
        raise RuntimeError(
            "Public Threads profile lookup by numeric ID is currently unavailable; use a username"
        )

    def profile_from_username(
        self, username: str, raw: bool = False
    ) -> Union[ThreadsProfile, Dict[str, Any]]:
        return self._profile_from_public_page(username, raw=raw)

    def profile(
        self, username_or_id: Union[str, int], raw: bool = False
    ) -> Union[ThreadsProfile, Dict[str, Any]]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            return self.profile_from_user_id(username_or_id, raw=raw)
        return self.profile_from_username(username_or_id, raw=raw)

    def _extract_post(self, post_data: Dict[str, Any]) -> ThreadsPost:
        inner_media = post_data.get("carousel_media") or [post_data]
        post_media = []
        for obj in inner_media:
            candidates = (obj.get("image_versions2") or {}).get("candidates") or []
            pictures = [
                Picture(pic["url"], pic.get("width"), pic.get("height"))
                for pic in candidates
                if pic.get("url")
            ]
            pictures.sort(key=lambda picture: picture.width or 0, reverse=True)
            thumbnail = pictures[0] if pictures else None
            video_versions = obj.get("video_versions") or []
            if video_versions and video_versions[0].get("url"):
                version = video_versions[0]
                post_media.append(
                    Video(
                        type=version.get("type"),
                        url=version["url"],
                        width=version.get("width"),
                        height=version.get("height"),
                        thumbnail=thumbnail,
                    )
                )
            elif thumbnail:
                post_media.append(thumbnail)

        info = post_data.get("text_post_app_info") or {}
        fragments = (info.get("text_fragments") or {}).get("fragments") or []
        text = ""
        links = []
        for fragment in fragments:
            text += fragment.get("plaintext") or ""
            link = fragment.get("link_fragment") or {}
            if fragment.get("fragment_type") == "link" and link.get("uri"):
                links.append(
                    Link(url=link["uri"], display_text=link.get("display_text"))
                )
        user = post_data["user"]
        return ThreadsPost(
            id=post_data["id"],
            user_id=int(user["pk"]),
            username=user["username"],
            is_verified=user.get("is_verified"),
            text=text,
            links=links,
            published_at=datetime.datetime.fromtimestamp(
                post_data["taken_at"], tz=datetime.timezone.utc
            ),
            likes=post_data.get("like_count"),
            replies=info.get("direct_reply_count", 0),
            reposts=info.get("repost_count", 0),
            quotes=info.get("quote_count", 0),
            is_private=user.get("text_post_app_is_private", False),
            media=post_media,
            reply_control=info.get("reply_control"),
            media_type=post_data.get("media_type"),
            accessibility_caption=post_data.get("accessibility_caption"),
            is_paid_partnership=post_data.get("is_paid_partnership"),
            like_and_view_counts_disabled=post_data.get(
                "like_and_view_counts_disabled"
            ),
            has_audio=post_data.get("has_audio"),
            original_width=post_data.get("original_width"),
            original_height=post_data.get("original_height"),
            code=post_data.get("code"),
            reshares=info.get("reshare_count"),
        )

    @staticmethod
    def _timeline(result: Dict[str, Any]) -> Dict[str, Any]:
        timeline = result["data"].get("mediaData")
        if not isinstance(timeline, dict) or not isinstance(
            timeline.get("edges"), list
        ):
            raise RuntimeError("Public Threads profile response had no timeline data")
        return timeline

    def profile_posts_from_user_id(
        self, user_id: int, raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        raise RuntimeError(
            "Public Threads timeline lookup by numeric ID is currently unavailable; use a username"
        )
        yield None

    def profile_posts_from_username(
        self, username: str, raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        timeline = self._timeline(
            self._result_with("mediaData", self._public_page_results(username))
        )
        for edge in timeline["edges"]:
            node = edge.get("node") if isinstance(edge, dict) else None
            items = node.get("thread_items") if isinstance(node, dict) else None
            post_data = (
                items[0].get("post") if items and isinstance(items[0], dict) else None
            )
            if not isinstance(post_data, dict):
                continue
            if raw:
                yield post_data
            else:
                post = self._extract_post(post_data)
                self._user_id_cache[post.username] = post.user_id
                yield post
        page_info = timeline.get("page_info") or {}
        if page_info.get("has_next_page") and page_info.get("end_cursor"):
            raise RuntimeError(
                "Public Threads timeline pagination is currently unavailable; collect only the first public page"
            )

    def profile_posts(
        self, username_or_id: Union[str, int], raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            yield from self.profile_posts_from_user_id(username_or_id, raw=raw)
        else:
            yield from self.profile_posts_from_username(username_or_id, raw=raw)
