"""Normalize an uploaded .mov into a browser-playable, rotation-applied H.264 .mp4.

The output keeps the original frame timing (-fps_mode passthrough) and starts at t=0, which is
the first frame of the source. Every timecode in the service refers to that timeline.
The same file feeds the evidence extractor and the browser preview, and is the analyzer's default
input; it is downscaled to NORMALIZE_MAX_SIDE (evidence is capped at 1280 px anyway). The analyzer
also gets the untouched original via JobContext.source_path if it needs full resolution.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from app.media.probe import SAFE_INPUT_ARGS, MediaError

EVEN_DIMENSIONS = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
# Guard: the output timeline starts exactly at the first video frame even if the container start
# time is offset (e.g. audio starting earlier). Relative frame timing is preserved.
ZERO_START = "setpts=PTS-STARTPTS"


def _size_filters(max_side: int) -> str:
    """Fit the long side into max_side (never upscale), keep even dimensions. 0 = keep size."""
    if max_side <= 0:
        return EVEN_DIMENSIONS
    m = int(max_side)
    return f"scale='if(gte(iw,ih),min({m},iw),-2)':'if(gte(iw,ih),-2,min({m},ih))',{EVEN_DIMENSIONS}"


def scale_filter(max_side: int) -> str:
    return f"{ZERO_START},{_size_filters(max_side)}"


def _encoder_args(encoder: str, preset: str, crf: int) -> list[str]:
    if "nvenc" in encoder:
        return ["-c:v", encoder, "-preset", "p4", "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    return ["-c:v", encoder, "-preset", preset, "-crf", str(crf)]


def build_normalize_cmd(
    ffmpeg_bin: str,
    src: Path,
    dst: Path,
    *,
    encoder: str,
    preset: str,
    crf: int,
    max_side: int = 0,
    frames_dir: Path | None = None,
    frames_fps: float = 0.0,
) -> list[str]:
    # ffmpeg applies the rotation side data by default (autorotate) and drops it from the output.
    cmd = [ffmpeg_bin, "-nostdin", "-hide_banner", "-v", "error", "-y", "-progress", "pipe:1", *SAFE_INPUT_ARGS, "-i", str(src)]
    cmd += ["-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-fps_mode", "passthrough"]
    cmd += ["-vf", scale_filter(max_side), "-pix_fmt", "yuv420p", *_encoder_args(encoder, preset, crf)]
    cmd += ["-movflags", "+faststart", str(dst)]
    if frames_dir is not None and frames_fps > 0:
        # Frame N (1-based file index) is at t = (N - 1) / frames_fps on the normalized timeline.
        frames_filter = f"{ZERO_START},fps={frames_fps},{_size_filters(max_side)}"
        cmd += ["-map", "0:v:0", "-vf", frames_filter, "-q:v", "3", str(frames_dir / "%06d.jpg")]
    return cmd


def normalize_video(
    ffmpeg_bin: str,
    src: Path,
    dst: Path,
    *,
    duration_sec: float,
    timeout_sec: float,
    encoder: str = "libx264",
    preset: str = "veryfast",
    crf: int = 23,
    max_side: int = 1280,
    frames_dir: Path | None = None,
    frames_fps: float = 0.0,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Transcode src -> dst. Raises MediaError on failure, TimeoutError past timeout_sec."""
    if frames_dir is not None and frames_fps > 0:
        frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_normalize_cmd(
        ffmpeg_bin, src, dst, encoder=encoder, preset=preset, crf=crf, max_side=max_side,
        frames_dir=frames_dir, frames_fps=frames_fps,
    )
    if timeout_sec <= 0:
        raise TimeoutError("no time left for normalization")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    timed_out = threading.Event()

    def _kill() -> None:  # watchdog: fires even if ffmpeg stops printing progress
        timed_out.set()
        proc.kill()

    watchdog = threading.Timer(timeout_sec, _kill)
    watchdog.daemon = True
    watchdog.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and on_progress and duration_sec > 0 and value.isdigit():
                on_progress(min(1.0, int(value) / 1_000_000 / duration_sec))
        proc.wait()
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if timed_out.is_set() or proc.returncode != 0:
        dst.unlink(missing_ok=True)  # never leave a truncated file that could look like a result
    if timed_out.is_set():
        raise TimeoutError("normalization exceeded its time budget")
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise MediaError("transcode_failed", "Video could not be decoded")
