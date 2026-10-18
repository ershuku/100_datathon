"""Jury-first scheduling, UI caps, expiry of queued jobs, no analyzer restart after shutdown."""

from __future__ import annotations

import time

import pytest

from app.analysis.port import AnalyzerError
from app.analysis.runner import AnalyzerProcess
from app.jobs.janitor import expire_queued
from app.jobs.store import JobStore
from conftest import needs_ffmpeg, upload, wait_for


@needs_ffmpeg
def test_api_jobs_run_before_waiting_ui_jobs(make_client, videos):
    client = make_client(dummy_delay_sec=3, worker_concurrency=1, ui_max_active=5)
    ui_first = upload(client, videos["h264"], url="/ui/analyze", headers={}).json()["job_id"]
    ui_second = upload(client, videos["h264"], url="/ui/analyze", headers={}).json()["job_id"]
    jury = upload(client, videos["h264"]).json()["job_id"]
    time.sleep(0.5)
    assert client.get(f"/ui/jobs/{jury}").json()["queue_position"] == 1
    assert client.get(f"/ui/jobs/{ui_second}").json()["queue_position"] == 2

    wait_for(client, jury)
    assert client.get(f"/ui/jobs/{ui_second}").json()["status"] in ("queued", "processing")
    for job_id in (ui_first, ui_second):
        assert wait_for(client, job_id, ui=True)["status"] == "done"
    first_done = client.get(f"/ui/jobs/{ui_first}").json()["timings"]["total_sec"]
    jury_done = client.get(f"/ui/jobs/{jury}").json()["timings"]["total_sec"]
    second_done = client.get(f"/ui/jobs/{ui_second}").json()["timings"]["total_sec"]
    assert jury_done < second_done and first_done < second_done


@needs_ffmpeg
def test_ui_active_job_cap(make_client, videos):
    client = make_client(ui_max_active=1, dummy_delay_sec=5)
    assert upload(client, videos["h264"], url="/ui/analyze", headers={}).status_code == 200
    resp = upload(client, videos["h264"], url="/ui/analyze", headers={})
    assert resp.status_code == 503 and resp.json()["code"] == "queue_full"
    assert upload(client, videos["h264"]).status_code == 200  # API unaffected


def test_expired_queued_jobs_are_failed(make_settings):
    settings = make_settings(job_timeout_sec=10)
    store = JobStore(settings.db_path)
    now = time.time()
    store.create("aaaaaaaaaaaaaaaa", created_at=now - 11, video_meta={})
    store.create("bbbbbbbbbbbbbbbb", created_at=now - 1, video_meta={})
    assert expire_queued(settings, store, now=now) == ["aaaaaaaaaaaaaaaa"]
    expired = store.get("aaaaaaaaaaaaaaaa")
    assert expired.status == "failed" and expired.error == "timeout"
    assert store.get("bbbbbbbbbbbbbbbb").status == "queued"
    assert not store.claim("aaaaaaaaaaaaaaaa", now)  # the worker will skip it
    assert store.claim("bbbbbbbbbbbbbbbb", now)
    store.close()


def test_closed_analyzer_refuses_to_restart():
    analyzer = AnalyzerProcess("app.analysis.dummy:DummyAnalyzer", {"delay_sec": 0})
    analyzer.close()
    with pytest.raises(AnalyzerError):
        analyzer.start()
    assert not analyzer.is_alive()
