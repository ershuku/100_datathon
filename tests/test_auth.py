from __future__ import annotations

import pytest

from app.config import Settings
from conftest import API_KEYS, KEY, KEY_TWO, auth, needs_ffmpeg, upload

pytestmark = needs_ffmpeg


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}, {"X-API-Key": API_KEYS}])
def test_public_routes_reject_missing_or_wrong_key(make_client, headers):
    client = make_client()
    for resp in (client.get("/api/v1/jobs/0123456789abcdef", headers=headers),
                 client.post("/api/v1/analyze", headers=headers, files={"file": ("a.mov", b"x")})):  # fmt: skip
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}


def test_every_key_in_comma_list_is_accepted(make_client, videos):
    client = make_client()
    for key in (KEY, KEY_TWO):
        resp = upload(client, videos["h264"], headers=auth(key))
        assert resp.status_code == 200, resp.text


def test_wrong_key_is_rejected_before_body_is_read(make_client):
    client = make_client(max_upload_mb=1)
    resp = client.post("/api/v1/analyze", headers={"X-API-Key": "nope"},
                       files={"file": ("big.mov", b"0" * (3 * 1024 * 1024))})  # fmt: skip
    assert resp.status_code == 401  # not 413: auth runs first


def test_ui_and_health_need_no_key(make_client):
    client = make_client()
    assert client.get("/health").status_code == 200
    assert client.get("/ui/config").status_code == 200
    assert client.get("/ui/jobs/0123456789abcdef").status_code == 404


@pytest.mark.parametrize("key", ["change-me", "short", "dev-key", " , "])
def test_weak_or_placeholder_keys_are_refused_at_startup(key, tmp_path):
    with pytest.raises(ValueError):
        Settings(_env_file=None, api_key=key, data_dir=tmp_path)


def test_security_headers_on_every_response(make_client):
    client = make_client()
    for resp in (client.get("/api/v1/jobs/0123456789abcdef"), client.get("/ui/config"), client.get("/health")):
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert client.get("/api/v1/jobs/0123456789abcdef").headers["cache-control"] == "no-store"
