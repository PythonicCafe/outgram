import datetime
import json
from typing import Any, Dict, Generator, Union

from .client import BaseClient
from .models import Link, Picture, ThreadsPost, ThreadsProfile, Video
from .utils import REGEXP_LSD


# TODO: add username <-> user ID cache, so we avoid unneeded requests and the user don't need to manage this
class Threads(BaseClient):
    main_url = "https://www.threads.net/"
    graphql_url = "https://www.threads.net/api/graphql"

    # TODO: implement authentication
    # TODO: list post comments (needs authentication)

    def __post_init__(self):
        response = self.request(method="GET", url=self.main_url)
        html = response.content.decode(response.apparent_encoding)
        self.session.headers["x-fb-lsd"] = REGEXP_LSD.findall(html)[0]
        self._user_id_cache = {}

    def _extract_profile(self, json_data: dict) -> ThreadsProfile:
        user = json_data["data"]["user"]
        pictures = []
        if "profile_pic_url" in user:
            pictures.append(Picture(url=user["profile_pic_url"], width=150, height=150))  # TODO: check hard-coded size
        pictures.extend(
            [
                Picture(url=pic["url"], width=pic["width"], height=pic["height"])
                for pic in user.get("hd_profile_pic_versions", [])
            ]
        )
        # TODO: bio_links not working?
        if "bio_links" in user:
            bio_links = [
                Link(url=link["url"], is_verified=link["is_verified"], id=int(link["link_id"]))
                for link in user.get("bio_links", [])
            ]
        else:
            bio_links = []
        return ThreadsProfile(
            id=int(user["id"]),
            username=user["username"],
            full_name=user["full_name"],
            biography=user["biography"],
            is_verified=user["is_verified"],
            followers=user["follower_count"],
            pictures=pictures,
            is_private=user["text_post_app_is_private"],
            bio_links=bio_links,
            is_threads_only_user=user.get("is_threads_only_user"),
        )

    def simple_profile(self, username: str, raw: bool = False) -> Union[ThreadsProfile, Dict[str, Any]]:
        """Get basic profile information. For complete info, use `.full_profile`"""
        query_name = "BarcelonaUsernameHoverCardImplQuery"
        headers = {
            "x-fb-friendly-name": query_name,
        }
        query_variables = {
            "username": username,
            "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": "false",
        }
        data = {
            "fb_api_req_friendly_name": query_name,
            "variables": json.dumps(query_variables),
            "lsd": self.session.headers["x-fb-lsd"],
            "doc_id": "7679337195500348",
        }
        response = self.request(method="POST", url=self.graphql_url, headers=headers, data=data)
        data = response.json()
        if raw:
            return data
        profile = self._extract_profile(data)
        self._user_id_cache[profile.username] = profile.id
        return profile

    def profile_from_user_id(self, user_id: int, raw: bool = False) -> Union[ThreadsProfile, Dict[str, Any]]:
        """Get full profile info for an user. If you only have the username, get the ID with `simple_profile()`"""
        query_name = "BarcelonaProfilePageQuery"
        headers = {
            "x-fb-friendly-name": query_name,
        }
        query_variables = {
            "userID": user_id,
            "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": "false",
            "__relay_internal__pv__BarcelonaIsPASTISWarningEnabledrelayprovider": "false",
            "__relay_internal__pv__BarcelonaIsSableEnabledrelayprovider": "false",
            "__relay_internal__pv__BarcelonaIsLinkVerificationEnabledrelayprovider": "false",
            "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": "false",
        }
        data = {
            "fb_api_req_friendly_name": query_name,
            "variables": json.dumps(query_variables),
            "lsd": self.session.headers["x-fb-lsd"],
            "doc_id": "8454848744553415",
        }
        response = self.request(method="POST", url=self.graphql_url, headers=headers, data=data)
        data = response.json()
        return self._extract_profile(data) if not raw else data  # `raw` is useful for debugging purposes

    def profile_from_username(self, username: str, raw: bool = False) -> Union[ThreadsProfile, Dict[str, Any]]:
        if username in self._user_id_cache:
            user_id = self._user_id_cache[username]
        else:
            simple_profile = self.simple_profile(username)
            user_id = simple_profile.id
        return self.profile_from_user_id(user_id=user_id, raw=raw)

    def profile(self, username_or_id: Union[str, int], raw: bool = False) -> Union[ThreadsProfile, Dict[str, Any]]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            return self.profile_from_user_id(username_or_id)
        else:
            return self.profile_from_username(username_or_id)

    def _extract_post(self, post_data: dict) -> ThreadsPost:
        if len(post_data.get("carousel_media") or []) > 0:
            inner_media = post_data["carousel_media"]
        else:
            inner_media = [post_data]
        post_media = []
        for obj in inner_media:
            obj_picture = None
            if "image_versions2" in obj and "candidates" in obj["image_versions2"]:
                images = [
                    Picture(pic["url"], pic["width"], pic["height"]) for pic in obj["image_versions2"]["candidates"]
                ]
                images.sort(key=lambda obj: obj.width, reverse=True)
                if images:
                    obj_picture = images[0]
            if len(obj.get("video_versions") or []) > 0:
                video = obj["video_versions"][0]
                video = Video(type=video["type"], url=video["url"])
                if obj_picture is not None:
                    video.thumbnail = obj_picture
                post_media.append(video)
            elif obj_picture is not None:
                post_media.append(obj_picture)

        text = ""
        links = []
        if "text_post_app_info" in post_data and "text_fragments" in post_data["text_post_app_info"]:
            for fragment in post_data["text_post_app_info"]["text_fragments"]["fragments"]:
                text += fragment["plaintext"]
                if fragment["fragment_type"] == "link" and fragment["link_fragment"]:
                    links.append(
                        Link(
                            url=fragment["link_fragment"]["uri"],
                            display_text=fragment["link_fragment"]["display_text"],
                        )
                    )
        user = post_data["user"]
        return ThreadsPost(
            id=post_data["id"],
            user_id=int(user["pk"]),
            username=user["username"],
            is_verified=user["is_verified"],
            text=text,
            links=links,
            published_at=datetime.datetime.fromtimestamp(post_data["taken_at"]).replace(tzinfo=datetime.timezone.utc),
            likes=post_data["like_count"],
            replies=post_data["text_post_app_info"].get("direct_reply_count", 0),
            reposts=post_data["text_post_app_info"].get("repost_count", 0),
            quotes=post_data["text_post_app_info"].get("quote_count", 0),
            is_private=user.get("text_post_app_is_private", False),
            media=post_media,
            reply_control=post_data["text_post_app_info"].get("reply_control"),
            media_type=post_data.get("media_type"),
            accessibility_caption=post_data.get("accessibility_caption"),
            is_paid_partnership=post_data.get("is_paid_partnership"),
            like_and_view_counts_disabled=post_data.get("like_and_view_counts_disabled"),
            has_audio=post_data.get("has_audio"),
            original_width=post_data.get("original_width"),
            original_height=post_data.get("original_height"),
            code=post_data.get("code"),
            reshares=post_data["text_post_app_info"].get("reshare_count"),
        )

    def profile_posts_from_user_id(
        self, user_id: int, raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        """
        Get last posts for user with ID `user_id`

        Call `profile(username)` or `full_profile(username)` to get `user_id` from a username
        """
        query_name = "BarcelonaProfileThreadsTabQuery"
        headers = {
            "x-fb-friendly-name": query_name,
        }
        query_variables = {
            "userID": user_id,
            "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": "false",
            "__relay_internal__pv__BarcelonaIsInlineReelsEnabledrelayprovider": "true",
            "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": "true",
            "__relay_internal__pv__BarcelonaShowReshareCountrelayprovider": "true",
            "__relay_internal__pv__BarcelonaQuotedPostUFIEnabledrelayprovider": "false",
            "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": "false",
            "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": "false",
        }
        data = {
            "fb_api_req_friendly_name": query_name,
            "variables": json.dumps(query_variables),
            "lsd": self.session.headers["x-fb-lsd"],
            "doc_id": "27224795300468294",
        }
        response = self.request(method="POST", url=self.graphql_url, headers=headers, data=data)
        data = response.json()
        for post_data in data["data"]["mediaData"]["edges"]:
            raw_post = post_data["node"]["thread_items"][0]["post"]
            if raw:
                yield raw_post
            else:
                post = self._extract_post(raw_post)
                self._user_id_cache[post.username] = post.user_id
                yield post
        # TODO: if logged in, get `end_cursor` inside `page_info` and paginate

    def profile_posts_from_username(
        self, username: str, raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        if username in self._user_id_cache:
            user_id = self._user_id_cache[username]
        else:
            simple_profile = self.simple_profile(username)
            user_id = simple_profile.id
        yield from self.profile_posts_from_user_id(user_id=user_id, raw=raw)

    def profile_posts(
        self, username_or_id: Union[str, int], raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            yield from self.profile_posts_from_user_id(username_or_id)
        else:
            yield from self.profile_posts_from_username(username_or_id)
