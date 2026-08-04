# Maintaining the Instagram public scraper

Instagram changes its public Web client frequently. Persisted GraphQL query IDs (`doc_id`), endpoints, request variables and response schemas are implementation details, not a stable API. When `outgram` stops working, capture one public browser session, compare it with the client and make the smallest compatible change.

This guide is for public profiles and content that you are authorized to archive. Do not use it to bypass private-profile access, login challenges, rate limits or other access controls.

## Current implementation map

| Capability | Implementation | Public source to inspect when it fails |
| --- | --- | --- |
| Resolve numeric user ID | `Instagram._user_info_from_user_id` | `GET /api/v1/users/<id>/info/` |
| Profile by username or ID | `profile_from_username`, `profile_from_user_id`, `profile_from_public_page` | profile HTML metadata and the user-info endpoint |
| Profile HTML fallback | `InstagramPublicPageHTMLParser`, `_extract_ssr_profile_data`, `_extract_public_profile_from_html` | SSR `xig_user_by_username` GraphQL payload, then `<meta>` tags |
| Public timeline | `_profile_posts_from_public_user_id` | `Instagram.public_timeline_query` and `data.user.edge_owner_to_timeline_media` |
| Individual post | `post`, `_media_id_from_code` | `Instagram.public_post_query` and `xdt_api__v1__media__media_id_web_info.items` |
| Compact timeline node parsing | `_extract_post_from_graphql_node` | `GraphImage`, `GraphVideo`, `GraphSidecar` nodes |
| Detailed media-ID node parsing | `_extract_post_from_xdt_timeline_node` | `XDTMediaDict` and `carousel_media` nodes |
| Media download | `BaseClient.download` / `download_many` | CDN response status, MIME type and bytes |
| Public object URLs | `InstagramProfile.url`, `InstagramPost.url` | canonical profile, `/p/<code>/` and `/reel/<code>/` URLs |

Keep request-specific values together in class-level dictionaries. The current public queries are intentionally centralized in:

```python
Instagram.public_timeline_query
Instagram.public_post_query
```

Do not scatter a replacement `doc_id` across methods.

## Symptoms and likely causes

| Symptom | Typical cause | First check |
| --- | --- | --- |
| `The GraphQL document with ID ... was not found` | A persisted query was retired. | HAR request URL/form fields and loaded JavaScript bundle operation IDs. |
| Post lookup returns empty data or `None` | The shortcode query or response path changed. | Shortcode-to-media-ID conversion, `public_post_query`, `items` response path. |
| Numeric profile ID fails but username works | User-info endpoint changed or the ID resolver was bypassed. | `GET /api/v1/users/<id>/info/` and `profile_from_user_id`. |
| `429` | The server is rate-limiting the session/IP. | Stop requests; use a longer wait or retry later. |
| `401`, `403`, challenge or login wall | The endpoint/content is unavailable to the anonymous client. | Do not attempt to bypass it. |
| `KeyError`, missing media or wrong media type | Response schema changed or compact nodes omit a field. | Photo, video and carousel fixtures plus HAR response schema. |
| Archive ends early without an error | A response is malformed/blocked and code is swallowing it. | Ensure the collector raises a descriptive error; do not silently return. |
| Media download fails | Expired CDN URL, unsupported MIME type or unavailable rendition. | Re-run collection, inspect status/MIME type and validate downloaded bytes. |

## Capture a small and reproducible HAR

Use a disposable browser profile and a normal logged-out session.

1. Open one **public** profile.
2. Start network recording, reload it and scroll enough to load a second timeline page.
3. Open one public photo, one Reel/video and one carousel in their individual routes.
4. Export a HAR with request payloads and response bodies if the browser supports it.
5. Capture a separate HAR for each failure instead of recording unrelated browsing activity.
6. Inspect the complete HAR locally when diagnosing the browser protocol. Read cookies, CSRF/LSD values, device identifiers, temporary CDN URLs, request forms and headers when needed to compare the browser with a newly created client session and derive dynamic bootstrap rules. Do not commit the HAR, attach it to issues, paste transient values into logs or fixtures, hard-code them or replay them from the HAR. Derive equivalent values from each new client session instead.

### Lightpanda CDP capture

The repository includes a stdlib-only Lightpanda installer and CDP recorder:

```shell
python scripts/install_lightpanda.py
python scripts/capture_instagram_lightpanda.py \
  target_username another_public_username \
  --scrolls 2 \
  --output data/instagram.har
```

The recorder starts `lightpanda serve`, connects through CDP, records `Network.*` events and writes HAR 1.2 JSON. It captures response bodies where exposed by Lightpanda and is useful for GET query strings, response schemas and resource URLs.

The currently tested Lightpanda CDP build does not expose POST request bodies. Use a full browser HAR when the required operation data exists only in a POST form body. Cookie, `Set-Cookie` and `Authorization` headers are removed by default; `--keep-cookies` is for local diagnostics only and those HARs must never be shared.

See [`lightpanda-capture.md`](lightpanda-capture.md) for installation and capture details.

## Produce a safe request summary

The local analyzer intentionally omits cookies, authorization headers and response bodies:

```shell
python scripts/analyze_har.py profile.har --profile target_username
python scripts/analyze_har.py profile.har --profile target_username --json > har-summary.json
```

For every successful relevant request, record only:

- HTTP method and endpoint;
- `doc_id` and `fb_api_req_friendly_name`, if present;
- variables shape and cursor fields;
- top-level response path to the wanted object;
- node type names and fields for photo, video and carousel;
- whether request headers such as `X-IG-App-ID`, LSD or friendly-name are actually required.

Delete raw HARs and summaries when no longer needed. Never copy browser cookies, CSRF/LSD values or temporary media URLs into fixtures, source code, tests, commits or documentation.

## Change checklist by capability

### Profile data: SSR GraphQL first, metadata last

The public profile page can contain an SSR GraphQL result inside an `application/json` script:

```text
RelayPrefetchedStreamCache → xig_user_by_username
```

When present, it is the primary structured source for:

```text
id, username, full_name, profile picture, biography, verification, privacy,
follower/following counts, post count and bio_links
```

`InstagramPublicPageHTMLParser` collects those JSON scripts with `HTMLParser`; `_extract_ssr_profile_data` finds `xig_user_by_username`; `_extract_public_profile_from_html` maps it into `InstagramProfile` and `Link` objects.

`_fetch_public_profile_page` must send document-navigation headers (`Accept: text/html`, `Sec-Fetch-Dest: document`, `Sec-Fetch-Mode: navigate`, `Sec-Fetch-User: ?1` and a current browser user agent). Instagram can omit the SSR GraphQL payload, including `bio_links`, when the same URL is requested with fetch/XHR-like headers.

Some anonymous responses do not include that SSR payload. Only in that case use semantic metadata as the final fallback. Verify both attribute orders:

```html
<meta property="og:title" content="...">
<meta content="..." name="description">
```

Metadata fallback reliably provides only:

```text
id, username, full_name, picture URL, followers, followees, posts, biography
```

It must return `bio_links=[]` when SSR data is absent. Do not invent verification, privacy state, detailed links or an HD picture from metadata alone.

### Numeric user IDs

Validate both forms of every feature:

```text
username → user ID → public timeline
numeric ID → user-info endpoint → profile/public timeline
```

A public timeline query already accepts a numeric ID; do not first resolve it through a profile GraphQL document that may have expired.

### Public timeline

Check all of the following against the HAR:

- `Instagram.public_timeline_query` method, URL, headers and `doc_id`;
- first-page variables;
- `after` cursor for later pages;
- `data.user.edge_owner_to_timeline_media` path;
- `page_info.has_next_page` and `page_info.end_cursor`;
- `GraphImage`, `GraphVideo` and `GraphSidecar` media nodes;
- compact `owner` objects and absent optional fields.

A failed or unexpected response must raise an error. It must not produce a partial archive silently.

### Individual post

The current post query receives a numeric media ID, not a shortcode. `Instagram._media_id_from_code` decodes Instagram's URL-safe base64 shortcode before using `Instagram.public_post_query`.

Validate:

- shortcode decoding for at least two known codes;
- post-query method, endpoint, `doc_id` and variable name;
- `data.xdt_api__v1__media__media_id_web_info.items` response path;
- the returned item has the requested `code`;
- photo, video and carousel parsing;
- carousel children without `media_type`;
- video rendition dimensions and thumbnails;
- likes, comments, caption, author and location where supplied.

### Media and canonical URLs

Check that:

- photos, video thumbnails, videos and all carousel children have HTTPS URLs;
- downloaded bytes are non-empty and MIME type matches the media class;
- profile URLs use `profile.username`;
- photo/carousel URLs use `/p/<code>/`;
- video URLs use `/reel/<code>/`.

## Automated tests

### Sanitized unit fixtures

Unit fixtures live in `tests/fixtures/` and contain no real account data, cookies, CDN URLs or HAR payloads:

```text
tests/fixtures/instagram_public_profile.html
tests/fixtures/instagram_media_nodes.json
```

They cover:

- metadata attributes in either order and HTML entities;
- profile count parsing;
- shortcode-to-media-ID decoding;
- compact public timeline video nodes;
- media-ID carousel nodes whose children omit `media_type`;
- numeric-ID resolver request shape;
- timeline query request/response path;
- profile and post URL properties.

Run them without network access:

```shell
pytest -q tests/test_instagram_unit.py
```

When schema changes, add the smallest sanitized fragment that reproduces the new shape. Never add a raw HAR or a real temporary media URL.

### Opt-in live smoke tests

Live smoke tests use known public profiles and are intentionally disabled by default:

```shell
OUTGRAM_RUN_SMOKE=1 pytest -m instagram_smoke
```

They validate actual content, not only absence of exceptions:

- profile lookup by username and a cached numeric ID returns matching stable fields;
- uncached numeric-ID lookup is attempted separately and is skipped only when Instagram rate-limits the public user-info endpoint;
- timeline lookup by username and numeric ID returns 13 valid posts, forcing a second page;
- every collected post has code, author, timezone-aware publication time, supported type and HTTPS media URLs;
- individual known photo, Reel and carousel posts have expected author/type/media shape;
- stable fields of known timeline and detailed posts agree;
- an image download has bytes and an `image/*` MIME type;
- a one-post archive has CSV metadata and profile/post media files.

The smoke tests currently use `raficomedy` and `govbr`. They are network-dependent and may need fixture/profile updates if the posts are deleted, made private or substantially edited. The older live integration module, `tests/test_instagram.py`, is also marked `instagram_smoke` and requires the same environment variable, so normal test runs remain offline.

## Manual visual validation checklist

Before accepting a maintenance change, compare the output with a logged-out browser view and record the date/profile/post URLs used.

### Profile

- username and display name;
- follower/following/post counts, allowing formatting differences such as `11K` versus `11000`;
- public bio text and profile image;
- whether the account is public.

### Individual posts

For one photo, one Reel and one carousel:

- shortcode and canonical URL;
- author username;
- caption text;
- publication date;
- media type;
- number and ordering of carousel items;
- visible thumbnail/video and whether downloaded media opens;
- visible likes/comments only when those fields are expected from the selected endpoint.

### Timeline/archive

- first-page ordering and a post from the second page;
- no duplicate shortcodes across pages;
- a shared/collaboration post if the profile has one;
- `profile.csv` and `post.csv` have populated stable fields;
- downloaded file count matches the post media model;
- available disk space is sufficient before a large video-heavy archive.

## Implementation rules

- Keep query settings as named configuration dictionaries, with comments that they are observed public-web values and may expire.
- Send only headers shown to be required for a public request. Do not reproduce an entire browser fingerprint or HAR form payload.
- Use `.get()` only for genuinely optional fields; raise a descriptive error for required schema paths.
- Prefer separate parsers for genuinely different schemas rather than forcing one schema into another.
- Preserve `raw=True` semantics and pass it through public wrapper methods.
- Stop on `429` and access-control responses; do not add authentication, cookie import, challenge solving, proxy rotation or rate-limit evasion as a workaround.
- State the observed failure, HAR date, endpoint/query update, test commands and result in the pull request or changelog.
