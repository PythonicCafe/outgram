import datetime
import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, Generator, List, Optional, Union
from urllib.parse import urljoin

from .client import BaseClient
from .models import InstagramPost, InstagramProfile, Link, Location, Picture, Video
from .utils import REGEXP_LSD

REGEXP_INSTAGRAM_APP_ID = re.compile(r'"X-IG-App-ID"\s*:\s*"([^"]+)"')
REGEXP_INSTAGRAM_CSRF_TOKEN = re.compile(r'"csrf_token"\s*:\s*"([^"]+)"')
REGEXP_INSTAGRAM_PROFILE_ID = re.compile(r'"page_id"\s*:\s*"profilePage_([^"]+)"')
REGEXP_DID = re.compile("([0-9A-Z]+-[0-9A-Z]+-[0-9A-Z]+-[0-9A-Z]+-[0-9A-Z]+)")
REGEXP_PROFILE_COUNTS = re.compile(r"([\d,.]+[KM]?) Followers, ([\d,.]+[KM]?) Following, ([\d,.]+[KM]?) Posts")


class InstagramPublicPageHTMLParser(HTMLParser):
    """Collect metadata and JSON bootstrap scripts from a public page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metadata = {}
        self.json_scripts = []
        self._is_json_script = False
        self._script_content = []

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if tag.lower() == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content is not None and key not in self.metadata:
                self.metadata[key] = content
        elif tag.lower() == "script" and attributes.get("type") == "application/json":
            self._is_json_script = True
            self._script_content = []

    def handle_data(self, data: str):
        if self._is_json_script:
            self._script_content.append(data)

    def handle_endtag(self, tag: str):
        if tag.lower() == "script" and self._is_json_script:
            self.json_scripts.append("".join(self._script_content))
            self._is_json_script = False
            self._script_content = []


# TODO: add username <-> user ID cache, so we avoid unneeded requests and the user don't need to manage this
class Instagram(BaseClient):
    main_url = "https://www.instagram.com/"
    graphql_url = "https://www.instagram.com/graphql/query"
    media_types_ids = {1: "photo", 2: "video", 8: "carousel"}
    media_types_names = {
        "XDTGraphVideo": "video",
        "XDTGraphSidecar": "carousel",
        "XDTGraphImage": "photo",
        # Legacy public GraphQL endpoint (used by logged-out web clients)
        "GraphVideo": "video",
        "GraphSidecar": "carousel",
        "GraphImage": "photo",
    }
    # Observed in the logged-out public Web client. Persisted query IDs can
    # expire; keep all request-specific settings together for maintenance.
    public_timeline_query = {
        "method": "GET",
        "url": graphql_url + "/",
        "headers": {"x-requested-with": "XMLHttpRequest"},
        "doc_id": "7950326061742207",
        "page_size": 12,
    }
    # Backward-compatible read-only alias. New code should use the complete
    # public_timeline_query configuration above.
    public_timeline_doc_id = public_timeline_query["doc_id"]
    public_post_query = {
        "method": "GET",
        "url": graphql_url + "/",
        "headers": {"x-requested-with": "XMLHttpRequest"},
        "doc_id": "36648847008092410",
        "variable_name": "mediaId",
    }

    # TODO: implement authentication
    # TODO: list post comments

    def __post_init__(self):
        self._user_id_cache = {}
        response = self.request(
            method="GET",
            url="https://www.instagram.com/ajax/bootloader-endpoint/",
            params={
                "modules": "PolarisLoggedOutContentWallDialog.react",
                "__d": "www",
                "__user": "0",
                "__a": "1",
                "__req": "d",
            },
        )
        html = response.content.decode(response.apparent_encoding)
        values = REGEXP_DID.findall(html)
        if values:
            self.session.cookies["ig_did"] = values[0]

        response = self.request(method="GET", url=self.main_url)
        html = response.content.decode(response.apparent_encoding)
        csrf_result = REGEXP_INSTAGRAM_CSRF_TOKEN.findall(html)
        app_id_result = REGEXP_INSTAGRAM_APP_ID.findall(html)
        self.lsd = REGEXP_LSD.findall(html)[0]
        self.session.headers.update(
            {
                "x-csrftoken": csrf_result[0],
                "X-IG-App-ID": app_id_result[0],
                "x-fb-lsd": self.lsd,
                "x-asbd-id": "359341",
                "x-ig-www-claim": "0",
            }
        )

    def user_id(self, username: str) -> int:
        response = self.request(method="GET", url=urljoin(self.main_url, username))
        html = response.content.decode(response.apparent_encoding)
        return int(REGEXP_INSTAGRAM_PROFILE_ID.findall(html)[0])

    def _user_info_from_user_id(self, user_id: int) -> Dict[str, Any]:
        """Resolve a public numeric user ID through Instagram's current user-info endpoint."""
        response = self.request(
            method="GET",
            url=f"{self.main_url}api/v1/users/{user_id}/info/",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        data = response.json()
        user = data.get("user")
        if not user or "username" not in user:
            raise RuntimeError(f"Cannot resolve Instagram user ID {user_id}: {data}")
        return user

    def profile_from_user_id(self, user_id: int, raw: bool = False) -> Union[InstagramProfile, Dict[str, Any]]:
        if not raw and user_id in self._user_id_cache.values():
            usernames = [username for username, cached_id in self._user_id_cache.items() if cached_id == user_id]
            if usernames:
                return self.profile_from_public_page(username=usernames[0], user_id=user_id)
        user = self._user_info_from_user_id(user_id)
        if raw:
            return user
        return self.profile_from_public_page(username=user["username"], user_id=user_id)

    @staticmethod
    def _parse_public_profile_count(value: str) -> int:
        value = value.replace(",", "")
        multiplier = 1000 if value.endswith("K") else 1000000 if value.endswith("M") else 1
        return int(float(value.rstrip("KM")) * multiplier)

    @staticmethod
    def _iter_json_objects(value):
        if isinstance(value, dict):
            yield value
            for inner_value in value.values():
                yield from Instagram._iter_json_objects(inner_value)
        elif isinstance(value, list):
            for inner_value in value:
                yield from Instagram._iter_json_objects(inner_value)

    @classmethod
    def _extract_ssr_profile_data(
        cls, parser: InstagramPublicPageHTMLParser, username: str
    ) -> Optional[Dict[str, Any]]:
        """Find the preloaded GraphQL profile object in a server-rendered page."""
        candidates = []
        for script in parser.json_scripts:
            try:
                data = json.loads(script)
            except json.JSONDecodeError:
                continue
            for value in cls._iter_json_objects(data):
                user = value.get("xig_user_by_username")
                if user and user.get("username") == username:
                    candidates.append(user)
        if not candidates:
            return None
        detail_fields = {"bio_links", "biography", "follower_count", "following_count", "is_verified"}
        return max(candidates, key=lambda user: len(detail_fields.intersection(user)))

    @classmethod
    def _extract_public_profile_from_html(cls, page: str, username: str, user_id: int) -> InstagramProfile:
        """Build a profile from SSR GraphQL data, falling back to public metadata."""
        parser = InstagramPublicPageHTMLParser()
        parser.feed(page)
        parser.close()
        ssr_user = cls._extract_ssr_profile_data(parser, username)
        metadata = parser.metadata
        description = metadata.get("og:description", "")
        title = metadata.get("og:title", username)
        counts = REGEXP_PROFILE_COUNTS.search(description)
        if ssr_user:
            raw_bio_links = ssr_user.get("bio_links") or []
            bio_links = [Link(title=link.get("title"), url=link["url"]) for link in raw_bio_links if link.get("url")]
            picture_url = ssr_user.get("profile_pic_url") or metadata.get("og:image")
            if picture_url is None:
                raise RuntimeError("Cannot get public profile picture URL from SSR profile data")
            return InstagramProfile(
                id=int(ssr_user.get("pk") or user_id),
                username=ssr_user["username"],
                full_name=ssr_user.get("full_name") or username,
                picture=Picture(url=picture_url),
                is_verified=ssr_user.get("is_verified"),
                followers=(
                    ssr_user.get("follower_count")
                    if ssr_user.get("follower_count") is not None
                    else cls._parse_public_profile_count(counts.group(1)) if counts else None
                ),
                followees=(
                    ssr_user.get("following_count")
                    if ssr_user.get("following_count") is not None
                    else cls._parse_public_profile_count(counts.group(2)) if counts else None
                ),
                posts=(
                    ssr_user.get("all_media_count")
                    if ssr_user.get("all_media_count") is not None
                    else (
                        ssr_user.get("media_count")
                        if ssr_user.get("media_count") is not None
                        else cls._parse_public_profile_count(counts.group(3)) if counts else None
                    )
                ),
                is_private=ssr_user.get("is_private"),
                biography=ssr_user.get("biography") or metadata.get("description"),
                bio_links=bio_links,
            )
        picture_url = metadata.get("og:image")
        if picture_url is None:
            raise RuntimeError("Cannot get public profile picture URL from profile page metadata")
        return InstagramProfile(
            id=int(user_id),
            username=username,
            full_name=title.split(" (@", 1)[0],
            picture=Picture(url=picture_url),
            followers=cls._parse_public_profile_count(counts.group(1)) if counts else None,
            followees=cls._parse_public_profile_count(counts.group(2)) if counts else None,
            posts=cls._parse_public_profile_count(counts.group(3)) if counts else None,
            biography=metadata.get("description"),
            bio_links=[],
        )

    def _fetch_public_profile_page(self, username: str) -> str:
        # Request this as a document navigation. Instagram may omit the SSR
        # GraphQL payload (including bio_links) for fetch/XHR-like headers.
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.5",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "origin": None,
        }
        response = self.request(method="GET", url=urljoin(self.main_url, username), headers=headers)
        return response.content.decode(response.apparent_encoding)

    def profile_from_public_page(self, username: str, user_id: Optional[int] = None) -> InstagramProfile:
        """Get public profile metadata without the versioned profile GraphQL query."""
        if user_id is None:
            user_id = self.user_id(username)
        profile = self._extract_public_profile_from_html(
            page=self._fetch_public_profile_page(username), username=username, user_id=user_id
        )
        self._user_id_cache[profile.username] = profile.id
        return profile

    def profile_from_username(self, username: str, raw: bool = False) -> Union[InstagramProfile, Dict[str, Any]]:
        if username in self._user_id_cache:
            user_id = self._user_id_cache[username]
        else:
            user_id = self.user_id(username)
        if raw:
            return self.profile_from_user_id(user_id=user_id, raw=True)
        # Username lookup already resolved the ID, so it can go straight to
        # the profile page and avoid an extra rate-limited user-info request.
        return self.profile_from_public_page(username=username, user_id=user_id)

    def profile(self, username_or_id: Union[str, int], raw: bool = False) -> Union[InstagramProfile, Dict[str, Any]]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            return self.profile_from_user_id(username_or_id, raw=raw)
        else:
            return self.profile_from_username(username_or_id, raw=raw)

    def _extract_media_from_xdt_timeline_node(self, node: Dict[str, Any]) -> List[Union[Picture, Video]]:
        result = []
        # Try to get the image with original size. If not found, get the biggest one
        images = list(node["image_versions2"]["candidates"])
        original_size = (node["original_width"], node["original_height"])
        selected_images = [image for image in images if (image["width"], image["height"]) == original_size]
        if selected_images:
            image = selected_images[0]
        else:
            images.sort(key=lambda obj: obj["width"], reverse=True)
            image = images[0]
        media_type_id = node.get("media_type")
        if media_type_id is None:
            # Carousel children from the media-ID query omit media_type.
            media_type = "video" if node.get("video_versions") else "photo"
        else:
            media_type = self.media_types_ids[media_type_id]
        if media_type == "carousel":
            media_type = "photo"
        image_media = Picture(
            url=image["url"],
            width=image["width"],
            height=image["height"],
        )
        if media_type == "video":
            video = node["video_versions"][0]
            media = Video(
                type=video.get("type"),
                url=video["url"],
                width=video.get("width", node.get("original_width")),
                height=video.get("height", node.get("original_height")),
                thumbnail=image_media,
            )
        else:
            media = image_media
        result.append(media)
        carousel = node.get("carousel_media") or []
        for inner_node in carousel:
            result.extend(self._extract_media_from_xdt_timeline_node(inner_node))
        # TODO: extract usertags (for each media)
        return result

    def _extract_post_from_xdt_timeline_node(self, node: Dict[str, Any]) -> InstagramPost:
        assert "taken_at" in node
        user = node["user"]
        node_pk = int(node["pk"])
        author_id = int(user.get("pk") or user["id"])
        node_id = node.get("id") or f"{node_pk}_{author_id}"
        timestamp = node["taken_at"]
        code = node["code"]
        if user.get("hd_profile_pic_url_info"):
            profile_picture_url = user["hd_profile_pic_url_info"]["url"]
        else:
            profile_picture_url = user["profile_pic_url"]
        author = InstagramProfile(
            id=author_id,
            username=user["username"],
            full_name=user.get("full_name") or user["username"],
            picture=Picture(url=profile_picture_url),
            is_verified=user.get("is_verified"),
            is_private=user.get("is_private"),
        )
        accessibility_caption = node.get("accessibility_caption")
        text = (node.get("caption") or {}).get("text")
        comments = node.get("comment_count")
        likes = node.get("like_count")
        pinned = len(node.get("timeline_pinned_user_ids") or []) > 0
        media_type = self.media_types_ids[node["media_type"]]
        raw_location = node.get("location") or {}
        location_pk = raw_location.get("pk") or raw_location.get("id")
        if not location_pk:
            location = None
        else:
            location = Location(
                id=int(location_pk),
                lat=raw_location["lat"],
                lng=raw_location["lng"],
                name=raw_location["name"],
            )
        published_at = datetime.datetime.fromtimestamp(timestamp).replace(tzinfo=datetime.timezone.utc)
        post_media = self._extract_media_from_xdt_timeline_node(node)
        thumbnail = None
        if media_type != "photo" and len(post_media) > 1 and isinstance(post_media[0], Picture):
            thumbnail = post_media.pop(0)
        elif media_type == "video" and post_media and isinstance(post_media[0], Video):
            thumbnail = post_media[0].thumbnail
        return InstagramPost(
            id=node_id,
            pk=node_pk,
            code=code,
            type=media_type,
            pinned=pinned,
            published_at=published_at,
            text=text,
            author=author,
            comments=comments,
            likes=likes,
            accessibility_caption=accessibility_caption,
            location=location,
            thumbnail=thumbnail,
            media=post_media,
        )

    def _extract_media_from_graphql_node(self, node: Dict[str, Any]) -> List[Union[Picture, Video]]:
        media_type = self.media_types_names[node["__typename"]]
        images = [
            Picture(url=img["src"], width=img["config_width"], height=img["config_height"])
            for img in node["display_resources"]
        ]
        images.sort(key=lambda pic: pic.width, reverse=True)

        if media_type == "photo":
            return [images[0]]

        elif media_type == "video":
            dimensions = node["dimensions"]
            return [
                Video(
                    url=node["video_url"],
                    width=dimensions["width"],
                    height=dimensions["height"],
                    thumbnail=images[0],
                    duration=node.get("video_duration"),
                )
            ]

        elif media_type == "carousel":
            result = [images[0]]
            for child in node["edge_sidecar_to_children"]["edges"]:
                result.extend(self._extract_media_from_graphql_node(child["node"]))
            return result

    def _extract_post_from_graphql_node(self, node: Dict[str, Any]) -> InstagramPost:
        assert "taken_at_timestamp" in node
        user = node["owner"]
        node_pk = int(node["id"])
        node_id = f"{node_pk}_{user['id']}"
        timestamp = node["taken_at_timestamp"]
        code = node["shortcode"]
        # The public timeline query returns a deliberately compact owner object. Keep the fields that it does provide
        # instead of requiring post-detail data.
        profile_picture_url = user.get("profile_pic_url") or node.get("display_url")
        if profile_picture_url is None:
            resources = node.get("display_resources") or []
            profile_picture_url = resources[0]["src"] if resources else None
        if profile_picture_url is None:
            raise RuntimeError(f"Public timeline post {code!r} has no author picture URL")
        author = InstagramProfile(
            id=int(user["id"]),
            username=user["username"],
            full_name=user.get("full_name") or user["username"],
            is_verified=user.get("is_verified"),
            followers=(user.get("edge_followed_by") or {}).get("count"),
            posts=(user.get("edge_owner_to_timeline_media") or {}).get("count"),
            is_private=user.get("is_private"),
            picture=Picture(url=profile_picture_url),
        )
        captions = node.get("edge_media_to_caption", {}).get("edges", [])
        text = captions[0]["node"]["text"] if captions else None
        accessibility_caption = node.get("accessibility_caption")
        comments = likes = pinned = None
        media_type = self.media_types_names[node["__typename"]]
        raw_location = node.get("location")
        if not raw_location:
            location = None
        else:
            address = json.loads(raw_location["address_json"]) if raw_location.get("address_json") else {}
            location = Location(
                id=int(raw_location["id"]),
                has_public_page=raw_location.get("has_public_page"),
                name=raw_location["name"],
                slug=raw_location.get("slug"),
                address=address.get("street_address"),
                zip_code=address.get("zip_code"),
                city=address.get("city_name"),
                country_code=address.get("country_code"),
            )
        published_at = datetime.datetime.fromtimestamp(timestamp).replace(tzinfo=datetime.timezone.utc)
        # TODO: may use `node["edge_media_to_tagged_user"]` to get tagged users

        post_media = self._extract_media_from_graphql_node(node)
        if media_type == "photo":
            views = plays = thumbnail = None
        elif media_type == "video":
            views = node.get("video_view_count")
            plays = node.get("video_play_count")
            thumbnail = Picture(url=node["thumbnail_src"])
        elif media_type == "carousel":
            views = plays = None
            thumbnail = post_media.pop(0)

        return InstagramPost(
            id=node_id,
            pk=node_pk,
            code=code,
            type=media_type,
            pinned=pinned,
            published_at=published_at,
            text=text,
            author=author,
            comments=comments,
            likes=likes,
            accessibility_caption=accessibility_caption,
            location=location,
            thumbnail=thumbnail,
            media=post_media,
            views=views,
            plays=plays,
        )

    def profile_posts_from_username(
        self, username: str, raw: bool = False
    ) -> Generator[Union[InstagramPost, Dict[str, Any]], None, None]:
        """Collect all posts from a user timeline

        Some attributes may be different according to post type:
        - "photo":
           - post.thumbnail is None
           - len(post.media) == 1
           - type(post.media[0]) is Picture
        - "video":
          - post.thumbnail is not None
          - type(post.thumbnail) is Picture
          - len(post.media) == 1
          - type(post.media[0]) is Video
        - "carousel":
          - post.thumbnail is not None
          - type(post.thumbnail) is Picture
          - len(post.media) > 1
          - type(post.media[n]) in (Picture, Video)
        """
        user_id = self.user_id(username)
        yield from self._profile_posts_from_public_user_id(user_id=user_id, raw=raw)

    def _profile_posts_from_public_user_id(
        self, user_id: int, raw: bool = False
    ) -> Generator[Union[InstagramPost, Dict[str, Any]], None, None]:
        """Collect the public timeline directly from the numeric user ID."""
        query = self.public_timeline_query
        cursor = None
        finished = False
        while not finished:
            variables = {
                "id": str(user_id),
                "include_clips_attribution_info": False,
                "first": query["page_size"],
            }
            if cursor is not None:
                variables["after"] = cursor
            response = self.request(
                method=query["method"],
                url=query["url"],
                headers=query["headers"],
                params={"doc_id": query["doc_id"], "variables": json.dumps(variables)},
            )
            response_data = response.json()
            data = response_data.get("data")
            if data is None:
                raise RuntimeError(f"Cannot get public profile posts for {user_id}: {response_data}")
            try:
                timeline = data["user"]["edge_owner_to_timeline_media"]
                page_info = timeline["page_info"]
            except KeyError as exc:
                raise RuntimeError(f"Unexpected public timeline response for {user_id}: {response_data}") from exc
            for edge in timeline["edges"]:
                if raw:
                    yield edge
                else:
                    post = self._extract_post_from_graphql_node(edge["node"])
                    self._user_id_cache[post.author.username] = post.author.id
                    yield post
            finished = not page_info["has_next_page"]
            cursor = page_info["end_cursor"]

    def profile_posts_from_user_id(
        self, user_id: int, raw: bool = False
    ) -> Generator[Union[InstagramPost, Dict[str, Any]], None, None]:
        yield from self._profile_posts_from_public_user_id(user_id=user_id, raw=raw)

    def profile_posts(
        self, username_or_id: Union[str, int], raw: bool = False
    ) -> Generator[Union[InstagramPost, Dict[str, Any]], None, None]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            yield from self.profile_posts_from_user_id(username_or_id)
        else:
            yield from self.profile_posts_from_username(username_or_id)

    @staticmethod
    def _media_id_from_code(code: str) -> int:
        """Decode Instagram's URL-safe base64 shortcode into its numeric media ID."""
        if not code:
            raise ValueError("Instagram post code cannot be empty")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        media_id = 0
        try:
            for character in code:
                media_id = media_id * 64 + alphabet.index(character)
        except ValueError as exc:
            raise ValueError(f"Invalid Instagram post code: {code!r}") from exc
        return media_id

    def post(self, code: str, raw: bool = False) -> InstagramPost:
        """Get a public post through the current media-ID GraphQL query."""
        query = self.public_post_query
        variables = {query["variable_name"]: str(self._media_id_from_code(code))}
        response = self.request(
            method=query["method"],
            url=query["url"],
            headers=query["headers"],
            params={"doc_id": query["doc_id"], "variables": json.dumps(variables)},
        )
        response_data = response.json()
        try:
            items = response_data["data"]["xdt_api__v1__media__media_id_web_info"]["items"]
            node = next(item for item in items if item["code"] == code)
        except (KeyError, StopIteration, TypeError) as exc:
            raise RuntimeError(f"Cannot get public post {code!r}: {response_data}") from exc
        if raw:
            return node
        post = self._extract_post_from_xdt_timeline_node(node)
        self._user_id_cache[post.author.username] = post.author.id
        return post
