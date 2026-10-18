from __future__ import annotations

import pytest

from app.media.normalize import normalize_video
from app.media.probe import MediaError, probe_video
from conftest import FFMPEG, FFPROBE, _ff, needs_ffmpeg

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def big_video(tmp_path_factory) -> object:
    path = tmp_path_factory.mktemp("big") / "big.mov"
    _ff("-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=3", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-f", "mov", str(path))  # fmt: skip
    return path


def _norm(src, dst, **kw):
    info = probe_video(FFPROBE, src)
    normalize_video(FFMPEG, src, dst, duration_sec=info.duration_sec, timeout_sec=kw.pop("timeout_sec", 60),
                    preset="ultrafast", **kw)  # fmt: skip
    return probe_video(FFPROBE, dst)


def test_downscales_long_side_and_keeps_timeline(big_video, tmp_path):
    out = _norm(big_video, tmp_path / "n.mp4", max_side=1280)
    assert (out.width, out.height) == (1280, 720)
    assert abs(out.duration_sec - 3.0) < 0.1 and out.rotation == 0


def test_never_upscales(videos, tmp_path):
    out = _norm(videos["h264"], tmp_path / "n.mp4", max_side=1280)
    assert (out.width, out.height) == (640, 360)


def test_rotation_applied_and_metadata_dropped(videos, tmp_path):
    out = _norm(videos["hevc_rot"], tmp_path / "n.mp4", max_side=1280)
    assert (out.width, out.height) == (720, 1280) and out.rotation == 0 and out.codec == "h264"


def test_progress_reported(videos, tmp_path):
    seen: list[float] = []
    _norm(videos["h264"], tmp_path / "n.mp4", on_progress=seen.append)
    assert seen and max(seen) <= 1.0


def test_watchdog_kills_slow_normalization(big_video, tmp_path):
    with pytest.raises(TimeoutError):
        _norm(big_video, tmp_path / "n.mp4", max_side=0, timeout_sec=0.05)


def test_corrupt_input_is_media_error(videos, tmp_path):
    broken = tmp_path / "broken.mov"
    broken.write_bytes(videos["h264"].read_bytes()[:4096])
    with pytest.raises(MediaError):
        info = probe_video(FFPROBE, broken)
        normalize_video(FFMPEG, broken, tmp_path / "n.mp4", duration_sec=info.duration_sec, timeout_sec=30)
