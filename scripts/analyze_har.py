#!/usr/bin/env python3
"""Safely summarize public Instagram and Threads requests from a HAR file.

The output deliberately excludes request and response bodies, cookies,
authorization data, CSRF/LSD values, session/device identifiers and media URLs.
The optional public-identifier output includes only usernames and numeric public
IDs. It is intended to identify persisted-query document IDs and request shapes
that outgram must support. Inspect the HAR locally when its complete bootstrap
or request envelope is needed; never persist captured session values.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

INTERESTING_PATHS = ("/graphql/", "/api/graphql", "/api/v1/")
SENSITIVE_WORDS = (
    "auth",
    "cookie",
    "csrf",
    "device",
    "did",
    "lsd",
    "password",
    "session",
    "token",
)
PUBLIC_IDENTIFIER_FIELDS = ("id", "pk", "userID", "username")


def first(values: Dict[str, List[str]], name: str):
    value = values.get(name, [])
    return value[0] if value else None


def is_sensitive(name: str) -> bool:
    return any(word in name.lower() for word in SENSITIVE_WORDS)


def request_parameters(request: Dict[str, Any]) -> Dict[str, List[str]]:
    """Return URL and form parameters without exposing request headers."""
    result = parse_qs(urlparse(request["url"]).query)
    post_data = request.get("postData", {})
    if post_data.get("mimeType", "").startswith("application/x-www-form-urlencoded"):
        result.update(parse_qs(post_data.get("text", "")))
    return result


def value_shape(value: Any, depth: int = 0) -> Any:
    """Describe JSON types without retaining values or sensitive field names."""
    if depth == 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {
            "[redacted]" if is_sensitive(key) else key: value_shape(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [value_shape(value[0], depth + 1)] if value else []
    if value is None:
        return "null"
    return type(value).__name__


def public_identifiers(value: Any) -> Dict[str, Any]:
    """Extract explicit public profile identifiers without exposing session values."""
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key in PUBLIC_IDENTIFIER_FIELDS and isinstance(item, (str, int))
    }


def response_summary(response: Dict[str, Any]) -> Dict[str, Any]:
    """Return a small structural summary without exposing a response body."""
    content = response.get("content", {})
    result = {
        "content_type": next(
            (
                header["value"]
                for header in response.get("headers", [])
                if header["name"].lower() == "content-type"
            ),
            None,
        ),
        "size": content.get("size"),
    }
    text = content.get("text")
    if not text:
        return result
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        result["shape"] = "non-json"
        return result
    result["shape"] = value_shape(data)
    page_info = (
        data.get("data", {}).get("mediaData", {}).get("page_info", {})
        if isinstance(data, dict)
        else {}
    )
    result["has_page_info"] = bool(page_info)
    result["has_end_cursor"] = "end_cursor" in page_info
    result["has_next_page"] = "has_next_page" in page_info
    return result


def relevant_header_names(headers: List[Dict[str, str]]) -> List[str]:
    """Return non-sensitive request header names only."""
    return sorted(
        {header["name"] for header in headers if not is_sensitive(header["name"])}
    )


def relevant(
    entries: Iterable[Dict[str, Any]],
    profile: Optional[str],
    show_public_identifiers: bool = False,
):
    for index, entry in enumerate(entries):
        request = entry["request"]
        parsed_url = urlparse(request["url"])
        if not any(part in parsed_url.path for part in INTERESTING_PATHS):
            continue
        parameters = request_parameters(request)
        variables = first(parameters, "variables")
        referer = next(
            (
                header["value"]
                for header in request.get("headers", [])
                if header["name"].lower() == "referer"
            ),
            "",
        )
        if (
            profile
            and profile not in request["url"]
            and profile not in (variables or "")
            and profile not in referer
        ):
            continue
        try:
            variables_data = json.loads(variables) if variables else None
            variables_shape = value_shape(variables_data) if variables else None
        except ValueError:
            variables_data = None
            variables_shape = "invalid-json"
        response = entry.get("response", {})
        yield {
            "entry": index,
            "method": request["method"],
            "endpoint": f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}",
            "status": response.get("status"),
            "friendly_name": first(parameters, "fb_api_req_friendly_name"),
            "doc_id": first(parameters, "doc_id"),
            "variables": variables_shape,
            "public_identifiers": (
                public_identifiers(variables_data) if show_public_identifiers else None
            ),
            "form_parameters": sorted(
                "[redacted]" if is_sensitive(name) else name for name in parameters
            ),
            "request_headers": relevant_header_names(request.get("headers", [])),
            "response": response_summary(response),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "har", type=Path, help="HAR exported after visiting a public profile"
    )
    parser.add_argument(
        "-u",
        "--username",
        "--profile",
        dest="username",
        help="Optional username: retain only requests whose URL, variables or referrer mention it",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable summary",
    )
    parser.add_argument(
        "--show-public-identifiers",
        action="store_true",
        help="Include public username and numeric ID variables, never session values",
    )
    args = parser.parse_args()

    har = json.loads(args.har.read_text(encoding="utf-8"))
    rows = list(
        relevant(har["log"]["entries"], args.username, args.show_public_identifiers)
    )
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("No matching public API requests found.")
        return
    for row in rows:
        print(f"[{row['entry']}] {row['method']} {row['status']} {row['endpoint']}")
        print(f"  operation: {row['friendly_name'] or '-'}")
        print(f"  doc_id: {row['doc_id'] or '-'}")
        print(f"  variables: {json.dumps(row['variables'], ensure_ascii=False)}")
        if row["public_identifiers"]:
            print(
                f"  public identifiers: {json.dumps(row['public_identifiers'], ensure_ascii=False)}"
            )
        print(f"  form parameters: {', '.join(row['form_parameters']) or '-'}")
        print(f"  request headers: {', '.join(row['request_headers']) or '-'}")
        response = row["response"]
        print(
            f"  response: {response['content_type'] or '-'}, {response['size'] or 0} bytes"
        )
        print(
            f"  response shape: {json.dumps(response.get('shape'), ensure_ascii=False)}"
        )
        print(
            "  pagination: page_info={}, end_cursor={}, has_next_page={}".format(
                response.get("has_page_info", False),
                response.get("has_end_cursor", False),
                response.get("has_next_page", False),
            )
        )


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
