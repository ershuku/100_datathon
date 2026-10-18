from __future__ import annotations

import base64
import io
import time

from PIL import Image

from app.jobs.store import JobStore
from conftest import auth, needs_ffmpeg, upload, wait_for

pytestmark = needs_ffmpeg


def _submit(client, path, **kw) -> str:
    resp = upload(client, path, **kw)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"job_id"}
    return body["job_id"]


def test_processing_then_done_with_violations(make_client, videos):
    client = make_client(dummy_delay_sec=1.5)
    job_id = _submit(client, videos["h264"])
    first = client.get(f"/api/v1/jobs/{job_id}", headers=auth()).json()
    assert first == {"job_id": job_id, "status": "processing"}

    done = wait_for(client, job_id)
    assert done["status"] == "done"
    assert done["verdict"] == "violation"
    assert len(done["violations"]) == 2
    for v in done["violations"]:
        assert set(v) == {"type", "timecode_sec", "description", "evidence_frames"}
        assert v["timecode_sec"] == round(v["timecode_sec"], 1)
        assert 1 <= len(v["evidence_frames"]) <= 3
        assert v["description"].startswith("[ТЕСТОВЫЙ РЕЖИМ]")
        for f in v["evidence_frames"]:
            assert not f["image_base64"].startswith("data:")
            assert 0 <= f["timestamp_sec"] <= 4.0


def test_no_violation_has_empty_list(make_client, videos):
    client = make_client(dummy_scenario="none")
    done = wait_for(client, _submit(client, videos["h264"]))
    assert done == {"job_id": done["job_id"], "status": "done", "verdict": "no_violation", "violations": []}


def test_analyzer_crash_is_failed_not_no_violation(make_client, videos):
    client = make_client(dummy_scenario="crash")
    done = wait_for(client, _submit(client, videos["h264"]))
    assert done["status"] == "failed"
    assert set(done) == {"job_id", "status", "error"}
    assert done["error"] == "analysis failed"


def test_unknown_and_malformed_job_ids_are_404(make_client):
    client = make_client()
    for job_id in ("0123456789abcdef", "nope", "../../etc/passwd", "0123456789ABCDEF"):
        assert client.get(f"/api/v1/jobs/{job_id}", headers=auth()).status_code == 404


def test_hevc_with_rotation_is_normalized_upright(make_client, videos):
    client = make_client()
    job_id = _submit(client, videos["hevc_rot"])
    ui = wait_for(client, job_id, ui=True)
    assert ui["status"] == "done", ui
    assert (ui["video"]["width"], ui["video"]["height"]) == (720, 1280)
    frame_url = ui["violations"][0]["evidence_frames"][0]["url"]
    img = Image.open(io.BytesIO(client.get(frame_url).content))
    assert img.height > img.width  # rotation applied to evidence
    preview = client.get(ui["video"]["preview_url"], headers={"Range": "bytes=0-99"})
    assert preview.status_code == 206 and len(preview.content) == 100


def test_queue_positions_with_single_slot(make_client, videos):
    client = make_client(dummy_delay_sec=3, worker_concurrency=1)
    ids = [_submit(client, videos["h264"]) for _ in range(3)]
    time.sleep(0.5)
    states = [client.get(f"/ui/jobs/{i}").json() for i in ids]
    assert states[0]["status"] == "processing"
    assert [s["queue_position"] for s in states[1:]] == [1, 2]
    for i in ids:
        assert wait_for(client, i)["status"] == "done"
    timings = client.get(f"/ui/jobs/{ids[2]}").json()["timings"]
    assert timings["queue_wait_sec"] > 3


def test_restart_marks_interrupted_jobs_failed(make_client, make_settings):
    settings = make_settings()
    store = JobStore(settings.db_path)
    store.create("aaaaaaaaaaaaaaaa", created_at=time.time(), video_meta={})
    store.update("aaaaaaaaaaaaaaaa", status="processing")
    store.create("bbbbbbbbbbbbbbbb", created_at=time.time(), video_meta={})
    store.close()

    client = make_client(data_dir=settings.data_dir)
    for job_id in ("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"):
        body = client.get(f"/api/v1/jobs/{job_id}", headers=auth()).json()
        assert body == {"job_id": job_id, "status": "failed", "error": "interrupted by service restart"}


def test_evidence_base64_is_valid_capped_jpeg(make_client, videos):
    client = make_client()
    done = wait_for(client, _submit(client, videos["hevc"]))
    for v in done["violations"]:
        for f in v["evidence_frames"]:
            raw = base64.b64decode(f["image_base64"], validate=True)
            assert raw[:3] == b"\xff\xd8\xff" and len(raw) <= 300_000
            img = Image.open(io.BytesIO(raw))
            img.verify()
            assert img.format == "JPEG" and max(img.size) <= 1280
