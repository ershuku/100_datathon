"""Zero-shot pre-labels with Grounding DINO (Apache-2.0), exported as COCO for CVAT.

    python training/prelabel.py --frames datasets/frames --out datasets/frames/prelabels.coco.json

Runs locally on the GPU; frames never leave the machine. The output is a starting point only:
every frame still needs a human pass in CVAT (fix boxes, flip open/closed states, add misses).
Use --only X-1,X-2 to make one file per annotator.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import torch
from PIL import Image
from torchvision.ops import batched_nms, box_iou
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

from classes import CATEGORY_ID, MAX_PER_FRAME, PROMPTS, coco_categories
from splits import norm_video_id

MODEL_ID = "IDEA-Research/grounding-dino-base"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True, help="output dir of extract_frames.py")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()

    only = {norm_video_id(v) for v in args.only.split(",") if v.strip()}
    with open(args.frames / "manifest.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if not only or r["video"] in only]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    # Default resize upscales 464x848 frames to ~730x1333; native size is ~2.5x cheaper per pass
    # and loses nothing, since there is no extra detail to upscale into.
    processor.image_processor.size = {"shortest_edge": 464, "longest_edge": 848}
    model = AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_ID).to(device).eval()
    min_thr = min(t for _, t in PROMPTS.values())

    # image index -> list of (box xyxy, score, class name)
    found: dict[int, list] = defaultdict(list)
    sizes: list[tuple[int, int]] = []
    for start in range(0, len(rows), args.batch):
        chunk = rows[start:start + args.batch]
        pil = [Image.open(args.frames / "images" / r["file"]).convert("RGB") for r in chunk]
        sizes.extend(im.size for im in pil)
        targets = [im.size[::-1] for im in pil]
        for prompt, (cls, thr) in PROMPTS.items():
            inputs = processor(images=pil, text=[prompt + "."] * len(pil), return_tensors="pt").to(device)
            with torch.no_grad(), torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
                outputs = model(**inputs)
            outputs.logits, outputs.pred_boxes = outputs.logits.float(), outputs.pred_boxes.float()
            results = processor.post_process_grounded_object_detection(
                outputs, inputs.input_ids, threshold=min_thr, text_threshold=min_thr, target_sizes=targets)
            # One prompt per caption, so every box belongs to this prompt's class.
            for k, res in enumerate(results):
                for box, score in zip(res["boxes"].tolist(), res["scores"].tolist()):
                    if score >= thr:
                        found[start + k].append((box, score, cls))
        print(f"{min(start + args.batch, len(rows))}/{len(rows)} frames", flush=True)

    images, annotations = [], []
    for i, r in enumerate(rows):
        w, h = sizes[i]
        images.append({"id": i + 1, "file_name": r["file"], "width": w, "height": h})
        dets = found.get(i)
        if not dets:
            continue
        b = torch.tensor([d[0] for d in dets])
        s = torch.tensor([d[1] for d in dets])
        c = torch.tensor([CATEGORY_ID[d[2]] for d in dets])
        keep = batched_nms(b, s, c, 0.5)
        # Near-identical boxes with different classes (e.g. the safe also matching "door"):
        # keep the higher-scoring one.
        kb = b[keep]
        iou = box_iou(kb, kb)
        drop = set()
        for a in range(len(keep)):
            for z in range(a + 1, len(keep)):
                if iou[a, z] > 0.8:
                    drop.add(z if s[keep[a]] >= s[keep[z]] else a)
        per_cls: dict[int, int] = defaultdict(int)
        for j, idx in enumerate(keep.tolist()):  # keep is sorted by score, high first
            if j in drop:
                continue
            name = dets[idx][2]
            per_cls[CATEGORY_ID[name]] += 1
            if per_cls[CATEGORY_ID[name]] > MAX_PER_FRAME.get(name, 99):
                continue
            x0, y0, x1, y1 = b[idx].tolist()
            annotations.append({
                "id": len(annotations) + 1, "image_id": i + 1, "category_id": int(c[idx]),
                "bbox": [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)],
                "area": round((x1 - x0) * (y1 - y0), 1), "iscrowd": 0,
                "attributes": {"prelabel_score": round(float(s[idx]), 3)},
            })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"images": images, "annotations": annotations,
                                    "categories": coco_categories()}), encoding="utf-8")
    print(f"{len(annotations)} boxes on {len(images)} frames -> {args.out}")


if __name__ == "__main__":
    main()
