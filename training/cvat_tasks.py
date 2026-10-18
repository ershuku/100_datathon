"""Create the CVAT project and one task per annotator, with pre-labels imported.

    python training/cvat_tasks.py --frames datasets/frames --prelabels datasets/frames/prelabels.coco.json \
        --annotators 4

Recording groups (training/splits.py) are kept whole and dealt to annotators so every task has
roughly the same frame count. Reads the admin password from ~/.cvat_admin.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from cvat_sdk import make_client
from cvat_sdk.core.proxies.tasks import ResourceType

from classes import CLASSES
from splits import GROUPS, is_duplicate, norm_video_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--prelabels", type=Path, required=True)
    ap.add_argument("--annotators", type=int, default=4)
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--project", default="cashier-detector")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.frames / "manifest.csv", encoding="utf-8")))
    frames_by_video: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if not is_duplicate(r["video"]):  # identical copies would be labelled twice
            frames_by_video[r["video"]].append(r["file"])

    # Deal groups, largest first, to whichever task currently has the fewest frames.
    groups = sorted(GROUPS, key=lambda g: -sum(len(frames_by_video[f"X-{n}"]) for n in g))
    tasks: list[list[str]] = [[] for _ in range(args.annotators)]
    for g in groups:
        target = min(range(args.annotators), key=lambda i: sum(len(frames_by_video[v]) for v in tasks[i]))
        tasks[target].extend(f"X-{n}" for n in g if not is_duplicate(f"X-{n}"))

    coco = json.loads(args.prelabels.read_text(encoding="utf-8"))
    pw = (Path.home() / ".cvat_admin").read_text().strip()
    with make_client(args.url, credentials=("admin", pw)) as client:
        project = client.projects.create(
            spec={"name": args.project, "labels": [{"name": n, "type": "rectangle"} for n in CLASSES]})
        for i, videos in enumerate(tasks, 1):
            videos.sort(key=lambda v: int(v[2:]))
            files = [f for v in videos for f in frames_by_video[v]]
            names = set(files)
            imgs = [im for im in coco["images"] if im["file_name"] in names]
            ids = {im["id"] for im in imgs}
            anns = [{k: v for k, v in a.items() if k != "attributes"}
                    for a in coco["annotations"] if a["image_id"] in ids]
            task = client.tasks.create_from_data(
                spec={"name": f"part{i}: {','.join(videos)}", "project_id": project.id},
                resource_type=ResourceType.LOCAL,
                resources=[str(args.frames / "images" / f) for f in files],
                data_params={"image_quality": 95, "sorting_method": "natural"},
            )
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
                json.dump({"images": imgs, "annotations": anns, "categories": coco["categories"]}, tmp)
            task.import_annotations(format_name="COCO 1.0", filename=tmp.name)
            Path(tmp.name).unlink()
            print(f"task {task.id} part{i}: {len(files)} frames, {len(anns)} pre-label boxes, videos {videos}")
    print(f"project {project.id} -> {args.url}/projects/{project.id}")


if __name__ == "__main__":
    main()
