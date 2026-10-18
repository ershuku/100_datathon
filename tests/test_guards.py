from __future__ import annotations

from app.api.guards import SlidingWindowLimiter, _rate_key, client_ip
from app.config import TrustProxy


def _scope(client: str, **headers: str) -> dict:
    return {"client": (client, 1234), "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]}


def test_headers_ignored_unless_proxy_mode_configured():
    scope = _scope("10.0.0.1", cf_connecting_ip="1.1.1.1", x_forwarded_for="2.2.2.2")
    assert client_ip(scope, TrustProxy.NONE) == "10.0.0.1"


def test_cloudflare_mode_reads_only_cf_header():
    scope = _scope("10.0.0.1", cf_connecting_ip="1.1.1.1", x_forwarded_for="2.2.2.2")
    assert client_ip(scope, TrustProxy.CLOUDFLARE) == "1.1.1.1"


def test_xff_mode_uses_right_most_hop_not_spoofable_left():
    scope = _scope("127.0.0.1", cf_connecting_ip="9.9.9.9", x_forwarded_for="6.6.6.6, 3.3.3.3")
    assert client_ip(scope, TrustProxy.XFF) == "3.3.3.3"


def test_ipv6_limited_per_64():
    assert _rate_key("2001:db8:1:2:aaaa::1") == _rate_key("2001:db8:1:2:bbbb::2")
    assert _rate_key("203.0.113.5") == "203.0.113.5"


def test_sliding_window():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, clock=lambda: now[0])
    assert limiter.hit("a") is None and limiter.hit("a") is None
    assert limiter.hit("a") is not None
    now[0] = 61.0
    assert limiter.hit("a") is None
