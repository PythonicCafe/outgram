#!/usr/bin/env python3
"""Capture useful HAR files from public Instagram profiles through Lightpanda CDP.

Uses only the Python standard library. It starts `lightpanda serve`, drives a
page with the Chrome DevTools Protocol (CDP), records Network events and saves
a HAR 1.2 file. GraphQL request bodies and JSON/text GraphQL responses are
included when Lightpanda exposes them.
"""

import argparse
import base64
import hashlib
import json
import os
import random
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from urllib.request import urlopen

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._")
SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization", "set-cookie"}


class WebSocket:
    """Small RFC 6455 client sufficient for localhost CDP JSON messages."""

    def __init__(self, url, timeout):
        parsed = urlparse(url)
        if parsed.scheme != "ws" or not parsed.hostname:
            raise ValueError("Lightpanda must expose a ws:// CDP URL")
        self.sock = socket.create_connection((parsed.hostname, parsed.port or 80), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = (parsed.path or "/") + (("?" + parsed.query) if parsed.query else "")
        request = (
            "GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).format(path=path, host=parsed.netloc, key=key)
        self.sock.sendall(request.encode("ascii"))
        response = self._read_http_headers()
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if (
            " 101 " not in response.split("\r\n", 1)[0]
            or "sec-websocket-accept: " + expected.lower() not in response.lower()
        ):
            raise RuntimeError(
                "Lightpanda did not accept the CDP WebSocket connection: " + response.split("\r\n", 1)[0]
            )

    def _read_http_headers(self):
        data = b""
        while b"\r\n\r\n" not in data:
            block = self.sock.recv(4096)
            if not block:
                raise ConnectionError("CDP server closed during WebSocket handshake")
            data += block
        return data.decode("latin-1")

    def _exact(self, length):
        data = b""
        while len(data) < length:
            block = self.sock.recv(length - len(data))
            if not block:
                raise ConnectionError("CDP server closed the WebSocket")
            data += block
        return data

    def send_json(self, message):
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        length = len(payload)
        if length < 126:
            header = bytes((0x81, 0x80 | length))
        elif length <= 0xFFFF:
            header = bytes((0x81, 0x80 | 126)) + struct.pack("!H", length)
        else:
            header = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", length)
        self.sock.sendall(header + mask + masked)

    def receive_json(self):
        first, second = self._exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._exact(8))[0]
        mask = self._exact(4) if masked else None
        payload = self._exact(length)
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        if opcode == 0x8:
            raise ConnectionError("CDP WebSocket closed")
        if opcode == 0x9:
            self.sock.sendall(b"\x8a\x80\x00\x00\x00\x00")
            return self.receive_json()
        if opcode != 0x1:
            return self.receive_json()
        return json.loads(payload.decode("utf-8"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    def __init__(self, websocket_url, timeout):
        self.ws = WebSocket(websocket_url, timeout)
        self.timeout = timeout
        self.next_id = 1
        self.events = []

    def receive(self, timeout=None):
        old_timeout = self.ws.sock.gettimeout()
        self.ws.sock.settimeout(self.timeout if timeout is None else timeout)
        try:
            return self.ws.receive_json()
        finally:
            self.ws.sock.settimeout(old_timeout)

    def call(self, method, params=None, session_id=None):
        message_id = self.next_id
        self.next_id += 1
        message = {"id": message_id, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        self.ws.send_json(message)
        while True:
            message = self.receive()
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(method + ": " + message["error"].get("message", "CDP error"))
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)

    def collect_for(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                message = self.receive(timeout=min(0.5, deadline - time.monotonic()))
            except socket.timeout:
                continue
            if "method" in message:
                self.events.append(message)

    def close(self):
        self.ws.close()


def wait_for_cdp(port, timeout):
    deadline = time.monotonic() + timeout
    url = "http://127.0.0.1:{}/json/version".format(port)
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                return json.load(response)["webSocketDebuggerUrl"]
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("Lightpanda CDP endpoint did not start on port {}".format(port))


def header_list(headers, keep_cookies):
    result = []
    for name, value in (headers or {}).items():
        if not keep_cookies and name.lower() in SENSITIVE_HEADERS:
            continue
        result.append({"name": name, "value": str(value)})
    return result


def iso_time(wall_time):
    if wall_time is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(wall_time, timezone.utc).isoformat().replace("+00:00", "Z")


def is_graphql(url):
    return "/graphql" in url or "/api/graphql" in url


def make_har(cdp, session_id, keep_cookies, max_body_bytes):
    requests = {}
    responses = {}
    finished = {}
    for event in cdp.events:
        params = event.get("params", {})
        if event.get("method") == "Network.requestWillBeSent":
            requests[params["requestId"]] = params
        elif event.get("method") == "Network.responseReceived":
            responses[params["requestId"]] = params
        elif event.get("method") == "Network.loadingFinished":
            finished[params["requestId"]] = params

    entries = []
    for request_id, event in requests.items():
        request = event["request"]
        response_event = responses.get(request_id, {})
        response = response_event.get("response", {})
        url = request["url"]
        response_body = None
        base64_encoded = False
        # Bodies are most valuable for GraphQL and are bounded to avoid saving videos.
        if (
            request_id in finished
            and is_graphql(url)
            and finished[request_id].get("encodedDataLength", 0) <= max_body_bytes
        ):
            try:
                body = cdp.call("Network.getResponseBody", {"requestId": request_id}, session_id)
                response_body = body.get("body")
                base64_encoded = body.get("base64Encoded", False)
            except RuntimeError:
                pass
        parsed = urlparse(url)
        post_data = request.get("postData")
        if post_data is None and request.get("method") == "POST":
            try:
                post_data = cdp.call("Network.getRequestPostData", {"requestId": request_id}, session_id).get(
                    "postData"
                )
            except RuntimeError:
                pass
        har_request = {
            "method": request.get("method", "GET"),
            "url": url,
            "httpVersion": "HTTP/1.1",
            "headers": header_list(request.get("headers"), keep_cookies),
            "queryString": [
                {"name": key, "value": value} for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            ],
            "cookies": [],
            "headersSize": -1,
            "bodySize": len(post_data.encode("utf-8")) if post_data else 0,
        }
        if post_data is not None:
            har_request["postData"] = {
                "mimeType": request.get("headers", {}).get("Content-Type", ""),
                "text": post_data,
            }
        content = {
            "size": finished.get(request_id, {}).get("encodedDataLength", 0),
            "mimeType": response.get("mimeType", ""),
        }
        if response_body is not None:
            content["text"] = response_body
            if base64_encoded:
                content["encoding"] = "base64"
        timing = response.get("timing", {})
        wait = timing.get("receiveHeadersEnd", -1)
        entries.append(
            {
                "startedDateTime": iso_time(event.get("wallTime")),
                "time": max(0, wait),
                "request": har_request,
                "response": {
                    "status": response.get("status", 0),
                    "statusText": response.get("statusText", ""),
                    "httpVersion": "HTTP/1.1",
                    "headers": header_list(response.get("headers"), keep_cookies),
                    "cookies": [],
                    "content": content,
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": content["size"],
                },
                "cache": {},
                "timings": {"send": -1, "wait": wait, "receive": 0},
            }
        )
    return entries


def valid_username(value):
    return 0 < len(value) <= 30 and all(char in USERNAME_CHARS for char in value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="+", help="public usernames, without @")
    parser.add_argument("--lightpanda", default="lightpanda")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-p", "--port", type=int, default=9222)
    parser.add_argument("-s", "--scrolls", type=int, default=2)
    parser.add_argument("--min-wait", type=float, default=2.0)
    parser.add_argument("--max-wait", type=float, default=5.0)
    parser.add_argument("-t", "--startup-timeout", type=float, default=15.0)
    parser.add_argument("--max-graphql-body-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument(
        "--keep-cookies", action="store_true", help="keep Cookie, Set-Cookie and Authorization headers in the HAR"
    )
    args = parser.parse_args()
    invalid = [profile for profile in args.profiles if not valid_username(profile)]
    if invalid or args.scrolls < 0 or args.min_wait < 0 or args.max_wait < args.min_wait:
        parser.error("invalid profile, scroll count or wait interval")

    environment = os.environ.copy()
    environment.setdefault("LIGHTPANDA_DISABLE_TELEMETRY", "true")
    environment.setdefault("LIGHTPANDA_DISABLE_CORE_DUMP", "true")
    process = subprocess.Popen(
        [args.lightpanda, "serve", "--host", "127.0.0.1", "--port", str(args.port), "--disable-metrics"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    cdp = None
    try:
        cdp = CDP(wait_for_cdp(args.port, args.startup_timeout), timeout=30)
        target_id = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        session_id = cdp.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
        cdp.call("Page.enable", session_id=session_id)
        cdp.call("Network.enable", session_id=session_id)
        for profile in args.profiles:
            print("Visiting @{}".format(profile), file=sys.stderr)
            cdp.call("Page.navigate", {"url": "https://www.instagram.com/{}/".format(profile)}, session_id)
            cdp.collect_for(random.uniform(args.min_wait, args.max_wait))
            for _ in range(args.scrolls):
                cdp.call("Runtime.evaluate", {"expression": "window.scrollBy(0, 1200)"}, session_id)
                cdp.collect_for(random.uniform(args.min_wait, args.max_wait))
        entries = make_har(cdp, session_id, args.keep_cookies, args.max_graphql_body_bytes)
    finally:
        if cdp:
            cdp.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "outgram Lightpanda CDP capture", "version": "1"},
            "comment": "Captured through Lightpanda CDP. Cookie, Set-Cookie and Authorization headers are removed unless --keep-cookies is supplied. GraphQL response bodies are included up to the configured limit.",
            "entries": entries,
        }
    }
    args.output.write_text(json.dumps(har, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved {} network entries to {}".format(len(entries), args.output), file=sys.stderr)


if __name__ == "__main__":
    main()
