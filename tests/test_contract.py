"""Validates real public responses against schemas/job_response.schema.json (the jury contract)."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from conftest import REPO, auth, needs_ffmpeg, upload, wait_for

pytestmark = needs_ffmpeg

SCHEMA = json.loads((REPO / "schemas" / "job_response.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def _assert_valid(body: dict) -> None:
    errors = sorted(VALIDATOR.iter_errors(body), key=str)
    assert not errors, [e.message for e in errors]


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("scenario", ["violations", "none", "crash"])
def test_every_status_matches_schema(make_client, videos, scenario):
    client = make_client(dummy_scenario=scenario, dummy_delay_sec=1)
    job_id = upload(client, videos["h264"]).json()["job_id"]
    _assert_valid(client.get(f"/api/v1/jobs/{job_id}", headers=auth()).json())  # processing
    _assert_valid(wait_for(client, job_id))


@pytest.mark.parametrize(
    "bad",
    [
        {"job_id": "x", "status": "processing", "progress": 5},
        {"job_id": "x", "status": "done", "verdict": "no_violation", "violations": [{}]},
        {"job_id": "x", "status": "done", "verdict": "violation", "violations": []},
        {"job_id": "x", "status": "done", "verdict": "maybe", "violations": []},
        {"job_id": "x", "status": "done", "verdict": "violation", "violations": [
            {"type": "t", "timecode_sec": 1.0, "description": "d",
             "evidence_frames": [{"timestamp_sec": 1.0, "image_base64": "data:image/jpeg;base64,/9j/AA"}]}]},
    ],
)  # fmt: skip
def test_schema_rejects_contract_breaks(bad):
    assert list(VALIDATOR.iter_errors(bad))
