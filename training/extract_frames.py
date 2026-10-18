"""Sample frames from the dataset videos for annotation.

    python training/extract_frames.py --videos ../open/videos --out datasets/frames --fps 2

Writes <out>/images/X-12_t012.50.jpg and <out>/manifest.csv (video, t_sec, file, pov, split).
Near-duplicate consecutive frames (static scene) are dropped so annotators don't label the same
picture twenty times.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

import cv2
import numpy as np

from splits import DUPLICATE_OF, POV, norm_video_id, split_of


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def thumb(frame: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (48, 88), interpolation=cv2.INTER_AREA).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--dedup", type=float, default=1.0,
                    help="mean abs pixel diff (0-255) on a thumbnail below which a frame is a duplicate")
    ap.add_argument("--only", default="", help="comma-separated video ids, e.g. X-1,X-2")
    args = ap.parse_args()

    only = {norm_video_id(v) for v in args.only.split(",") if v.strip()}
    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    seen_sha: dict[str, str] = {}
    for path in sorted(args.videos.glob("*.mov"), key=lambda p: int(norm_video_id(p.stem)[2:])):
        vid = norm_video_id(path.stem)
        if only and vid not in only:
            continue
        # Identical files would put the same frames in two places (and possibly two splits).
        sha = file_sha256(path)
        if vid in DUPLICATE_OF or sha in seen_sha:
            print(f"{vid}: skipped, byte-identical to {DUPLICATE_OF.get(vid) or seen_sha[sha]}")
            if vid not in DUPLICATE_OF:
                print(f"  WARNING: add '{vid}': '{seen_sha[sha]}' to splits.DUPLICATE_OF")
            continue
        seen_sha[sha] = vid
        cap = cv2.VideoCapture(str(path))
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(src_fps / args.fps))
        idx, kept, last = 0, 0, None
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                t = thumb(frame)
                if last is None or float(np.abs(t - last).mean()) >= args.dedup:
                    t_sec = idx / src_fps
                    name = f"{vid}_t{t_sec:06.2f}.jpg"
                    cv2.imwrite(str(img_dir / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    rows.append({"video": vid, "t_sec": f"{t_sec:.2f}", "file": name,
                                 "pov": POV.get(vid, "unknown"), "split": split_of(vid)})
                    last, kept = t, kept + 1
            idx += 1
        cap.release()
        print(f"{vid}: {idx} frames read, {kept} kept")

    with open(args.out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["video", "t_sec", "file", "pov", "split"])
        w.writeheader()
        w.writerows(rows)
    n_val = sum(r["split"] == "valid" for r in rows)
    print(f"total {len(rows)} frames ({len(rows) - n_val} train / {n_val} valid) -> {img_dir}")


if __name__ == "__main__":
    main()
