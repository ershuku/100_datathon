"""ffprobe wrapper: real duration, fps, rotation and container checks."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

PROBE_TIMEOUT_SEC = 30
QUICKTIME_DEMUXER = "mov"  # ffprobe reports "mov,mp4,m4a,3gp,3g2,mj2" for the QuickTime family
# Put before every -i on untrusted media: force the QuickTime demuxer (no playlists/concat lists
# disguised as .mov) and allow only local files and pipes (no network protocols).
SAFE_INPUT_ARGS = ("-f", QUICKTIME_DEMUXER, "-protocol_whitelist", "file,pipe")
# QuickTime/ISO-BMFF top-level atoms that may start a file; anything else is not a .mov.
_QT_ATOMS = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot", b"uuid"}


class MediaError(Exception):
    """A user-facing media problem. `code` is stable and mapped to text by the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VideoInfo:
    duration_sec: float
    fps: float
    width: int
    height: int
    codec: str
    rotation: int
    start_time_sec: float
    format_name: str
    major_brand: str

    @property
    def display_size(self) -> tuple[int, int]:
        if self.rotation % 180:
            return self.height, self.width
        return self.width, self.height

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_rate(value: str | None) -> float:
    if not value or value in ("0/0", "0"):
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _rotation(stream: dict) -> int:
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            return int(round(float(side["rotation"]))) % 360
    tag = (stream.get("tags") or {}).get("rotate")
    return int(tag) % 360 if tag else 0


def looks_like_quicktime(path: Path) -> bool:
    with path.open("rb") as fh:
        header = fh.read(12)
    return len(header) >= 8 and header[4:8] in _QT_ATOMS


def _run_ffprobe(ffprobe_bin: str, path: Path) -> dict:
    cmd = [ffprobe_bin, "-v", "error", *SAFE_INPUT_ARGS, "-print_format", "json", "-show_format",
           "-show_streams", "-i", str(path)]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_SEC, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("probe_timeout", "Video could not be read in time") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"ffprobe not found: {ffprobe_bin}") from exc
    if proc.returncode != 0:
        raise MediaError("unreadable_video", "File is not a readable video")
    try:
        return json.loads(proc.stdout or b"{}")
    except json.JSONDecodeError as exc:
        raise MediaError("unreadable_video", "File is not a readable video") from exc


def probe_video(ffprobe_bin: str, path: Path, *, max_side_px: int = 0, max_fps: float = 0.0) -> VideoInfo:
    if not looks_like_quicktime(path):
        raise MediaError("unsupported_container", "Only QuickTime .mov files are accepted")
    data = _run_ffprobe(ffprobe_bin, path)
    fmt = data.get("format") or {}
    format_name = fmt.get("format_name", "")
    if QUICKTIME_DEMUXER not in format_name.split(","):
        raise MediaError("unsupported_container", "Only QuickTime .mov files are accepted")

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("no_video_stream", "File contains no video stream")

    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    fps = _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate"))
    if duration <= 0 or fps <= 0:
        raise MediaError("unreadable_video", "Video duration or frame rate could not be determined")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if max_side_px and (max(width, height) > max_side_px or min(width, height) <= 0):
        raise MediaError("unsupported_resolution", f"Video resolution must be at most {max_side_px} px per side")
    if max_fps and fps > max_fps:
        raise MediaError("unsupported_frame_rate", f"Frame rate must be at most {max_fps:g} fps")

    return VideoInfo(
        duration_sec=duration,
        fps=fps,
        width=width,
        height=height,
        codec=str(video.get("codec_name", "")),
        rotation=_rotation(video),
        start_time_sec=float(fmt.get("start_time") or 0.0),
        format_name=format_name,
        major_brand=str((fmt.get("tags") or {}).get("major_brand", "")).strip(),
    )
