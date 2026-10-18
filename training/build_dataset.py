"""Merge corrected CVAT COCO exports into the RF-DETR dataset layout.

    python training/build_dataset.py --frames datasets/frames \
        --coco exports/aibar.json exports/baga.json --out datasets/rfdetr [--holdout-pov behind]

Output: <out>/{train,valid,test}/ with images and _annotations.coco.json. test holds the fixed
held-out groups from splits.TEST_GROUPS (RF-DETR only reports on it; it never steers training);
the jury videos are never used here. Categories are remapped by *name* to training/classes.py, so
exports from different CVAT tasks with different id orders merge safely.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from classes import CATEGORY_ID, coco_categories
from splits import DUPLICATE_OF, is_duplicate, norm_video_id, split_of


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--coco", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout-pov", choices=["front", "behind"], default=None)
    ap.add_argument("--extra", type=Path, nargs="*", default=[],
                    help="dirs with _annotations.coco.json + images/ (e.g. openimages.py output); "
                         "train split only, validation stays on our own footage")
    args = ap.parse_args()

    splits = {s: {"images": [], "annotations": [], "categories": coco_categories()}
              for s in ("train", "valid", "test")}
    seen: set[str] = set()
    unknown: Counter[str] = Counter()
    per_class: dict[str, Counter[str]] = {s: Counter() for s in splits}
    source: dict[str, Path] = {}  # file name -> image path to copy
    skipped_dup = 0

    sources = [(p, args.frames / "images", False) for p in args.coco]
    sources += [(d / "_annotations.coco.json", d / "images", True) for d in args.extra]
    for path, img_root, is_extra in sources:
        data = json.loads(path.read_text(encoding="utf-8"))
        id2name = {c["id"]: c["name"] for c in data["categories"]}
        anns_by_img: dict[int, list] = {}
        for a in data["annotations"]:
            anns_by_img.setdefault(a["image_id"], []).append(a)
        for img in data["images"]:
            fname = Path(img["file_name"]).name
            if fname in seen:
                print(f"skip duplicate frame {fname} from {path.name}")
                continue
            if not is_extra and is_duplicate(norm_video_id(fname.split("_t")[0])):
                skipped_dup += 1
                continue
            seen.add(fname)
            source[fname] = img_root / fname
            split = "train" if is_extra else split_of(norm_video_id(fname.split("_t")[0]), args.holdout_pov)
            out = splits[split]
            new_id = len(out["images"]) + 1
            out["images"].append({"id": new_id, "file_name": fname,
                                  "width": img["width"], "height": img["height"]})
            for a in anns_by_img.get(img["id"], []):
                name = id2name[a["category_id"]]
                if name not in CATEGORY_ID:
                    unknown[name] += 1
                    continue
                x, y, w, h = a["bbox"]
                if w < 2 or h < 2:
                    continue
                out["annotations"].append({
                    "id": len(out["annotations"]) + 1, "image_id": new_id,
                    "category_id": CATEGORY_ID[name], "bbox": [x, y, w, h],
                    "area": w * h, "iscrowd": 0})
                per_class[split][name] += 1

    for split, data in splits.items():
        d = args.out / split
        d.mkdir(parents=True, exist_ok=True)
        for img in data["images"]:
            shutil.copy2(source[img["file_name"]], d / img["file_name"])
        (d / "_annotations.coco.json").write_text(json.dumps(data), encoding="utf-8")

    print(f"{'class':16} {'train':>6} {'valid':>6} {'test':>6}")
    for name in CATEGORY_ID:
        print(f"{name:16} {per_class['train'][name]:6} {per_class['valid'][name]:6} {per_class['test'][name]:6}")
    print("images: " + ", ".join(f"{s} {len(d['images'])}" for s, d in splits.items()))
    missing = [n for n in CATEGORY_ID if per_class["train"][n] == 0]
    if missing:
        print(f"WARNING: no train boxes for {missing} - RF-DETR drops unannotated classes")
    if unknown:
        print(f"WARNING: ignored unknown CVAT labels {dict(unknown)}")
    if skipped_dup:
        print(f"skipped {skipped_dup} frames of duplicate videos {sorted(DUPLICATE_OF)}")


if __name__ == "__main__":
    main()
