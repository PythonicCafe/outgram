import datetime
import json
import re
from typing import Any, Dict, Generator, List, Union
from urllib.parse import urljoin

from .client import BaseClient
from .models import InstagramPost, InstagramProfile, Link, Location, Picture, Video
from .utils import REGEXP_LSD

REGEXP_INSTAGRAM_APP_ID = re.compile(r'"X-IG-App-ID"\s*:\s*"([^"]+)"')
REGEXP_INSTAGRAM_CSRF_TOKEN = re.compile(r'"csrf_token"\s*:\s*"([^"]+)"')
REGEXP_INSTAGRAM_PROFILE_ID = re.compile(r'"page_id"\s*:\s*"profilePage_([^"]+)"')
REGEXP_DID = re.compile("([0-9A-Z]+-[0-9A-Z]+-[0-9A-Z]+-[0-9A-Z]+-[0-9A-Z]+)")


# TODO: add username <-> user ID cache, so we avoid unneeded requests and the user don't need to manage this
class Instagram(BaseClient):
    main_url = "https://www.instagram.com/"
    graphql_url = "https://www.instagram.com/graphql/query"
    media_types_ids = {1: "photo", 2: "video", 8: "carousel"}
    media_types_names = {"XDTGraphVideo": "video", "XDTGraphSidecar": "carousel", "XDTGraphImage": "photo"}

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
                "x-asbd-id": "129477",
                "x-ig-www-claim": "0",
            }
        )

    def user_id(self, username: str) -> int:
        response = self.request(method="GET", url=urljoin(self.main_url, username))
        html = response.content.decode(response.apparent_encoding)
        return int(REGEXP_INSTAGRAM_PROFILE_ID.findall(html)[0])

    def _extract_profile(self, data):
        raw_bio_links = data.pop("bio_links", [])
        bio_links = [Link(title=link["title"], url=link["url"]) for link in raw_bio_links]
        profile_picture = Picture(url=data.pop("hd_profile_pic_url_info")["url"])
        return InstagramProfile(
            id=int(data.pop("id")),
            username=data.pop("username"),
            full_name=data.pop("full_name"),
            biography=data.pop("biography"),
            is_verified=data.pop("is_verified"),
            followers=data.pop("follower_count"),
            is_private=data.pop("is_private"),
            picture=profile_picture,
            bio_links=bio_links,
            followees=data.pop("following_count"),
            posts=data.pop("media_count"),
        )

    def profile_from_user_id(self, user_id: int, raw: bool = False) -> Union[InstagramProfile, Dict[str, Any]]:
        query_name = "PolarisProfilePageContentQuery"
        headers = {"x-fb-friendly-name": query_name}
        variables = {
            "id": str(user_id),
            "render_surface": "PROFILE",
        }
        data = {
            "lsd": self.lsd,
            "fb_api_req_friendly_name": query_name,
            "variables": json.dumps(variables),
            "doc_id": "9013883645373700",
        }
        response = self.request(method="POST", url=self.graphql_url, headers=headers, data=data)
        data = response.json()
        if "data" not in data:
            raise RuntimeError(f"Cannot get user profile: {data}")
        user = data["data"]["user"]
        if raw:
            return user
        profile = self._extract_profile(user)
        self._user_id_cache[profile.username] = profile.id
        return profile

    def profile_from_username(self, username: str, raw: bool = False) -> Union[InstagramProfile, Dict[str, Any]]:
        if username in self._user_id_cache:
            user_id = self._user_id_cache[username]
        else:
            user_id = self.user_id(username)
        return self.profile_from_user_id(user_id=user_id, raw=raw)

    def profile(self, username_or_id: Union[str, int], raw: bool = False) -> Union[InstagramProfile, Dict[str, Any]]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            return self.profile_from_user_id(username_or_id)
        else:
            return self.profile_from_username(username_or_id)

    def _extract_media(self, node: Dict[str, Any]) -> List[Union[Picture, Video]]:
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
        media_type = self.media_types_ids[node["media_type"]]
        if media_type == "carousel":
            media_type = "photo"
        image_media = Picture(
            url=image["url"],
            width=image["width"],
            height=image["height"],
        )
        if media_type == "video":
            video = node["video_versions"][0] if media_type == "video" else {}
            media = Video(
                type=video["type"],
                url=video["url"],
                width=video["width"],
                height=video["height"],
                thumbnail=image_media,
            )
        else:
            media = image_media
        result.append(media)
        carousel = node.get("carousel_media") or []
        for inner_node in carousel:
            result.extend(self._extract_media(inner_node))
        # TODO: extract usertags (for each media)
        return result

    def _extract_post_from_posts(self, node: Dict[str, Any]) -> InstagramPost:
        assert "taken_at" in node
        user = node["user"]
        node_pk = int(node["pk"])
        node_id = node["id"]
        timestamp = node["taken_at"]
        code = node["code"]
        if "hd_profile_pic_url_info" in user and user["hd_profile_pic_url_info"]:
            profile_picture_url = user["hd_profile_pic_url_info"]["url"]
        else:
            profile_picture_url = user["profile_pic_url"]
        author = InstagramProfile(
            id=int(user["pk"]),
            username=user["username"],
            full_name=user["full_name"],
            picture=Picture(url=profile_picture_url),
        )
        accessibility_caption = node["accessibility_caption"]
        text = (node["caption"] or {}).get("text")
        comments = node["comment_count"]
        likes = node["like_count"]
        pinned = len(node["timeline_pinned_user_ids"]) > 0
        media_type = self.media_types_ids[node["media_type"]]
        raw_location = node["location"] or {}
        location_pk = raw_location.get("pk")
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
        post_media = self._extract_media(node)
        thumbnail = None
        if media_type != "photo" and len(post_media) > 1 and isinstance(post_media[0], Picture):
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
        )

    def _extract_post_media(self, node: Dict[str, Any]) -> List[Union[Picture, Video]]:
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
                    duration=node["video_duration"],
                )
            ]

        elif media_type == "carousel":
            result = [images[0]]
            for child in node["edge_sidecar_to_children"]["edges"]:
                result.extend(self._extract_post_media(child["node"]))
            return result

    def _extract_post_from_post(self, node: Dict[str, Any]) -> InstagramPost:
        assert "taken_at_timestamp" in node
        user = node["owner"]
        node_pk = int(node["id"])
        node_id = f"{node_pk}_{user['id']}"
        timestamp = node["taken_at_timestamp"]
        code = node["shortcode"]
        author = InstagramProfile(
            id=int(user["id"]),
            username=user["username"],
            full_name=user["full_name"],
            is_verified=user["is_verified"],
            followers=user["edge_followed_by"]["count"],
            posts=user["edge_owner_to_timeline_media"]["count"],
            is_private=user["is_private"],
            picture=Picture(url=user["profile_pic_url"]),
        )
        text = node["edge_media_to_caption"]["edges"][0]["node"]["text"]
        accessibility_caption = node["accessibility_caption"]
        comments = likes = pinned = None
        media_type = self.media_types_names[node["__typename"]]
        raw_location = node["location"]
        if not raw_location:
            location = None
        else:
            json_address = raw_location["address_json"]
            address = json.loads(json_address)
            location = Location(
                id=int(raw_location["id"]),
                has_public_page=raw_location["has_public_page"],
                name=raw_location["name"],
                slug=raw_location["slug"],
                address=address["street_address"],
                zip_code=address["zip_code"],
                city=address["city_name"],
                country_code=address["country_code"],
            )
        published_at = datetime.datetime.fromtimestamp(timestamp).replace(tzinfo=datetime.timezone.utc)
        # TODO: may use `node["edge_media_to_tagged_user"]` to get tagged users

        post_media = self._extract_post_media(node)
        if media_type == "photo":
            views = plays = thumbnail = None
        elif media_type == "video":
            views = node["video_view_count"]
            plays = node["video_play_count"]
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
        # TODO: check if this method gets the pinned posts
        query_name = "PolarisProfilePostsTabContentQuery_connection"
        headers = {"x-fb-friendly-name": query_name, "x-requested-with": "XMLHttpRequest"}
        cursor = None
        page_size = 12
        finished = False
        while not finished:
            variables = {
                "after": cursor,
                "before": None,
                "data": {
                    "count": page_size,
                    "include_reel_media_seen_timestamp": "true",
                    "include_relationship_info": "true",
                    "latest_besties_reel_media": "true",
                    "latest_reel_media": "true",
                },
                "first": page_size,
                "last": None,
                "username": username,
                "__relay_internal__pv__PolarisIsLoggedInrelayprovider": "true",
            }
            data = {
                "lsd": self.lsd,
                "fb_api_req_friendly_name": query_name,
                "variables": json.dumps(variables),
                "doc_id": "28967623359495231",
            }
            response = self.request(method="POST", url=self.graphql_url, headers=headers, data=data)
            response_data = response.json()
            data = response_data["data"]
            if data is None:
                return
            timeline = data["xdt_api__v1__feed__user_timeline_graphql_connection"]
            page_info = timeline["page_info"]
            edges = timeline["edges"]
            for edge in edges:
                if raw:
                    yield edge
                else:
                    post = self._extract_post_from_posts(edge["node"])
                    self._user_id_cache[post.author.username] = post.author.id
                    yield post
            finished = not page_info["has_next_page"]
            cursor = page_info["end_cursor"]

    def profile_posts_from_user_id(
        self, user_id: int, raw: bool = False
    ) -> Generator[Union[InstagramPost, Dict[str, Any]], None, None]:
        if user_id in self._user_id_cache.values():
            inverted = {value: key for key, value in self._user_id_cache.items()}
            username = inverted[user_id]
        else:
            profile = self.profile_from_user_id(user_id=user_id)
            username = profile.username
        yield from self.profile_posts_from_username(username=username, raw=raw)

    def profile_posts(
        self, username_or_id: Union[str, int], raw: bool = False
    ) -> Generator[Union[InstagramPost, Dict[str, Any]], None, None]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            yield from self.profile_posts_from_user_id(username_or_id)
        else:
            yield from self.profile_posts_from_username(username_or_id)

    def post(self, code: str, raw: bool = False) -> InstagramPost:
        query_name = "PolarisPostActionLoadPostQueryQuery"
        headers = {"x-fb-friendly-name": query_name}
        variables = {
            "shortcode": code,
            "fetch_tagged_user_count": None,
            "hoisted_comment_id": None,
            "hoisted_reply_id": None,
        }
        data = {
            "lsd": self.lsd,
            "fb_api_req_friendly_name": query_name,
            "fb_api_caller_class": "RelayModern",
            "variables": json.dumps(variables),
            "doc_id": "8845758582119845",
        }
        response = self.request(method="POST", url=self.graphql_url, headers=headers, data=data)
        data = response.json()
        node = data["data"]["xdt_shortcode_media"]
        if raw:
            return node
        post = self._extract_post_from_post(node)
        self._user_id_cache[post.author.username] = post.author.id
        return post
