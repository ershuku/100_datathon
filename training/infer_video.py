"""Run a trained detector over videos and write tracker-format JSON (one file per video).

    python training/infer_video.py --weights runs/v0/checkpoint_best_total.pth \
        --videos ~/open/videos/X-22.mov ~/open/videos/X-4.mov --out runs/v0/eval [--samples 6]

Per video <out>/<name>.json:
    {"source_sha256", "source_end_pts", "sampling": {"target_fps"}, "model": {...},
     "frames": [{"frame_index", "pts_sec", "width", "height",
                 "detections": [{"label", "score", "box_xyxy"}]}]}
frame_index is the index in the source video; pts_sec comes from the decoder (PyAV), not
index / fps; boxes are in source-frame pixels; frames without detections are kept. Rotated
videos are rejected, as the tracker pilot does. --samples saves that many evenly spaced frames
per video with boxes drawn (<out>/<name>_samples/) for eyeballing hits, misses and false boxes.
<out>/summary.json collects speed, GPU memory and per-class detection counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import av
import cv2
import numpy as np
import torch
from rfdetr import RFDETR


# Fixed furniture exists once per room: per frame keep only the highest-scoring box of each family,
# so the output never says "safe open" and "safe closed" at the same time. --keep-all disables it.
FAMILY = {"safe_open": "safe", "safe_closed": "safe", "laptop_open": "laptop", "laptop_closed": "laptop",
          "door_open": "door", "door_closed": "door", "counter_machine": "counter", "uv_detector": "uv"}


def one_per_family(dets: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    out = []
    for d in dets:
        fam = FAMILY.get(d["label"])
        if fam is None:
            out.append(d)
        elif fam not in best or d["score"] > best[fam]["score"]:
            best[fam] = d
    return out + list(best.values())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(model, path: Path, fps: float, threshold: float,
        keep_all: bool = False) -> tuple[dict, list[np.ndarray], float]:
    frames, images = [], []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        rotation = stream.metadata.get("rotate") or "0"
        if rotation not in ("0", "0.0"):
            raise SystemExit(f"{path.name}: rotated video ({rotation} deg) is not supported")
        tb = float(stream.time_base)
        next_t, last_end, infer_s = 0.0, 0.0, 0.0
        for index, frame in enumerate(container.decode(stream)):
            pts = float(frame.pts * tb)
            dur = float(frame.duration * tb) if frame.duration else 1.0 / float(stream.average_rate or 30)
            last_end = pts + dur
            if pts + 1e-6 < next_t:
                continue
            next_t = (np.floor(pts * fps + 1e-6) + 1) / fps
            rgb = frame.to_ndarray(format="rgb24")
            t0 = time.perf_counter()
            det = model.predict(rgb, threshold=threshold)
            infer_s += time.perf_counter() - t0
            names = det.data.get("class_name", [str(c) for c in det.class_id])
            dets = [{"label": str(c), "score": round(float(s), 4), "box_xyxy": [round(float(v), 1) for v in b]}
                    for c, s, b in zip(names, det.confidence, det.xyxy)]
            if not keep_all:
                dets = one_per_family(dets)
            frames.append({"frame_index": index, "pts_sec": round(pts, 4),
                           "width": rgb.shape[1], "height": rgb.shape[0], "detections": dets})
            images.append(rgb)
    doc = {"source_sha256": sha256(path), "source_end_pts": round(last_end, 4),
           "sampling": {"target_fps": fps}, "frames": frames}
    return doc, images, infer_s


def draw(rgb: np.ndarray, frame: dict) -> np.ndarray:
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for d in frame["detections"]:
        x0, y0, x1, y1 = map(int, d["box_xyxy"])
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 0), 2)
        cv2.putText(img, f"{d['label']} {d['score']:.2f}", (x0, max(12, y0 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    cv2.putText(img, f"t={frame['pts_sec']:.1f}s", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--videos", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--samples", type=int, default=0)
    ap.add_argument("--keep-all", action="store_true",
                    help="keep every furniture box instead of the best one per family per frame")
    args = ap.parse_args()

    model = RFDETR.from_checkpoint(args.weights)
    model.predict(np.zeros((848, 464, 3), np.uint8), threshold=args.threshold)  # warm-up
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"weights": args.weights, "threshold": args.threshold, "target_fps": args.fps,
               "gpu": torch.cuda.get_device_name() if torch.cuda.is_available() else "cpu", "videos": {}}
    for path in args.videos:
        t0 = time.perf_counter()
        doc, images, infer_s = run(model, path, args.fps, args.threshold, args.keep_all)
        wall = time.perf_counter() - t0
        doc["model"] = {"weights": Path(args.weights).name, "threshold": args.threshold,
                        "one_per_family": not args.keep_all}
        (args.out / f"{path.stem}.json").write_text(json.dumps(doc), encoding="utf-8")
        counts = Counter(d["label"] for f in doc["frames"] for d in f["detections"])
        n = len(doc["frames"])
        summary["videos"][path.stem] = {
            "duration_sec": doc["source_end_pts"], "frames": n, "wall_sec": round(wall, 2),
            "ms_per_frame_model": round(1000 * infer_s / max(n, 1), 1),
            "detections_per_class": dict(sorted(counts.items())),
            "frames_with_class": dict(sorted(Counter(
                lab for f in doc["frames"] for lab in {d["label"] for d in f["detections"]}).items())),
        }
        if args.samples:
            sdir = args.out / f"{path.stem}_samples"
            sdir.mkdir(exist_ok=True)
            for i in np.linspace(0, n - 1, min(args.samples, n)).astype(int):
                cv2.imwrite(str(sdir / f"{doc['frames'][i]['pts_sec']:06.1f}s.jpg"), draw(images[i], doc["frames"][i]))
        print(f"{path.stem}: {n} frames in {wall:.1f}s ({summary['videos'][path.stem]['ms_per_frame_model']} "
              f"ms/frame model) {dict(counts)}", flush=True)
    if torch.cuda.is_available():
        summary["peak_gpu_mem_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"peak GPU memory {summary.get('peak_gpu_mem_mb')} MB -> {args.out}/summary.json")


if __name__ == "__main__":
    main()
