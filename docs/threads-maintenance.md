# Maintaining the Threads public scraper

Threads public Web responses are implementation details, not a stable API. This guide covers only logged-out public profiles. Do not use it to bypass private access, login walls, challenges or rate limits.

## Current implementation map

| Capability | Implementation |
| --- | --- |
| Profile by username | `Threads.simple_profile` and `profile_from_username` |
| Public timeline and cursor pagination by username | `Threads.profile_posts_from_username` and `_timeline_refetch` |
| SSR parser and request bootstrap | `ThreadsPublicPageHTMLParser`, `_relay_results` and `_timeline_refetch_bootstrap` |
| Profile and post parsing | `_extract_profile` and `_extract_post` |

The client navigates to `https://www.threads.com/@<username>` with document-navigation headers. The logged-out HTML can contain `RelayPrefetchedStreamCache` records whose `result.data.user` and `result.data.mediaData` provide the profile and initial timeline page.

The first timeline page comes from SSR. When it exposes `page_info.has_next_page` and `end_cursor`, the client derives the public GraphQL refetch bootstrap from that same HTML document and follows the cursor. It obtains LSD, CSRF, Bloks version, app ID, route, revisions and session cookies from its own new public response; it creates its own web-session ID and does not import HAR values.

Numeric-ID lookup is not currently supported. It has no public page route from which the client can derive the necessary profile bootstrap, so that path must raise a contextual error rather than replaying captured browser values.

## Capture and inspect a small HAR

Use a disposable, logged-out browser profile. Capture one public profile, load one additional timeline page, then stop recording. HAR files can contain cookies, CSRF/LSD values, session or device identifiers and temporary media URLs.

Inspect the complete HAR locally when diagnosing a failure. Read the actual values of cookies, CSRF/LSD tokens, device and web-session identifiers, request forms, headers and temporary URLs when they are needed to compare the browser with a newly created public session. This is expected diagnostic work, including for a logged-out anonymous browser, and it is how to determine which browser values are static, session-derived or unnecessary.

The restriction is persistence and disclosure, not local inspection: do not commit the HAR, paste transient values into chat, logs or issues, copy them into fixtures, hard-code them or replay them from the HAR. Implement extraction of equivalent values from each new client session instead. The client may derive a value from its own public response, but must not import a captured value.

Public protocol metadata is safe to keep in a sanitized summary: usernames, numeric public IDs, operation names, `doc_id`s, endpoints, parameter/header names, variable types and structural response paths. Use the local analyzer for GraphQL requests:

```shell
python scripts/analyze_har.py profile.har --profile target_username
python scripts/analyze_har.py profile.har --profile target_username --json > har-summary.json
```

## Safe maintenance workflow

1. Capture a small logged-out HAR.
2. Inspect the HTML locally and produce a sanitized request summary.
3. Confirm that the public profile page contains the expected SSR result before changing the parser.
4. Add the smallest synthetic HTML fixture and offline unit test for every confirmed schema change.
5. Run the opt-in smoke suite only after offline tests pass.

Stop on `401`, `403`, `429`, HTML login walls or challenges. A public page can also fall back to metadata without the SSR records; report that response as unavailable rather than inventing profile or post data.

When changing post parsing, preserve the distinction between text-only posts, photos, videos with thumbnails and carousel children. Validate both the SSR first page and a cursor page. The refetch form includes browser-generated fields such as `__dyn`, `__csr`, `__hsdp`, `__hblp` and `__sjsp`; the current public endpoint accepts empty values for them, so do not hard-code captured values or expand a browser fingerprint unless a fresh-session experiment proves it necessary.

## Tests

Offline coverage is the default and needs no public network access:

```shell
pytest -q tests/test_threads_unit.py
```

The live smoke suite is deliberate and validates the public profile SSR page plus cursor pagination without testing command-line parsing:

```shell
OUTGRAM_RUN_THREADS_SMOKE=1 pytest -m threads_smoke
```

A smoke failure caused by a block, unavailable SSR payload or changed public endpoint is diagnostic information, not a reason to add authentication, browser simulation, proxy rotation or aggressive retries.
