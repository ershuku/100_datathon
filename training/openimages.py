"""Pull a small Open Images V7 subset for the classes it shares with ours, as extra train data.

    python training/openimages.py --out datasets/openimages

Open Images boxes are CC BY 4.0 and its images are CC BY 2.0 (commercial use allowed with
attribution); every image's author and licence go to <out>/ATTRIBUTION.csv. Only the validation
and test splits are used (small CSVs, no account or key needed). Open Images has no banknote,
safe, key or ID-card class, and its doors and laptops carry no open/closed state, so only
stateless classes are mapped. Images are resized to <= 848 px like our frames.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from classes import CATEGORY_ID, coco_categories

ANN = "https://storage.googleapis.com/openimages/v5/{split}-annotations-bbox.csv"
META = "https://storage.googleapis.com/openimages/2018_04/{split}/{split}-images-with-rotation.csv"
IMG = "https://s3.amazonaws.com/open-images-dataset/{split}/{id}.jpg"

# Open Images MID -> our class. Laptops are mapped to laptop_open: nearly all OI laptops are open.
MAP = {
    "/m/01g317": "person",
    "/m/01c648": "laptop_open",
    "/m/01lsmm": "scissors",
    "/m/050k8": "personal_item",    # Mobile phone
    "/m/02p5f1q": "personal_item",  # Coffee cup
    "/m/02jvh9": "personal_item",   # Mug
    "/m/032b3c": "personal_item",   # Jacket
    "/m/080hkjn": "personal_item",  # Handbag
}
# Images wanted per class that *drives* selection (person comes along in most images anyway).
QUOTA = {"laptop_open": 300, "scissors": 300, "personal_item": 500, "person": 150}


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-side", type=int, default=848)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    meta_dir = args.out / "meta"

    boxes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    bad: set[tuple[str, str]] = set()
    meta: dict[tuple[str, str], dict] = {}
    for split in ("validation", "test"):
        for r in csv.DictReader(open(fetch(META.format(split=split), meta_dir / f"{split}-meta.csv"),
                                     encoding="utf-8")):
            rot = (r.get("Rotation") or "").strip()
            if "/by/2.0" in r["License"] and rot in ("", "0", "0.0"):
                meta[(split, r["ImageID"])] = r
        for r in csv.DictReader(open(fetch(ANN.format(split=split), meta_dir / f"{split}-bbox.csv"),
                                     encoding="utf-8")):
            key = (split, r["ImageID"])
            cls = MAP.get(r["LabelName"])
            if cls is None:
                continue
            # Group boxes cover a crowd with one rectangle and drawings are off-domain: skip the image.
            if r["IsGroupOf"] == "1" or r["IsDepiction"] == "1":
                bad.add(key)
                continue
            boxes[key].append({"cls": cls, "x0": float(r["XMin"]), "x1": float(r["XMax"]),
                               "y0": float(r["YMin"]), "y1": float(r["YMax"])})

    candidates = [k for k in boxes if k not in bad and k in meta]
    random.Random(args.seed).shuffle(candidates)
    chosen, count = [], defaultdict(int)
    for k in candidates:
        classes = {b["cls"] for b in boxes[k]}
        need = [c for c in classes if count[c] < QUOTA[c]]
        if not need or classes == {"person"} and count["person"] >= QUOTA["person"]:
            continue
        chosen.append(k)
        for c in classes:
            count[c] += 1
    print(f"{len(chosen)} images selected; images per class: {dict(count)}")

    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    def download(k: tuple[str, str]) -> tuple[tuple[str, str], tuple[int, int] | None]:
        split, iid = k
        dest = img_dir / f"oi_{iid}.jpg"
        try:
            if not dest.exists():
                raw = urllib.request.urlopen(IMG.format(split=split, id=iid), timeout=30).read()
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((args.max_side, args.max_side))
                im.save(dest, quality=92)
            with Image.open(dest) as im:
                return k, im.size
        except Exception as e:  # noqa: BLE001 - a few dead links are expected
            print(f"skip {iid}: {e}")
            return k, None

    with ThreadPoolExecutor(16) as pool:
        sizes = dict(pool.map(download, chosen))

    images, annotations = [], []
    with open(args.out / "ATTRIBUTION.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "author", "license", "original_url", "title"])
        for k in chosen:
            if not sizes.get(k):
                continue
            (W, H), (split, iid) = sizes[k], k
            m = meta[k]
            image_id = len(images) + 1
            fname = f"oi_{iid}.jpg"
            images.append({"id": image_id, "file_name": fname, "width": W, "height": H})
            w.writerow([fname, m["Author"], m["License"], m["OriginalURL"], m["Title"]])
            for b in boxes[k]:
                x, y, bw, bh = b["x0"] * W, b["y0"] * H, (b["x1"] - b["x0"]) * W, (b["y1"] - b["y0"]) * H
                if bw < 2 or bh < 2:
                    continue
                annotations.append({"id": len(annotations) + 1, "image_id": image_id,
                                    "category_id": CATEGORY_ID[b["cls"]],
                                    "bbox": [round(x, 1), round(y, 1), round(bw, 1), round(bh, 1)],
                                    "area": round(bw * bh, 1), "iscrowd": 0})
    (args.out / "_annotations.coco.json").write_text(
        json.dumps({"images": images, "annotations": annotations, "categories": coco_categories()}),
        encoding="utf-8")
    print(f"{len(images)} images, {len(annotations)} boxes -> {args.out}")


if __name__ == "__main__":
    main()
