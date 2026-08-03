#!/usr/bin/env python3
"""Summarize Instagram API requests from a browser-exported HAR file.

The output deliberately excludes cookies, authorization headers and response bodies. It is intended to identify stale
persisted-query document IDs and the request shape that outgram must support.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

INTERESTING_PATHS = ("/graphql/", "/api/graphql", "/api/v1/")


def first(values: Dict[str, List[str]], name: str):
    value = values.get(name, [])
    return value[0] if value else None


def request_parameters(request: Dict[str, Any]) -> Dict[str, List[str]]:
    """Return URL and form parameters without exposing request headers."""
    result = parse_qs(urlparse(request["url"]).query)
    post_data = request.get("postData", {})
    if post_data.get("mimeType", "").startswith("application/x-www-form-urlencoded"):
        result.update(parse_qs(post_data.get("text", "")))
    return result


def redact(value: Any) -> Any:
    """Remove browser/session identifiers before displaying request variables."""
    sensitive = ("auth", "cookie", "csrf", "device", "did", "lsd", "password", "session", "token")
    if isinstance(value, dict):
        return {
            key: "[redacted]" if any(word in key.lower() for word in sensitive) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def relevant(entries: Iterable[Dict[str, Any]], profile: Optional[str]):
    for index, entry in enumerate(entries):
        request = entry["request"]
        parsed_url = urlparse(request["url"])
        if not any(part in parsed_url.path for part in INTERESTING_PATHS):
            continue
        parameters = request_parameters(request)
        variables = first(parameters, "variables")
        referer = next(
            (header["value"] for header in request.get("headers", []) if header["name"].lower() == "referer"),
            "",
        )
        # Timeline variables commonly contain only a numeric user ID; referer is
        # therefore also used to exclude unrelated recommendations/dialogs.
        if profile and profile not in request["url"] and profile not in (variables or "") and profile not in referer:
            continue
        response = entry.get("response", {})
        yield {
            "entry": index,
            "method": request["method"],
            "endpoint": f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}",
            "status": response.get("status"),
            "friendly_name": first(parameters, "fb_api_req_friendly_name"),
            "doc_id": first(parameters, "doc_id"),
            "variables": redact(json.loads(variables)) if variables else None,
            "response_content_type": next(
                (header["value"] for header in response.get("headers", []) if header["name"].lower() == "content-type"),
                None,
            ),
            "response_size": response.get("content", {}).get("size"),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path, help="HAR exported after visiting a public profile")
    parser.add_argument(
        "-u",
        "--username",
        "--profile",
        dest="username",
        help="Optional username: retain only requests whose URL/variables mention it",
    )
    parser.add_argument("-j", "--json", action="store_true", help="Emit JSON instead of a human-readable table")
    args = parser.parse_args()
    har_filename = args.har
    username = args.username
    output_json = args.json

    har = json.loads(har_filename.read_text(encoding="utf-8"))
    rows = list(relevant(har["log"]["entries"], username))
    if output_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    if not rows:
        print("No matching Instagram API requests found.")
        return
    for row in rows:
        print(f"[{row['entry']}] {row['method']} {row['status']} {row['endpoint']}")
        print(f"  operation: {row['friendly_name'] or '-'}")
        print(f"  doc_id: {row['doc_id'] or '-'}")
        print(f"  variables: {json.dumps(row['variables'], ensure_ascii=False)}")
        print(f"  response: {row['response_content_type'] or '-'}, {row['response_size'] or 0} bytes")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Allow piping a large summary to tools such as `head`.
        pass
