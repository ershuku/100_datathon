"""Replace pre-labels in CVAT tasks that nobody has edited yet.

    python training/cvat_reimport.py --prelabels datasets/frames/prelabels_smooth.coco.json --tasks part1 part2 part3

A task is replaced only if every box in it still has source "file" (i.e. came from an import);
any manual box makes the script skip that task, so human work is never overwritten.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from cvat_sdk import make_client


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prelabels", type=Path, required=True)
    ap.add_argument("--tasks", nargs="+", required=True, help="task name prefixes, e.g. part1")
    ap.add_argument("--url", default="http://localhost:8080")
    args = ap.parse_args()

    coco = json.loads(args.prelabels.read_text(encoding="utf-8"))
    pw = (Path.home() / ".cvat_admin").read_text().strip()
    with make_client(args.url, credentials=("admin", pw)) as client:
        for task in sorted(client.tasks.list(), key=lambda t: t.id):
            if not any(task.name.startswith(p + ":") for p in args.tasks):
                continue
            ann = task.get_annotations()
            manual = [s for s in ann.shapes if s.source != "file"] + list(ann.tracks)
            if manual:
                print(f"SKIP {task.name[:5]}: {len(manual)} manual boxes/tracks - not overwriting")
                continue
            names = {f.name for f in task.get_frames_info()}
            imgs = [im for im in coco["images"] if im["file_name"] in names]
            ids = {im["id"] for im in imgs}
            anns = [a for a in coco["annotations"] if a["image_id"] in ids]
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
                json.dump({"images": imgs, "annotations": anns, "categories": coco["categories"]}, tmp)
            task.remove_annotations()
            task.import_annotations(format_name="COCO 1.0", filename=tmp.name)
            Path(tmp.name).unlink()
            print(f"{task.name[:5]}: {len(ann.shapes)} old boxes -> {len(task.get_annotations().shapes)} new "
                  f"on {len(imgs)} frames")


if __name__ == "__main__":
    main()
