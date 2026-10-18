"""Bundle a trained detector for the tracker team: weights, classes.json, inference code,
pinned dependency versions, run command and checksums, as one tar.gz.

    python training/package_model.py --run runs/v3 --name detector_v3 --out dist

Run inside the training venv so the pinned versions are the ones the weights were tested with.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from rfdetr import RFDETR

INFER_DEPS = ["torch", "torchvision", "rfdetr", "transformers", "supervision", "av", "opencv-python-headless",
              "numpy", "pillow", "peft", "pydantic"]

README = """# {name}: cashier-room object detector

Interim weights: trained on machine pre-labels ({labels}), not yet on human-corrected labels.
Check quality on your side before relying on any class; see "Known limits".

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-inference.txt --extra-index-url https://download.pytorch.org/whl/cu126
python infer_video.py --weights checkpoint_best_total.pth --videos /path/X.mov --out out/ [--fps 5 --threshold 0.35]
```

Writes out/<video>.json in the tracker format (frames[] with frame_index, pts_sec, width, height,
detections[label, score, box_xyxy]; plus source_sha256, source_end_pts, sampling.target_fps) and
out/summary.json with speed and peak GPU memory. Runs fully offline: weights are local, no API.

## Box coordinates

- Frames are decoded with PyAV at native resolution; frame_index is the source frame number and
  pts_sec the decoded timestamp (frame.pts * time_base), not index / fps. Sampling picks the first
  decoded frame at or after each 1/fps step.
- The full-resolution RGB frame goes to RFDETR.predict(). Inside, it is resized (no letterbox, no
  crop) to the model's square input ({res}x{res}); the model predicts normalised boxes, and
  rfdetr's postprocess scales them with the original (height, width) of that frame. So
  box_xyxy is already in source-frame pixels, x across width and y down height; no extra
  conversion is done or needed. width/height in the JSON are that decoded frame's size.
- Videos with rotation metadata are rejected (same as the tracker pilot). Our dataset clips are
  464x848 portrait with no rotation tag.

## Classes

classes.json lists the label names in model output order. Labels in the JSON are these names.
State classes are separate labels: safe_open/safe_closed, laptop_open/laptop_closed,
door_open/door_closed.

## Known limits ({name})

{limits}

## Measured (L40S, threshold 0.35, 5 fps)

{speed}
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path, default=Path("dist"))
    ap.add_argument("--labels", default="see training/README.md")
    ap.add_argument("--limits", default="- Not measured against human labels yet.")
    args = ap.parse_args()

    weights = args.run / "checkpoint_best_total.pth"
    stage = args.out / args.name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(weights, stage / weights.name)
    shutil.copy2(Path(__file__).with_name("infer_video.py"), stage / "infer_video.py")

    model = RFDETR.from_checkpoint(weights)
    names = list(model.class_names.values()) if isinstance(model.class_names, dict) else list(model.class_names)
    (stage / "classes.json").write_text(json.dumps({"classes": names}, indent=1), encoding="utf-8")
    res = getattr(model.model_config, "resolution", "?")

    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout
    pins = [l for l in freeze.splitlines() if l.split("==")[0].lower() in INFER_DEPS]
    pins = [p.replace("+cu126", "") for p in pins]
    (stage / "requirements-inference.txt").write_text(
        "# exact versions the weights were tested with (CUDA 12.6 wheels for torch/torchvision)\n"
        + "\n".join(sorted(pins)) + "\n", encoding="utf-8")

    speed = "not measured"
    summary = args.run / "eval_valid" / "summary.json"
    if summary.exists():
        s = json.loads(summary.read_text())
        ms = [v["ms_per_frame_model"] for v in s["videos"].values()]
        dur = sum(v["duration_sec"] for v in s["videos"].values())
        wall = sum(v["wall_sec"] for v in s["videos"].values())
        speed = (f"- model {min(ms)}-{max(ms)} ms/frame; {dur:.0f} s of video in {wall:.0f} s wall "
                 f"(decode + inference); peak GPU memory {s.get('peak_gpu_mem_mb')} MB")
    (stage / "README.md").write_text(README.format(name=args.name, labels=args.labels, res=res,
                                                   limits=args.limits, speed=speed), encoding="utf-8")

    files = sorted(p for p in stage.iterdir() if p.is_file())
    (stage / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in files), encoding="utf-8")
    archive = args.out / f"{args.name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(stage, arcname=args.name)
    print(f"{archive} ({archive.stat().st_size / 2**20:.0f} MB), sha256 {sha256(archive)}")
    print("contents:", [p.name for p in files] + ["SHA256SUMS"], "| classes:", names, "| input", res)


if __name__ == "__main__":
    main()
