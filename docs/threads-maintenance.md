# Maintaining the Threads public scraper

Threads public Web GraphQL operations are implementation details, not a stable API. Persisted query IDs (`doc_id`), operation names, request variables and response schemas can change without notice. This guide covers only logged-out public profiles and timelines; do not use it to bypass private access, login walls, challenges or rate limits.

## Current implementation map

| Capability | Implementation |
| --- | --- |
| Bootstrap and profile lookup | `Threads.__post_init__`, `simple_profile`, `profile_from_user_id` |
| Public profile timeline | `profile_posts_from_user_id` |
| Pagination | `Threads.public_timeline_refetch_query` |
| Profile and post parsing | `_extract_profile`, `_extract_post` |

The canonical public domain is `https://www.threads.com/`. Query settings are grouped in named dictionaries on `Threads`; replace an expired operation or document ID there, not at individual call sites.

## Capture and inspect a small HAR

Use a disposable, logged-out browser profile. Capture one public profile, load one additional timeline page, then stop recording. HAR files can contain cookies, CSRF/LSD values, session or device identifiers and temporary media URLs. Never commit, attach, print or copy them into fixtures.

Create a local structural summary instead:

```shell
python scripts/analyze_har.py profile.har --profile target_username
python scripts/analyze_har.py profile.har --profile target_username --json > har-summary.json
```

The analyzer reports endpoints, operations, document IDs, field types, form/header names and limited response structure. It intentionally omits bodies, values and sensitive identifiers. Delete local HARs and summaries when they are no longer needed.

## Safe maintenance workflow

1. Capture a small logged-out HAR.
2. Produce and inspect its sanitized summary.
3. Compare the operation, `doc_id`, variables, endpoint and response path with the named query configuration.
4. Test the smallest public envelope derived from a new anonymous bootstrap. Do not reproduce session, device, cookie, CSRF or LSD values from the HAR.
5. Add the smallest synthetic fixture and offline unit test for every confirmed schema change.
6. Run the opt-in smoke suite only after offline tests pass.

Stop on `401`, `403`, `429`, HTML login walls or challenges. They mean the public collection is unavailable from that session or network; retry later rather than adding authentication, browser simulation, proxy rotation or aggressive retries.

Timeline pagination uses `page_info.has_next_page` and `end_cursor`. Stop when either is absent or the response has an invalid structure. Preserve the distinction between text-only posts, photos, videos with thumbnails and carousel children when changing the parser.

## Tests

Offline coverage is the default and needs no public network access:

```shell
pytest -q tests/test_threads_unit.py
```

The existing live test module is a deliberate smoke test. It sends public requests and must be enabled explicitly:

```shell
OUTGRAM_RUN_THREADS_SMOKE=1 pytest -m threads_smoke tests/test_threads.py
```

A smoke failure caused by a block or unavailable public endpoint is diagnostic information, not a reason to bypass the service. Update synthetic fixtures and unit tests before changing the smoke profiles or protocol configuration.
