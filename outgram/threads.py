import datetime
import json
import re
import uuid
from html.parser import HTMLParser
from typing import Any, Dict, Generator, List, Union

from .client import BaseClient
from .models import Link, Picture, ThreadsPost, ThreadsProfile, Video

REGEXP_APP_ID = re.compile(r'"APP_ID":"([^"]+)"')
REGEXP_CANONICAL_ROUTE = re.compile(r'"canonicalRouteName":"([^"]+)"')
REGEXP_LSD = re.compile(r'\["LSD",\[\],\{"token":"([^"]+)"')
REGEXP_SITE_DATA = re.compile(r'\["SiteData",\[\],(\{.*?\}),\d+\]')
REGEXP_SECURITY_CONFIG = re.compile(r'\["InstagramSecurityConfig",\[\],(\{.*?\}),\d+\]')
REGEXP_BLOKS_VERSION = re.compile(r'\["WebBloksVersioningID",\[\],(\{.*?\}),\d+\]')


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
    graphql_url = main_url + "graphql/query"

    # Observed in the logged-out public Web client. Persisted query IDs and
    # feature variables can expire; keep request-specific settings together.
    public_timeline_refetch_query = {
        "doc_id": "28185048804453360",
        "operation": "BarcelonaProfileThreadsTabRefetchableDirectQuery",
        "root_field_name": "xdt_api__v1__text_feed__user_id__profile__connection",
        "asbd_id": "359341",
        "variables": {
            "allow_page_info_for_lox_user": True,
            "before": None,
            "first": 11,
            "last": None,
            "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasProfileSelfReplyContextrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasDearAlgoConsumptionrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider": False,
            "__relay_internal__pv__BarcelonaGenAIRepliesEnabledrelayprovider": False,
            "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasGameScoreSharerelayprovider": True,
            "__relay_internal__pv__BarcelonaHasPublicViewCountCardrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasCommunityEntityCardrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasScorecardCommunityrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasSportTeamAllegianceCardrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasMusicrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasNewspaperLinkStylerelayprovider": False,
            "__relay_internal__pv__BarcelonaHasMessagingrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasPodcastV2Consumptionrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasPodcastTranscriptConsumptionrelayprovider": False,
            "__relay_internal__pv__BarcelonaShouldFulfillLightboxQueryrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasViewerRepliedrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasPrivateRepliesDeprecationrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasGhostPostEmojiActivationrelayprovider": False,
            "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
            "__relay_internal__pv__BarcelonaHasDearAlgoWebProductionrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasWebFaviconsrelayprovider": False,
            "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": False,
            "__relay_internal__pv__BarcelonaHasCommunityTopContributorsrelayprovider": False,
            "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider": False,
            "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": False,
            "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider": False,
        },
    }

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

    def _public_page_html(self, username: str) -> str:
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
        return response.text

    def _ssr_results(self, html: str, username: str) -> List[Dict[str, Any]]:
        parser = ThreadsPublicPageHTMLParser()
        parser.feed(html)
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

    def _public_page_results(self, username: str) -> List[Dict[str, Any]]:
        return self._ssr_results(self._public_page_html(username), username)

    @staticmethod
    def _bootstrap_match(pattern: re.Pattern, html: str, name: str) -> str:
        match = pattern.search(html)
        if not match:
            raise RuntimeError(
                f"Public Threads profile response had no {name} bootstrap value"
            )
        return match.group(1)

    def _timeline_refetch_bootstrap(self, html: str) -> Dict[str, Any]:
        site_data = json.loads(
            self._bootstrap_match(REGEXP_SITE_DATA, html, "SiteData")
        )
        security = json.loads(
            self._bootstrap_match(REGEXP_SECURITY_CONFIG, html, "security")
        )
        bloks = json.loads(
            self._bootstrap_match(REGEXP_BLOKS_VERSION, html, "Bloks version")
        )
        lsd = self._bootstrap_match(REGEXP_LSD, html, "LSD")
        return {
            "app_id": self._bootstrap_match(REGEXP_APP_ID, html, "application ID"),
            "bloks_version": bloks["versioningID"],
            "csrf_token": security["csrf_token"],
            "lsd": lsd,
            "route": self._bootstrap_match(
                REGEXP_CANONICAL_ROUTE, html, "canonical route"
            ),
            "site_data": site_data,
        }

    @staticmethod
    def _web_session_id() -> str:
        value = uuid.uuid4().hex
        return f"{value[:6]}:{value[6:12]}:{value[12:18]}"

    def _timeline_refetch(
        self, html: str, username: str, user_id: int, cursor: str
    ) -> Dict[str, Any]:
        query = self.public_timeline_refetch_query
        bootstrap = self._timeline_refetch_bootstrap(html)
        site_data = bootstrap["site_data"]
        web_session_id = self._web_session_id()
        variables = dict(query["variables"])
        variables.update({"after": cursor, "userID": str(user_id)})
        lsd = bootstrap["lsd"]
        data = {
            "av": "0",
            "__user": "0",
            "__a": "1",
            "__req": "1",
            "__hs": site_data["haste_session"],
            "dpr": str(site_data["pr"]),
            "__ccg": "EXCELLENT",
            "__rev": str(site_data["__spin_r"]),
            "__s": web_session_id,
            "__hsi": site_data["hsi"],
            "__dyn": "",
            "__csr": "",
            "__hsdp": "",
            "__hblp": "",
            "__sjsp": "",
            "__comet_req": str(site_data["comet_env"]),
            "lsd": lsd,
            "jazoest": "2" + str(sum(ord(char) for char in lsd)),
            "__spin_r": str(site_data["__spin_r"]),
            "__spin_b": site_data["__spin_b"],
            "__spin_t": str(site_data["__spin_t"]),
            "__crn": bootstrap["route"],
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": query["operation"],
            "server_timestamps": "true",
            "variables": json.dumps(variables),
            "doc_id": query["doc_id"],
        }
        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "referer": f"{self.main_url}@{username}",
            "x-asbd-id": query["asbd_id"],
            "x-bloks-version-id": bootstrap["bloks_version"],
            "x-csrftoken": bootstrap["csrf_token"],
            "x-fb-friendly-name": query["operation"],
            "x-fb-lsd": lsd,
            "x-ig-app-id": bootstrap["app_id"],
            "x-logged-out-threads-migrated-request": "true",
            "x-root-field-name": query["root_field_name"],
            "x-web-session-id": web_session_id,
        }
        response = self.request(
            method="POST", url=self.graphql_url, headers=headers, data=data
        )
        if response.status_code in (401, 403, 429):
            raise RuntimeError(
                f"Public Threads collection was blocked for {query['operation']} (HTTP {response.status_code}); try again later"
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Public Threads request failed for {query['operation']} (HTTP {response.status_code})"
            )
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(
                f"Public Threads response was invalid JSON for {query['operation']}"
            )
        if not isinstance(result, dict) or not isinstance(result.get("data"), dict):
            raise RuntimeError(
                f"Public Threads response had unexpected shape for {query['operation']}"
            )
        return result

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
        html = self._public_page_html(username)
        results = self._ssr_results(html, username)
        timeline = self._timeline(self._result_with("mediaData", results))
        profile = self._result_with("user", results)["data"]["user"]
        user_id = int(profile["id"])
        while True:
            for edge in timeline["edges"]:
                node = edge.get("node") if isinstance(edge, dict) else None
                items = node.get("thread_items") if isinstance(node, dict) else None
                post_data = (
                    items[0].get("post")
                    if items and isinstance(items[0], dict)
                    else None
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
            cursor = page_info.get("end_cursor")
            if not page_info.get("has_next_page") or not cursor:
                return
            timeline = self._timeline(
                self._timeline_refetch(html, username, user_id, cursor)
            )

    def profile_posts(
        self, username_or_id: Union[str, int], raw: bool = False
    ) -> Generator[Union[ThreadsPost, Dict[str, Any]], None, None]:
        if isinstance(username_or_id, int) or username_or_id.isdigit():
            yield from self.profile_posts_from_user_id(username_or_id, raw=raw)
        else:
            yield from self.profile_posts_from_username(username_or_id, raw=raw)
