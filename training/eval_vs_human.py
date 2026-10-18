"""Before/after on the boxes people drew or fixed in CVAT (the only human-checked labels so far).

    python training/eval_vs_human.py --weights runs/v0/checkpoint_best_total.pth \
        --before datasets/frames/prelabels.coco.json datasets/frames/prelabels_smooth_v3.coco.json

For each human box: did each source (pre-label files = "before", the trained model = "after") put
the same class there (IoU >= 0.5)? Reported per class and split by whether the model trained on
that clip. Human boxes cover only what someone touched, not every object, so this is recall on
a small sample: precision and mAP need the fully corrected exports.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from rfdetr import RFDETR

from compare_prelabels import cvat_manual, iou, load
from splits import norm_video_id, split_of


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--before", type=Path, nargs="+", required=True)
    ap.add_argument("--frames", type=Path, default=Path("../datasets/frames"))
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--trained-on", default="train",
                    help="split names the model trained on, comma-separated (v0: train,test)")
    args = ap.parse_args()

    gt = cvat_manual()
    trained = set(args.trained_on.split(","))
    model = RFDETR.from_checkpoint(args.weights)
    sources = {p.stem.replace("prelabels", "pre").replace(".coco", ""): load(p)[0] for p in args.before}
    preds: dict[str, list] = {}
    for fname in {g[0] for g in gt}:
        det = model.predict(np.array(Image.open(args.frames / "images" / fname).convert("RGB")),
                            threshold=args.threshold)
        names = det.data.get("class_name", [str(c) for c in det.class_id])
        preds[fname] = [(str(c), list(map(float, b))) for c, b in zip(names, det.xyxy)]
    sources["model"] = preds

    rows: dict[str, dict[str, Counter]] = {}
    for fname, cls, box in gt:
        seen = "seen" if split_of(norm_video_id(fname.split("_t")[0])) in trained else "unseen"
        r = rows.setdefault(seen, {"total": Counter(), **{s: Counter() for s in sources}})
        r["total"][cls] += 1
        for name, by_file in sources.items():
            if any(c == cls and iou(box, b) >= 0.5 for c, b in by_file.get(fname, [])):
                r[name][cls] += 1
    for seen, r in sorted(rows.items()):
        print(f"\n== human boxes on clips the model {'trained on' if seen == 'seen' else 'did NOT train on'}")
        print(f"{'class':16} {'human':>5} " + " ".join(f"{s[:14]:>14}" for s in sources))
        for cls in sorted(r["total"]):
            print(f"{cls:16} {r['total'][cls]:5} " + " ".join(f"{r[s][cls]:14}" for s in sources))
        print(f"{'all':16} {sum(r['total'].values()):5} " +
              " ".join(f"{sum(r[s].values()):14}" for s in sources))


if __name__ == "__main__":
    main()
