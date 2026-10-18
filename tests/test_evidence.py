from __future__ import annotations

import io
import os

from PIL import Image

from app.media.evidence import clamp_timestamp, encode_jpeg, jpeg_from_video
from app.media.probe import probe_video
from conftest import FFMPEG, FFPROBE, needs_ffmpeg


def test_encode_jpeg_caps_size_and_side():
    noise = Image.frombytes("RGB", (4000, 3000), os.urandom(4000 * 3000 * 3))
    data = encode_jpeg(noise, max_side=1280, quality=85, max_bytes=300_000)
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG" and max(img.size) <= 1280 and len(data) <= 300_000


def test_low_configured_quality_still_encodes():
    noise = Image.frombytes("RGB", (800, 600), os.urandom(800 * 600 * 3))
    data = encode_jpeg(noise, max_side=1280, quality=30, max_bytes=300_000)
    assert data[:2] == bytes([0xFF, 0xD8]) and len(data) <= 300_000


def test_small_image_is_not_upscaled():
    data = encode_jpeg(Image.new("RGB", (320, 240), "white"), max_side=1280, quality=85, max_bytes=300_000)
    assert Image.open(io.BytesIO(data)).size == (320, 240)


def test_clamp_timestamp():
    assert clamp_timestamp(-1, 10, 30) == 0
    assert clamp_timestamp(99, 10, 30) < 10


@needs_ffmpeg
def test_frame_is_taken_at_exact_timestamp(videos):
    opts = {"max_side": 1280, "quality": 85, "max_bytes": 300_000}

    def color_at(t: float) -> tuple[int, int, int]:
        img = Image.open(io.BytesIO(jpeg_from_video(FFMPEG, videos["colors"], t, **opts)))
        return img.convert("RGB").getpixel((img.width // 2, img.height // 2))

    red, blue = color_at(1.9), color_at(2.0)
    assert red[0] > 200 and red[2] < 60
    assert blue[2] > 200 and blue[0] < 60


@needs_ffmpeg
def test_probe_reads_duration_fps_rotation(videos):
    info = probe_video(FFPROBE, videos["hevc_rot"])
    assert abs(info.duration_sec - 4.0) < 0.1
    assert abs(info.fps - 30) < 0.01
    assert info.codec == "hevc"
    assert info.rotation in (90, 270)
    assert info.display_size == (720, 1280)
