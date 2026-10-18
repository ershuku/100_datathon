from __future__ import annotations

import pytest

from conftest import auth, needs_ffmpeg, upload

pytestmark = needs_ffmpeg


@pytest.mark.parametrize(
    ("key", "status", "code"),
    [
        ("mp4", 415, "unsupported_extension"),
        ("avi_as_mov", 415, "unsupported_container"),
        ("text_as_mov", 415, "unsupported_container"),
        ("truncated", 422, "unreadable_video"),
    ],
)
def test_rejects_bad_files_with_clear_4xx(make_client, make_settings, videos, key, status, code):
    client = make_client()
    resp = upload(client, videos[key])
    assert resp.status_code == status
    assert resp.json()["code"] == code


def test_extension_check_is_case_insensitive(make_client, videos):
    resp = upload(make_client(), videos["h264"], name="CLIP.MOV")
    assert resp.status_code == 200


def test_missing_file_field(make_client):
    resp = make_client().post("/api/v1/analyze", headers=auth(), files={"other": ("a.mov", b"x")})
    assert resp.status_code == 400 and resp.json()["code"] == "missing_file"


def test_not_multipart(make_client):
    resp = make_client().post("/api/v1/analyze", headers=auth(), content=b"raw")
    assert resp.status_code == 400 and resp.json()["code"] == "not_multipart"


def test_empty_file(make_client):
    resp = make_client().post("/api/v1/analyze", headers=auth(), files={"file": ("a.mov", b"")})
    assert resp.status_code == 400 and resp.json()["code"] == "empty_file"


def test_too_large_is_413(make_client):
    client = make_client(max_upload_mb=1)
    resp = client.post("/api/v1/analyze", headers=auth(), files={"file": ("a.mov", b"0" * (3 * 1024 * 1024))})
    assert resp.status_code == 413 and resp.json()["code"] == "file_too_large"


def test_duration_bounds(make_client, videos):
    resp = upload(make_client(max_duration_sec=2), videos["h264"])
    assert resp.status_code == 422 and resp.json()["code"] == "duration_out_of_range"


def test_queue_full_is_503(make_client, videos):
    client = make_client(max_queue=1, dummy_delay_sec=5)
    assert upload(client, videos["h264"]).status_code == 200
    resp = upload(client, videos["h264"])
    assert resp.status_code == 503 and resp.headers["Retry-After"]


def test_rejected_uploads_leave_no_files(make_client, make_settings, videos):
    client = make_client()
    for key in ("mp4", "avi_as_mov", "text_as_mov"):
        upload(client, videos[key])
    data_dir = make_settings().data_dir
    assert list((data_dir / "uploads").iterdir()) == []
    assert list((data_dir / "jobs").iterdir()) == []


def test_ui_cannot_take_slots_reserved_for_the_jury(make_client, videos):
    client = make_client(max_queue=2, api_reserved_slots=1, dummy_delay_sec=5)
    assert upload(client, videos["h264"], url="/ui/analyze", headers={}).status_code == 200
    ui_resp = upload(client, videos["h264"], url="/ui/analyze", headers={})
    assert ui_resp.status_code == 503 and ui_resp.json()["code"] == "queue_full"
    assert upload(client, videos["h264"]).status_code == 200  # the API still gets the reserved slot


def test_resolution_cap(make_client, videos):
    resp = upload(make_client(max_video_side_px=320), videos["h264"])
    assert resp.status_code == 415 and resp.json()["code"] == "unsupported_resolution"
