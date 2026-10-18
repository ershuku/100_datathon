"""Shared fixtures. All test videos are synthetic (ffmpeg lavfi) — never dataset footage."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

KEY = "test-key-one-0123456789"
KEY_TWO = "test-key-two-0123456789"
API_KEYS = f"{KEY},{KEY_TWO}"
REPO = Path(__file__).resolve().parents[1]


def _bin(name: str) -> str | None:
    return os.environ.get(f"{name.upper()}_BIN") or shutil.which(name)


FFMPEG, FFPROBE = _bin("ffmpeg"), _bin("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not available")


def _ff(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-y", *args], check=True, timeout=120)


@pytest.fixture(scope="session")
def videos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    if not (FFMPEG and FFPROBE):
        pytest.skip("ffmpeg/ffprobe not available")
    d = tmp_path_factory.mktemp("videos")
    v = {
        "h264": d / "h264.mov",
        "hevc": d / "hevc_plain.mov",
        "hevc_rot": d / "hevc_rot.mov",
        "colors": d / "colors.mov",
        "avi_as_mov": d / "avi_as_mov.mov",
        "text_as_mov": d / "text.mov",
        "mp4": d / "clip.mp4",
    }
    src = ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4"]
    _ff(*src, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "mov", str(v["h264"]))
    _ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4", "-c:v", "libx265",
        "-x265-params", "log-level=error", "-tag:v", "hvc1", "-f", "mov", str(v["hevc"]))  # fmt: skip
    _ff("-display_rotation", "90", "-i", str(v["hevc"]), "-c", "copy", "-f", "mov", str(v["hevc_rot"]))
    # 0-2 s pure red, 2-4 s pure blue: lets tests check exact-timestamp extraction.
    _ff("-f", "lavfi", "-i", "color=c=red:size=320x240:rate=30:duration=2",
        "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=30:duration=2",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "mov", str(v["colors"]))  # fmt: skip
    _ff(*src, "-c:v", "mpeg4", "-f", "avi", str(v["avi_as_mov"]))
    v["text_as_mov"].write_text("this is not a video", encoding="utf-8")
    v["truncated"] = d / "truncated.mov"
    v["truncated"].write_bytes(v["h264"].read_bytes()[:2048])  # real QuickTime header, no media
    _ff(*src, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "mp4", str(v["mp4"]))
    return v


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "api_key": API_KEYS,
            "data_dir": tmp_path / "data",
            "static_dir": tmp_path / "no-static",
            "rules_path": REPO / "config" / "rules_legal.yaml",
            "ffmpeg_bin": FFMPEG or "ffmpeg",
            "ffprobe_bin": FFPROBE or "ffprobe",
            "dummy_delay_sec": 0.5,
            "dummy_scenario": "violations",
            "janitor_interval_sec": 3600,
            "evidence_reserve_sec": 1.0,
            "video_preset": "ultrafast",
            "ui_upload_per_min": 1000,
            "ui_poll_per_min": 10_000,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def make_client(make_settings: Callable[..., Settings]) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def factory(**overrides: object) -> TestClient:
        client = TestClient(create_app(make_settings(**overrides)))
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def auth(key: str = KEY) -> dict[str, str]:
    return {"X-API-Key": key}


def upload(client: TestClient, path: Path, *, url: str = "/api/v1/analyze", name: str | None = None,
           headers: dict[str, str] | None = None):  # fmt: skip
    with path.open("rb") as fh:
        files = {"file": (name or path.name, fh, "video/quicktime")}
        return client.post(url, files=files, headers=auth() if headers is None else headers)


def wait_for(client: TestClient, job_id: str, *, ui: bool = False, timeout: float = 60.0,
             until: tuple[str, ...] = ("done", "failed")) -> dict:  # fmt: skip
    url = f"/ui/jobs/{job_id}" if ui else f"/api/v1/jobs/{job_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(url, headers=None if ui else auth()).json()
        if body["status"] in until:
            return body
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not reach {until} in {timeout}s: {body}")
