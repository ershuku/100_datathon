from __future__ import annotations

import time

from app.jobs.janitor import sweep
from conftest import auth, needs_ffmpeg, upload, wait_for

pytestmark = needs_ffmpeg


def test_ttl_deletes_video_files_but_keeps_json(make_client, videos):
    client = make_client(file_ttl_sec=0)
    job_id = upload(client, videos["h264"]).json()["job_id"]
    before = wait_for(client, job_id)
    settings = client.app.state.settings
    job_dir = settings.jobs_dir / job_id
    assert not (job_dir / "upload.mov").exists()  # original removed as soon as the job ends
    assert (job_dir / "normalized.mp4").exists()

    assert sweep(settings, client.app.state.store) == 1
    assert not job_dir.exists()
    assert client.get(f"/api/v1/jobs/{job_id}", headers=auth()).json() == before
    ui = client.get(f"/ui/jobs/{job_id}").json()
    assert ui["video"]["preview_url"] is None
    assert client.get(f"/ui/jobs/{job_id}/preview.mp4").status_code == 404
    assert client.get(ui["violations"][0]["evidence_frames"][0]["url"]).status_code == 200


def test_ttl_not_reached_keeps_files(make_client, videos):
    client = make_client(file_ttl_sec=3600)
    job_id = upload(client, videos["h264"]).json()["job_id"]
    wait_for(client, job_id)
    assert sweep(client.app.state.settings, client.app.state.store) == 0
    assert (client.app.state.settings.jobs_dir / job_id / "normalized.mp4").exists()


def test_timeout_fails_job_and_kills_analyzer(make_client, videos):
    client = make_client(dummy_scenario="slow", job_timeout_sec=5)
    t0 = time.monotonic()
    job_id = upload(client, videos["h264"]).json()["job_id"]
    body = wait_for(client, job_id, timeout=20)
    assert body == {"job_id": job_id, "status": "failed", "error": "timeout"}
    assert time.monotonic() - t0 < 10


def test_partial_fallback_returns_events_found_so_far(make_client, videos):
    client = make_client(dummy_scenario="slow", job_timeout_sec=12, timeout_fallback="partial", min_analyze_sec=2)
    job_id = upload(client, videos["h264"]).json()["job_id"]
    body = wait_for(client, job_id, timeout=20)
    assert body["status"] == "done" and body["verdict"] == "violation" and len(body["violations"]) == 2
    assert client.get(f"/ui/jobs/{job_id}").json()["partial"] is True


def test_queue_wait_counts_against_deadline(make_client, videos):
    client = make_client(dummy_scenario="slow", job_timeout_sec=5, worker_concurrency=1)
    first = upload(client, videos["h264"]).json()["job_id"]
    second = upload(client, videos["h264"]).json()["job_id"]
    assert wait_for(client, first, timeout=20)["error"] == "timeout"
    body = wait_for(client, second, timeout=20)
    assert body["error"] == "timeout"
    assert client.get(f"/ui/jobs/{second}").json()["timings"]["total_sec"] < 8


def test_partial_fallback_never_turns_an_early_timeout_into_no_violation(make_client, videos):
    # Budget runs out before analysis even starts: there is nothing partial to report.
    client = make_client(dummy_scenario="none", job_timeout_sec=1.2, evidence_reserve_sec=1.0,
                         timeout_fallback="partial")
    job_id = upload(client, videos["hevc"]).json()["job_id"]
    assert wait_for(client, job_id, timeout=20) == {"job_id": job_id, "status": "failed", "error": "timeout"}


def test_violation_count_is_capped(make_client, videos):
    client = make_client(max_violations=1)
    body = wait_for(client, upload(client, videos["h264"]).json()["job_id"])
    assert body["verdict"] == "violation" and len(body["violations"]) == 1
