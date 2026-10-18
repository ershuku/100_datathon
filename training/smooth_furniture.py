"""Temporal smoothing of furniture pre-labels: the camera is fixed, so furniture doesn't move and
its state changes rarely.

    python training/smooth_furniture.py --frames datasets/frames \
        --prelabels datasets/frames/prelabels_refined.coco.json --out datasets/frames/prelabels_smooth.coco.json

Per video and furniture family (safe, laptop, door, counter, uv): the state in each frame is the
weighted majority within +-window seconds (weight = open-vs-closed margin for two-state
families, reference similarity otherwise), and the box is that state's median box over
the video (one stable rectangle instead of jitter). Frames where a family was missed get filled
when it was seen within the window. Other classes pass through unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict

from pathlib import Path

import numpy as np

from refine_prelabels import FAMILY


def iou_xywh(a: list[float], b: list[float]) -> float:
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax1, bx1) - max(a[0], b[0]))
    iy = max(0.0, min(ay1, by1) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def dominant_location(items: list[tuple], min_iou: float = 0.4) -> tuple[list[tuple], float]:
    """Keep the boxes at the one place the object really is (the camera is fixed).

    Per class, boxes are grouped greedily by overlap with a group's strongest box; the group with
    the largest summed reference similarity wins. Frames where some other object out-scored the
    real safe/door fall in a losing group and are dropped instead of dragging the median box onto
    the wrong object. Done per class because an open door/safe occupies a different box than a
    closed one. Returns the kept items and the share of items kept.
    """
    kept = []
    for cls in {it[1] for it in items}:
        own = sorted((it for it in items if it[1] == cls), key=lambda it: -it[4])
        groups: list[list[tuple]] = []
        for it in own:
            for g in groups:
                if iou_xywh(it[3], g[0][3]) >= min_iou:
                    g.append(it)
                    break
            else:
                groups.append([it])
        kept.extend(max(groups, key=lambda g: sum(it[4] for it in g)))
    return kept, len(kept) / max(len(items), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--prelabels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--window", type=float, default=1.5, help="seconds either side")
    ap.add_argument("--focus", default="", help="videos to report box locations for, e.g. X-30,X-31")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.frames / "manifest.csv", encoding="utf-8")))
    coco = json.loads(args.prelabels.read_text(encoding="utf-8"))
    id2name = {c["id"]: c["name"] for c in coco["categories"]}
    name2id = {v: k for k, v in id2name.items()}
    file2img = {im["file_name"]: im["id"] for im in coco["images"]}

    # obs[video][family] -> list of (t, class, weight, box xywh)
    obs: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    img_info = {r["file"]: (r["video"], float(r["t_sec"])) for r in rows}
    imgid2file = {v: k for k, v in file2img.items()}
    passthrough = []
    for a in coco["annotations"]:
        name = id2name[a["category_id"]]
        fam = FAMILY.get(name)
        if fam is None:
            passthrough.append(a)
            continue
        video, t = img_info[imgid2file[a["image_id"]]]
        attrs = a.get("attributes", {})
        # Two-state families vote with how clearly a frame was open vs closed (state_margin), so a
        # few decisive frames outvote many coin-flips; one-state families fall back to similarity.
        if fam in ("safe", "laptop", "door") and "state_margin" in attrs:
            w = max(float(attrs["state_margin"]), 0.002)
        else:
            w = float(attrs.get("ref_similarity", 0.6))
        obs[video][fam].append((t, name, w, a["bbox"], float(attrs.get("ref_similarity", 0.6))))

    frames_by_video = defaultdict(list)
    for r in rows:
        frames_by_video[r["video"]].append((float(r["t_sec"]), r["file"]))

    out_anns = list(passthrough)
    changed = filled = 0
    location: dict[str, dict[str, tuple]] = defaultdict(dict)  # video -> family -> (share kept, boxes)
    for video, fams in obs.items():
        for fam, items in fams.items():
            items, share = dominant_location(items)
            med = {}
            for cls in {it[1] for it in items}:
                med[cls] = np.median(np.array([it[3] for it in items if it[1] == cls]), axis=0).round(1).tolist()
            location[video][fam] = (share, med)
            seen_at = {round(it[0], 2): it[1] for it in items}
            for t, fname in frames_by_video[video]:
                near = [(it[1], it[2]) for it in items if abs(it[0] - t) <= args.window]
                if not near:
                    continue
                votes = defaultdict(float)
                for c, w in near:
                    votes[c] += w
                cls = max(votes, key=votes.get)
                orig = seen_at.get(round(t, 2))
                if orig is None:
                    filled += 1
                elif orig != cls:
                    changed += 1
                x, y, bw, bh = med[cls]
                out_anns.append({"id": 0, "image_id": file2img[fname], "category_id": name2id[cls],
                                 "bbox": [x, y, bw, bh], "area": round(bw * bh, 1), "iscrowd": 0})
    for i, a in enumerate(out_anns, 1):
        a["id"] = i
        a.pop("attributes", None)
    args.out.write_text(json.dumps({"images": coco["images"], "annotations": out_anns,
                                    "categories": coco["categories"]}), encoding="utf-8")

    # Per-video state timeline summary: runs of the voted state, for a quick sanity read.
    print(f"state flips smoothed: {changed}, missed frames filled: {filled}")
    per = defaultdict(lambda: defaultdict(list))
    for a in out_anns:
        name = id2name[a["category_id"]]
        fam = FAMILY.get(name)
        if fam in ("safe", "laptop", "door"):
            video, t = img_info[imgid2file[a["image_id"]]]
            per[video][fam].append((t, name.split("_")[-1]))
    for video in sorted(per, key=lambda v: int(v[2:])):
        parts = []
        for fam in ("safe", "laptop", "door"):
            seq = sorted(per[video][fam])
            runs = []
            for t, s in seq:
                if not runs or runs[-1][1] != s:
                    runs.append([t, s])
            parts.append(f"{fam}: " + " -> ".join(f"{s}@{t:.0f}s" for t, s in runs))
        print(f"  {video:5} " + " | ".join(parts))
    for video in [v.strip() for v in args.focus.split(",") if v.strip()]:
        for fam in ("safe", "door", "laptop"):
            if fam in location.get(video, {}):
                share, med = location[video][fam]
                boxes = ", ".join(f"{c} [x{b[0]:.0f} y{b[1]:.0f} w{b[2]:.0f} h{b[3]:.0f}]" for c, b in sorted(med.items()))
                print(f"  location {video:5} {fam:6} {share:.0%} of candidate frames agree -> {boxes}")
    print(f"{len(out_anns)} boxes -> {args.out}")


if __name__ == "__main__":
    main()
