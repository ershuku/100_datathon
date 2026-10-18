"""Generate a synthetic .mov (ffmpeg test pattern) for manual testing. Never use dataset footage here.

    uv run python scripts/make_test_video.py out.mov --duration 30 --hevc --rotate 90
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--size", default="1920x1080")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--hevc", action="store_true", help="encode HEVC like iPhone footage")
    parser.add_argument("--rotate", type=int, default=0, help="display rotation metadata, e.g. 90")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found (set FFMPEG_BIN)", file=sys.stderr)
        return 1
    codec = ["-c:v", "libx265", "-tag:v", "hvc1", "-x265-params", "log-level=error"] if args.hevc else [
        "-c:v", "libx264", "-pix_fmt", "yuv420p"]  # fmt: skip
    src = ["-f", "lavfi", "-i", f"testsrc2=size={args.size}:rate={args.fps}:duration={args.duration}"]
    base = [ffmpeg, "-hide_banner", "-v", "error", "-y"]
    if not args.rotate:
        subprocess.run([*base, *src, *codec, "-f", "mov", str(args.output)], check=True)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain.mov"
            subprocess.run([*base, *src, *codec, "-f", "mov", str(plain)], check=True)
            subprocess.run([*base, "-display_rotation", str(args.rotate), "-i", str(plain), "-c", "copy",
                            "-f", "mov", str(args.output)], check=True)  # fmt: skip
    print(f"wrote {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
