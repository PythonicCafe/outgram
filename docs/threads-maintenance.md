# Maintaining the Threads public scraper

Threads public Web responses are implementation details, not a stable API. This guide covers only logged-out public profiles. Do not use it to bypass private access, login walls, challenges or rate limits.

## Current implementation map

| Capability | Implementation |
| --- | --- |
| Profile by username | `Threads.simple_profile` and `profile_from_username` |
| First public timeline page by username | `Threads.profile_posts_from_username` |
| SSR parser | `ThreadsPublicPageHTMLParser` and `Threads._relay_results` |
| Profile and post parsing | `_extract_profile` and `_extract_post` |

The client navigates to `https://www.threads.com/@<username>` with document-navigation headers. The logged-out HTML can contain `RelayPrefetchedStreamCache` records whose `result.data.user` and `result.data.mediaData` provide the profile and initial timeline page.

Numeric-ID lookup and timeline pagination are not currently supported. The previously observed GraphQL documents require a browser request envelope that has not been reproduced from a fresh public session. The client must raise a contextual error for those paths rather than replay HAR values or return a partial archive silently.

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

When changing post parsing, preserve the distinction between text-only posts, photos, videos with thumbnails and carousel children. The first-page generator raises if it needs an unimplemented later page. Consumers that intentionally need only a small prefix must set a post limit before collection continues to pagination.

## Tests

Offline coverage is the default and needs no public network access:

```shell
pytest -q tests/test_threads_unit.py
```

The live smoke suite is deliberate and sends two conservative requests to the public service:

```shell
OUTGRAM_RUN_THREADS_SMOKE=1 pytest -m threads_smoke tests/test_threads.py
```

A smoke failure caused by a block, unavailable SSR payload or changed public endpoint is diagnostic information, not a reason to add authentication, browser simulation, proxy rotation or aggressive retries.
