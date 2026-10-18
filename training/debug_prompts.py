"""Print raw Grounding DINO phrases/scores on a few frames to tune PROMPTS.

    python training/debug_prompts.py --frames datasets/frames --n 12 [--separate]

--separate runs each prompt alone (slower, but avoids prompts competing in one caption).
"""

from __future__ import annotations

import argparse
import collections
import csv
import random
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

from classes import PROMPTS
from prelabel import MODEL_ID


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--threshold", type=float, default=0.2)
    ap.add_argument("--separate", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.frames / "manifest.csv", encoding="utf-8")))
    random.seed(0)
    rows = random.sample(rows, min(args.n, len(rows)))
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_ID).to("cuda").eval()
    captions = [p + "." for p in PROMPTS] if args.separate else [". ".join(PROMPTS) + "."]

    best: dict[str, list[float]] = collections.defaultdict(list)
    for r in rows:
        im = Image.open(args.frames / "images" / r["file"]).convert("RGB")
        for cap in captions:
            inputs = processor(images=im, text=cap, return_tensors="pt").to("cuda")
            with torch.no_grad():
                out = model(**inputs)
            res = processor.post_process_grounded_object_detection(
                out, inputs.input_ids, threshold=args.threshold, text_threshold=args.threshold,
                target_sizes=[im.size[::-1]])[0]
            for label, score in zip(res.get("text_labels", res["labels"]), res["scores"]):
                key = f"{cap[:-1]} -> {label!r}" if args.separate else repr(label)
                best[key].append(float(score))
    for key, scores in sorted(best.items(), key=lambda kv: -len(kv[1])):
        print(f"{len(scores):4}x  max {max(scores):.2f}  {key}")


if __name__ == "__main__":
    main()
