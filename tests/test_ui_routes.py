from __future__ import annotations

from conftest import auth, needs_ffmpeg, upload, wait_for

pytestmark = needs_ffmpeg


def _ui_upload(client, videos):
    resp = upload(client, videos["h264"], url="/ui/analyze", headers={})
    assert resp.status_code == 200, resp.text
    return resp.json()["job_id"]


def test_ui_flow_returns_extended_fields(make_client, videos):
    client = make_client()
    job_id = _ui_upload(client, videos)
    body = wait_for(client, job_id, ui=True)
    assert body["status"] == "done" and body["progress"] == 100
    v = body["violations"][0]
    assert {"type_code", "legal_ref", "needs_review"} <= set(v)
    assert body["timings"]["processing_sec"] > 0
    frame = client.get(v["evidence_frames"][0]["url"])
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"
    assert client.get(f"/ui/jobs/{job_id}/frames/9/0.jpg").status_code == 404


def test_result_download_equals_public_api(make_client, videos):
    client = make_client()
    job_id = _ui_upload(client, videos)
    wait_for(client, job_id, ui=True)
    download = client.get(f"/ui/jobs/{job_id}/result.json")
    assert "attachment" in download.headers["content-disposition"]
    assert download.json() == client.get(f"/api/v1/jobs/{job_id}", headers=auth()).json()


def test_ui_upload_rate_limit(make_client, videos):
    client = make_client(ui_upload_per_min=1)
    _ui_upload(client, videos)
    resp = upload(client, videos["h264"], url="/ui/analyze", headers={})
    assert resp.status_code == 429 and int(resp.headers["Retry-After"]) >= 1
    # the public API is not affected by the UI limiter
    assert upload(client, videos["h264"]).status_code == 200


def test_ui_config_and_health(make_client):
    client = make_client()
    assert client.get("/ui/config").json() == {"pipeline": "dummy", "max_upload_mb": 300, "poll_interval_ms": 2000}
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["pipeline"] == "dummy" and health["queue_length"] == 0
    assert isinstance(health["gpu"], bool)
