"""ASGI guards that run before any request body is read.

FastAPI parses multipart bodies before running dependencies, so auth, size and rate limits live
here: a wrong key or an oversized upload is rejected without buffering hundreds of megabytes.
"""

from __future__ import annotations

import ipaddress
import json
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import TrustProxy

PUBLIC_PREFIX = "/api/v1/"
UI_PREFIX = "/ui/"
UPLOAD_PATHS = ("/api/v1/analyze", "/ui/analyze")
MULTIPART_OVERHEAD = 1024 * 1024
WINDOW_SEC = 60.0
MAX_TRACKED_CLIENTS = 10_000
MEDIA_ROUTE = re.compile(r"/ui/jobs/[0-9a-f]{16}/(preview\.mp4|frames/\d{1,3}/\d\.jpg)")

# The SPA is served from the same origin; inline style attributes are used for progress bars.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "media-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", CSP.encode()),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


async def _send_json(send: Send, status: int, body: dict, headers: dict[str, str] | None = None) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    hdrs = [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())]
    hdrs += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": hdrs})
    await send({"type": "http.response.body", "body": raw})


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class ApiKeyMiddleware:
    """/api/v1/*: require X-API-Key matching one of the configured keys. 401 without details."""

    def __init__(self, app: ASGIApp, keys: tuple[str, ...]) -> None:
        self.app = app
        self._keys = tuple(k.encode() for k in keys)

    def _valid(self, provided: str | None) -> bool:
        if not provided:
            return False
        candidate = provided.encode("latin-1", errors="replace")
        # Compare against every key so timing does not reveal which one matched.
        return sum(secrets.compare_digest(candidate, k) for k in self._keys) > 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(PUBLIC_PREFIX):
            if not self._valid(_header(scope, b"x-api-key")):
                await _send_json(send, 401, {"detail": "Unauthorized"})
                return
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Upload routes: reject by Content-Length, and cut chunked bodies once they pass the limit."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self._limit = max_bytes + MULTIPART_OVERHEAD

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in UPLOAD_PATHS:
            await self.app(scope, receive, send)
            return
        declared = _header(scope, b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._limit:
            await _send_json(send, 413, {"detail": "File too large", "code": "file_too_large"})
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_json(send, 413, {"detail": "File too large", "code": "file_too_large"})


class _BodyTooLarge(Exception):
    pass


class SlidingWindowLimiter:
    """In-memory per-key limiter: at most `limit` hits per WINDOW_SEC."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the next slot frees up."""
        now = self._clock()
        with self._lock:
            window = self._hits.setdefault(key, deque())
            while window and now - window[0] >= WINDOW_SEC:
                window.popleft()
            if len(window) >= self.limit:
                return max(1.0, WINDOW_SEC - (now - window[0]))
            window.append(now)
            if len(self._hits) > MAX_TRACKED_CLIENTS:  # address churn: drop idle entries, then refuse
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < WINDOW_SEC}
                if len(self._hits) > MAX_TRACKED_CLIENTS:
                    self._hits.pop(key, None)
                    return WINDOW_SEC
            return None


def _rate_key(ip: str) -> str:
    """IPv6 clients usually control a whole /64, so they are limited per /64."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def client_ip(scope: Scope, trust: TrustProxy) -> str:
    """Only the header the configured proxy guarantees to set is trusted; anything else is spoofable."""
    if trust is TrustProxy.CLOUDFLARE:
        cf = _header(scope, b"cf-connecting-ip")
        if cf:
            return cf.strip()
    elif trust is TrustProxy.XFF:
        xff = _header(scope, b"x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()  # right-most hop = what our own proxy saw
    client = scope.get("client")
    return client[0] if client else "unknown"


class UiRateLimitMiddleware:
    """/ui/*: separate budgets for uploads and for polling/other reads."""

    def __init__(self, app: ASGIApp, *, uploads_per_min: int, reads_per_min: int, trust_proxy: TrustProxy) -> None:
        self.app = app
        self.uploads = SlidingWindowLimiter(uploads_per_min)
        self.reads = SlidingWindowLimiter(reads_per_min)
        self._trust = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(UI_PREFIX):
            is_upload = scope["method"] == "POST" and scope["path"] in UPLOAD_PATHS
            # Media (preview video ranges, frames) is fetched in many small requests; do not count it.
            is_media = scope["method"] == "GET" and MEDIA_ROUTE.fullmatch(scope["path"]) is not None
            if not is_media:
                limiter = self.uploads if is_upload else self.reads
                retry = limiter.hit(_rate_key(client_ip(scope, self._trust)))
                if retry is not None:
                    await _send_json(send, 429, {"detail": "Too many requests", "code": "rate_limited"},
                                     {"Retry-After": str(int(retry))})  # fmt: skip
                    return
        await self.app(scope, receive, send)



class SecurityHeadersMiddleware:
    """Adds hardening headers to every HTTP response; /api/v1 and /ui/jobs are also never cached."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        no_store = scope["path"].startswith((PUBLIC_PREFIX, "/ui/jobs/"))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in SECURITY_HEADERS if k not in present]
                if no_store and b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
