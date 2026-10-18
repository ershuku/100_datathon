"""Evidence frames: exact-timestamp extraction and size-capped JPEG encoding."""

from __future__ import annotations

import base64
import io
import secrets
import subprocess
import time
from pathlib import Path

from PIL import Image

from app.media.probe import SAFE_INPUT_ARGS, MediaError

EXTRACT_TIMEOUT_SEC = 20
BATCH_SIZE = 10
MIN_QUALITY = 40
QUALITY_STEP = 10
SHRINK_FACTOR = 0.8


def clamp_timestamp(t: float, duration_sec: float, fps: float) -> float:
    """Keep t inside the decodable range: [0, duration - one frame]."""
    last = max(0.0, duration_sec - (1.0 / fps if fps > 0 else 0.05))
    return min(max(0.0, t), last)


def extract_frame_png(ffmpeg_bin: str, video: Path, t: float) -> bytes:
    """Decode the first frame at or after t (ffmpeg seeks accurately when transcoding)."""
    cmd = [
        ffmpeg_bin, "-nostdin", "-hide_banner", "-v", "error",
        "-ss", f"{t:.3f}", *SAFE_INPUT_ARGS, "-i", str(video),
        "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=EXTRACT_TIMEOUT_SEC, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("frame_extract_timeout", "Evidence frame extraction timed out") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise MediaError("frame_extract_failed", "Evidence frame could not be extracted")
    return proc.stdout


def extract_frames_png(
    ffmpeg_bin: str, video: Path, timestamps: list[float], out_dir: Path, *, deadline: float | None = None
) -> dict[float, bytes]:
    """Batch version: one ffmpeg process per BATCH_SIZE timestamps (process start-up dominates).

    Missing entries in the result mean that frame could not be decoded (or the monotonic deadline
    was reached); callers decide what to do.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[float, bytes] = {}
    unique = sorted(set(timestamps))
    for start in range(0, len(unique), BATCH_SIZE):
        chunk = unique[start : start + BATCH_SIZE]
        timeout = EXTRACT_TIMEOUT_SEC if deadline is None else min(EXTRACT_TIMEOUT_SEC, deadline - time.monotonic())
        if timeout <= 0:
            break
        cmd = [ffmpeg_bin, "-nostdin", "-hide_banner", "-v", "error", "-y"]
        for t in chunk:
            cmd += ["-ss", f"{t:.3f}", *SAFE_INPUT_ARGS, "-i", str(video)]
        targets = [out_dir / f"ev_{start + i:03d}_{secrets.token_hex(3)}.png" for i in range(len(chunk))]
        for i, target in enumerate(targets):
            cmd += ["-map", f"{i}:v:0", "-frames:v", "1", "-c:v", "png", str(target)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            for target in targets:  # half-written files from the killed batch
                target.unlink(missing_ok=True)
            continue
        for t, target in zip(chunk, targets, strict=True):
            if target.exists() and target.stat().st_size > 0:
                result[t] = target.read_bytes()
                target.unlink()
    return result


def jpeg_from_png(png: bytes, *, max_side: int, quality: int, max_bytes: int) -> bytes:
    try:
        with Image.open(io.BytesIO(png)) as img:
            return encode_jpeg(img, max_side=max_side, quality=quality, max_bytes=max_bytes)
    except (OSError, ValueError) as exc:
        raise MediaError("frame_extract_failed", "Evidence frame could not be decoded") from exc


def encode_jpeg(image: Image.Image, *, max_side: int, quality: int, max_bytes: int) -> bytes:
    """Resize to max_side on the long edge and encode under max_bytes, lowering quality, then size."""
    img = image.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    while True:
        q = quality
        while True:  # always at least one attempt, even if quality < MIN_QUALITY
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            if buf.tell() <= max_bytes or q <= MIN_QUALITY:
                break
            q = max(MIN_QUALITY, q - QUALITY_STEP)
        if buf.tell() <= max_bytes:
            return buf.getvalue()
        new_size = (max(1, int(img.width * SHRINK_FACTOR)), max(1, int(img.height * SHRINK_FACTOR)))
        if new_size == img.size:
            return buf.getvalue()
        img = img.resize(new_size, Image.Resampling.LANCZOS)


def jpeg_from_video(
    ffmpeg_bin: str, video: Path, t: float, *, max_side: int, quality: int, max_bytes: int
) -> bytes:
    png = extract_frame_png(ffmpeg_bin, video, t)
    return jpeg_from_png(png, max_side=max_side, quality=quality, max_bytes=max_bytes)


def jpeg_from_file(path: Path, *, max_side: int, quality: int, max_bytes: int) -> bytes:
    try:
        with Image.open(path) as img:
            return encode_jpeg(img, max_side=max_side, quality=quality, max_bytes=max_bytes)
    except (OSError, ValueError) as exc:
        raise MediaError("frame_read_failed", "Evidence frame from the analyzer could not be read") from exc


def to_base64(data: bytes) -> str:
    """Plain base64, no data: prefix (required by the public API)."""
    return base64.b64encode(data).decode("ascii")
