"""Draw pre-label boxes on a few frames per video, for a quick visual check.

    python training/draw_prelabels.py --frames datasets/frames --prelabels datasets/frames/prelabels_smooth_v4.coco.json \
        --videos X-30,X-31,X-32 --classes safe_open,safe_closed,door_open,door_closed --n 8 --out runs/prelabel_check/v4
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

COLORS = {"safe_open": (0, 0, 255), "safe_closed": (0, 200, 0), "door_open": (0, 140, 255),
          "door_closed": (255, 120, 0), "laptop_open": (200, 0, 200), "laptop_closed": (120, 0, 120)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--prelabels", type=Path, required=True)
    ap.add_argument("--videos", required=True)
    ap.add_argument("--classes", default="", help="comma-separated; empty = all")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    coco = json.loads(args.prelabels.read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in coco["categories"]}
    want = {c for c in args.classes.split(",") if c}
    by_img = defaultdict(list)
    for a in coco["annotations"]:
        if not want or names[a["category_id"]] in want:
            by_img[a["image_id"]].append(a)
    for video in args.videos.split(","):
        imgs = sorted((im for im in coco["images"] if im["file_name"].startswith(video + "_t")),
                      key=lambda im: im["file_name"])
        if not imgs:
            print(f"{video}: no frames")
            continue
        out = args.out / video
        out.mkdir(parents=True, exist_ok=True)
        for i in np.linspace(0, len(imgs) - 1, min(args.n, len(imgs))).astype(int):
            im = imgs[i]
            img = cv2.imread(str(args.frames / "images" / im["file_name"]))
            for a in by_img.get(im["id"], []):
                x, y, w, h = map(int, a["bbox"])
                name = names[a["category_id"]]
                color = COLORS.get(name, (255, 255, 255))
                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                cv2.putText(img, name, (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            cv2.imwrite(str(out / im["file_name"]), img)
        print(f"{video}: {min(args.n, len(imgs))} frames -> {out}")


if __name__ == "__main__":
    main()
