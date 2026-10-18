"""Compare two pre-label versions, and score both against human-made boxes from CVAT.

    python training/compare_prelabels.py --a datasets/frames/prelabels_smooth.coco.json \
        --b datasets/frames/prelabels_smooth_v2.coco.json [--cvat-manual]

--cvat-manual pulls every box a person drew or edited in CVAT (source != "file") and reports,
per version, how many of those boxes the version already had (same class, IoU >= 0.5). That is
the only human-checked signal until the corrected exports exist, so treat small counts as anecdotes.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load(path: Path) -> tuple[dict[str, list[tuple[str, list[float]]]], Counter, Counter]:
    coco = json.loads(path.read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in coco["categories"]}
    files = {im["id"]: im["file_name"] for im in coco["images"]}
    by_file: dict[str, list] = defaultdict(list)
    boxes, frames = Counter(), defaultdict(set)
    for a in coco["annotations"]:
        cls = names[a["category_id"]]
        x, y, w, h = a["bbox"]
        by_file[files[a["image_id"]]].append((cls, [x, y, x + w, y + h]))
        boxes[cls] += 1
        frames[cls].add(a["image_id"])
    return by_file, boxes, Counter({k: len(v) for k, v in frames.items()})


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def cvat_manual() -> list[tuple[str, str, list[float]]]:
    from cvat_sdk import make_client
    pw = (Path.home() / ".cvat_admin").read_text().strip()
    out = []
    with make_client("http://localhost:8080", credentials=("admin", pw)) as c:
        for t in c.tasks.list():
            labels = {lab.id: lab.name for lab in t.get_labels()}
            frames = [f.name for f in t.get_frames_info()]
            for s in t.get_annotations().shapes:
                if s.source != "file" and s.type.value == "rectangle":
                    out.append((Path(frames[s.frame]).name, labels[s.label_id], list(s.points)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--cvat-manual", action="store_true")
    args = ap.parse_args()

    fa, ba, ra = load(args.a)
    fb, bb, rb = load(args.b)
    print(f"{'class':16} {'A boxes':>8} {'B boxes':>8} {'A frames':>9} {'B frames':>9}")
    for cls in sorted(set(ba) | set(bb)):
        print(f"{cls:16} {ba[cls]:8} {bb[cls]:8} {ra[cls]:9} {rb[cls]:9}")

    if args.cvat_manual:
        gt = cvat_manual()
        print(f"\n{len(gt)} human-made boxes in CVAT; matched by version (same class, IoU>=0.5):")
        hit = {"A": Counter(), "B": Counter()}
        total = Counter()
        for fname, cls, box in gt:
            total[cls] += 1
            for tag, f in (("A", fa), ("B", fb)):
                if any(c == cls and iou(box, b) >= 0.5 for c, b in f.get(fname, [])):
                    hit[tag][cls] += 1
        for cls in sorted(total):
            print(f"  {cls:16} {total[cls]:3} human  A {hit['A'][cls]:3}  B {hit['B'][cls]:3}")
        print(f"  {'all':16} {sum(total.values()):3} human  A {sum(hit['A'].values()):3}  "
              f"B {sum(hit['B'].values()):3}")


if __name__ == "__main__":
    main()
