"""Re-label furniture pre-labels by visual similarity to reference crops (DINOv2, Apache-2.0).

    python training/refine_prelabels.py --frames datasets/frames --refs datasets/refs \
        --prelabels datasets/frames/prelabels.coco.json --out datasets/frames/prelabels_refined.coco.json

Grounding DINO finds furniture but names it badly (wall -> door, safe missed). Here it only
proposes boxes (low threshold, furniture-ish prompts); each box crop is embedded with DINOv2 and
takes the class of the most similar reference crops in refs/<class>/*.jpg. A refs/background/
folder (walls, reflections, empty desk) lets wrong boxes be rejected explicitly; without it a
similarity floor learned from the refs does that job. Classes without refs keep their old
pre-labels, except door_*, which is dropped (known garbage; doors get labelled by keyframes).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision.ops import nms
from transformers import AutoImageProcessor, AutoModel, AutoModelForZeroShotObjectDetection, AutoProcessor

from classes import CATEGORY_ID, CLASSES, coco_categories
from prelabel import MODEL_ID as GDINO_ID

DINO_ID = "facebook/dinov2-base"
PROPOSAL_PROMPTS = ["safe", "metal cabinet", "laptop", "money counting machine", "machine", "box",
                    "stack of banknotes", "money", "cash bag", "bag", "id card", "card", "notebook",
                    "uv lamp", "door", "glass door"]
# At most one box per family per frame; a family's classes compete for that slot. Classes outside
# a family (cash, ID, bag, journal) may appear several times per frame.
FAMILY = {"safe_open": "safe", "safe_closed": "safe", "laptop_open": "laptop", "laptop_closed": "laptop",
          "counter_machine": "counter", "uv_detector": "uv", "door_open": "door", "door_closed": "door"}
# Ref folder names people actually use -> class names.
ALIASES = {"id": "id_card", "id_card": "id_card", "cash": "cash_stack", "money": "cash_stack"}
DROP_ALWAYS = {"door_open", "door_closed"}
# Too small for the furniture proposals (refs are ~10x6 px); keep their Grounding DINO pre-labels.
NOT_MATCHED = {"keys"}


class Embedder:
    def __init__(self, device: str):
        self.device = device
        self.proc = AutoImageProcessor.from_pretrained(DINO_ID)
        self.proc.do_center_crop = False
        self.proc.size = {"height": 224, "width": 224}
        self.model = AutoModel.from_pretrained(DINO_ID).to(device).eval()

    @torch.no_grad()
    def __call__(self, crops: list[Image.Image]) -> np.ndarray:
        out = []
        for i in range(0, len(crops), 64):
            inputs = self.proc(images=crops[i:i + 64], return_tensors="pt").to(self.device)
            h = self.model(**inputs).last_hidden_state
            feat = torch.cat([h[:, 0], h[:, 1:].mean(1)], dim=1)
            out.append(torch.nn.functional.normalize(feat, dim=1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 1536), np.float32)


def load_refs(refs: Path) -> tuple[list[str], list[Image.Image]]:
    labels, crops = [], []
    for d in sorted(p for p in refs.iterdir() if p.is_dir()):
        name = ALIASES.get(d.name.lower(), d.name)
        if name not in CATEGORY_ID and name != "background":
            print(f"skip refs/{d.name}: not a class in training/classes.py")
            continue
        if name in NOT_MATCHED:
            print(f"skip refs/{d.name}: too small to match against proposals")
            continue
        files = [f for f in sorted(d.glob("*")) if f.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        if not files:
            print(f"skip refs/{d.name}: empty")
        for f in files:
            labels.append(name)
            crops.append(Image.open(f).convert("RGB"))
    return labels, crops


def class_scores(sims: np.ndarray, ref_labels: np.ndarray, classes: list[str], k: int = 3) -> np.ndarray:
    """sims: (n, n_refs) -> (n, n_classes), mean of each class's top-k similarities."""
    out = np.full((sims.shape[0], len(classes)), -1.0, np.float32)
    for j, c in enumerate(classes):
        s = sims[:, ref_labels == c]
        kk = min(k, s.shape[1])
        out[:, j] = np.sort(s, axis=1)[:, -kk:].mean(1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--refs", type=Path, required=True)
    ap.add_argument("--prelabels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--proposal-threshold", type=float, default=0.15)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--person-margin", type=float, default=0.05,
                    help="drop a person box only if background similarity beats person similarity by this much")
    args = ap.parse_args()
    device = "cuda"

    ref_labels, ref_crops = load_refs(args.refs)
    embed = Embedder(device)
    ref_feat = embed(ref_crops)
    ref_lab = np.array(ref_labels)
    ref_classes = sorted(set(ref_labels))
    print("refs:", dict(Counter(ref_labels)))

    # Leave-one-out on the refs: how separable are the classes (open vs closed especially)?
    sims = ref_feat @ ref_feat.T
    np.fill_diagonal(sims, -1)
    loo = class_scores(sims, ref_lab, ref_classes)
    pred = np.array(ref_classes)[loo.argmax(1)]
    same = loo[np.arange(len(ref_lab)), [ref_classes.index(c) for c in ref_lab]]
    floor = float(np.percentile(same, 10)) - 0.05
    print(f"leave-one-out accuracy {np.mean(pred == ref_lab):.0%}; similarity floor {floor:.3f}")
    for c in ref_classes:
        m = ref_lab == c
        if m.sum() > 1:
            print(f"  {c:16} {np.mean(pred[m] == c):.0%}  confused with {dict(Counter(pred[m][pred[m] != c]))}")

    # Proposals don't depend on the refs, so they are cached: reruns with new refs skip Grounding DINO.
    rows = list(csv.DictReader(open(args.frames / "manifest.csv", encoding="utf-8")))
    cache = args.frames / "proposals_cache.json"
    key = {"prompts": PROPOSAL_PROMPTS, "threshold": args.proposal_threshold}
    proposals: dict[str, list[list[float]]] = {}
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved.get("key") == key:
            proposals = saved["boxes"]
            print(f"using cached proposals for {len(proposals)} frames")
    todo = [r for r in rows if r["file"] not in proposals]
    if todo:
        proc = AutoProcessor.from_pretrained(GDINO_ID)
        proc.image_processor.size = {"shortest_edge": 464, "longest_edge": 848}
        gdino = AutoModelForZeroShotObjectDetection.from_pretrained(GDINO_ID).to(device).eval()
    for start in range(0, len(todo), args.batch):
        chunk = todo[start:start + args.batch]
        pil = [Image.open(args.frames / "images" / r["file"]).convert("RGB") for r in chunk]
        boxes: list[list] = [[] for _ in pil]
        for prompt in PROPOSAL_PROMPTS:
            inputs = proc(images=pil, text=[prompt + "."] * len(pil), return_tensors="pt").to(device)
            with torch.no_grad(), torch.autocast(device, dtype=torch.bfloat16):
                o = gdino(**inputs)
            o.logits, o.pred_boxes = o.logits.float(), o.pred_boxes.float()
            res = proc.post_process_grounded_object_detection(
                o, inputs.input_ids, threshold=args.proposal_threshold,
                text_threshold=args.proposal_threshold, target_sizes=[im.size[::-1] for im in pil])
            for k, rr in enumerate(res):
                boxes[k].extend(zip(rr["boxes"].tolist(), rr["scores"].tolist()))
        for r, im, bx in zip(chunk, pil, boxes):
            kept = []
            if bx:
                b = torch.tensor([x[0] for x in bx])
                s = torch.tensor([x[1] for x in bx])
                b[:, 0::2] = b[:, 0::2].clamp(0, im.width)
                b[:, 1::2] = b[:, 1::2].clamp(0, im.height)
                ok = ((b[:, 2] - b[:, 0]) >= 8) & ((b[:, 3] - b[:, 1]) >= 8)
                b, s = b[ok], s[ok]
                kept = b[nms(b, s, 0.6)].tolist() if len(b) else []
            proposals[r["file"]] = kept
        print(f"proposals {min(start + args.batch, len(todo))}/{len(todo)} frames", flush=True)
    if todo:
        cache.write_text(json.dumps({"key": key, "boxes": proposals}), encoding="utf-8")

    # Match every proposal against the refs.
    refined: dict[str, list[tuple[list[float], str, float]]] = {}
    for n, r in enumerate(rows, 1):
        kept = proposals.get(r["file"], [])
        if not kept:
            refined[r["file"]] = []
            continue
        im = Image.open(args.frames / "images" / r["file"]).convert("RGB")
        feat = embed([im.crop(tuple(map(int, x))) for x in kept])
        sc = class_scores(feat @ ref_feat.T, ref_lab, ref_classes)
        best, multi = {}, []
        for box, row in zip(kept, sc):
            j = int(row.argmax())
            cls, sim = ref_classes[j], float(row[j])
            # People come from the person pre-labels (filtered below), never from these proposals.
            if cls in ("background", "person") or sim < floor:
                continue
            fam = FAMILY.get(cls)
            if fam is None:
                multi.append((box, cls, sim, 1.0))
                continue
            # The box is this family's object; its state is decided only between the family's own
            # states (open vs closed), never against unrelated classes, with the gap between them as
            # confidence. Picking the state by global argmax let any door-ish wall crop that happened
            # to sit nearer "door_open" refs win the frame, which is why doors came out always open.
            states = [k for k, c in enumerate(ref_classes) if FAMILY.get(c) == fam]
            ranked = sorted(states, key=lambda k: -row[k])
            state = ref_classes[ranked[0]]
            margin = float(row[ranked[0]] - row[ranked[1]]) if len(ranked) > 1 else 0.0
            if fam not in best or sim > best[fam][2]:
                best[fam] = (box, state, sim, margin)
        refined[r["file"]] = list(best.values()) + multi
        if n % 200 == 0:
            print(f"matched {n}/{len(rows)} frames", flush=True)

    # Merge: refined furniture + old pre-labels for classes that have no refs.
    coco = json.loads(args.prelabels.read_text(encoding="utf-8"))
    id2name = {c["id"]: c["name"] for c in coco["categories"]}
    replaced = set(ref_classes) - {"background", "person"}
    replaced_families = {FAMILY.get(c, c) for c in replaced}
    file_to_id = {im["file_name"]: im["id"] for im in coco["images"]}
    id_to_file = {v: k for k, v in file_to_id.items()}
    anns, people = [], defaultdict(list)
    for a in coco["annotations"]:
        name = id2name[a["category_id"]]
        if name in DROP_ALWAYS or FAMILY.get(name, name) in replaced_families:
            continue
        if name == "person" and "person" in ref_classes and "background" in ref_classes:
            people[id_to_file[a["image_id"]]].append(a)
            continue
        anns.append(a)

    # Person pre-labels: keep a box only if it looks more like the person refs than the background
    # refs (glass-door reflections, walls). Nothing is relabelled, boxes are only kept or dropped.
    if people:
        pi, bi = ref_classes.index("person"), ref_classes.index("background")
        dropped: Counter[str] = Counter()
        gaps: list[float] = []
        for fname, plist in people.items():
            im = Image.open(args.frames / "images" / fname).convert("RGB")
            crops = []
            for a in plist:
                x, y, w, h = a["bbox"]
                crops.append(im.crop((int(x), int(y), int(x + w), int(y + h))))
            sc = class_scores(embed(crops) @ ref_feat.T, ref_lab, ref_classes)
            for a, row in zip(plist, sc):
                gap = float(row[bi] - row[pi])
                gaps.append(gap)
                if gap <= args.person_margin:
                    anns.append(a)
                else:
                    dropped[fname.split("_t")[0]] += 1
        g = np.array(gaps)
        print("person drop rate by margin: " + ", ".join(
            f"{m:.2f}->{np.mean(g > m):.0%}" for m in (0.0, 0.02, 0.05, 0.08, 0.1, 0.15)))
        kept_people = sum(len(v) for v in people.values()) - sum(dropped.values())
        print(f"person boxes: kept {kept_people}, dropped {sum(dropped.values())} as background/reflection; "
              f"most dropped in {dropped.most_common(8)}")
    per_cls: Counter[str] = Counter()
    for fname, dets in refined.items():
        for (x0, y0, x1, y1), cls, sim, margin in dets:
            per_cls[cls] += 1
            anns.append({"id": 0, "image_id": file_to_id[fname], "category_id": CATEGORY_ID[cls],
                         "bbox": [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)],
                         "area": round((x1 - x0) * (y1 - y0), 1), "iscrowd": 0,
                         "attributes": {"ref_similarity": round(sim, 3), "state_margin": round(margin, 4)}})
    for i, a in enumerate(anns, 1):
        a["id"] = i
    args.out.write_text(json.dumps({"images": coco["images"], "annotations": anns,
                                    "categories": coco_categories()}), encoding="utf-8")

    by_video = defaultdict(Counter)
    for fname, dets in refined.items():
        for _, cls, _, _ in dets:
            by_video[fname.split("_t")[0]][cls] += 1
    # How decisive the state calls were: a low median margin means the refs barely separate
    # open from closed for that family, so more (and more varied) refs are needed there.
    margins = defaultdict(list)
    for dets in refined.values():
        for _, cls, _, m in dets:
            if FAMILY.get(cls) in ("safe", "laptop", "door"):  # families with two states
                margins[FAMILY[cls]].append(m)
    for fam, ms in sorted(margins.items()):
        ms = np.array(ms)
        print(f"state margin {fam:8} median {np.median(ms):.3f}, <0.01 on {np.mean(ms < 0.01):.0%} of frames")
    print("refined boxes:", dict(per_cls))
    print("per video (frames with each class):")
    n_frames = Counter(r["video"] for r in rows)
    for v in sorted(by_video, key=lambda v: int(v[2:])):
        print(f"  {v:5} {n_frames[v]:3} frames  " + ", ".join(f"{c} {n}" for c, n in sorted(by_video[v].items())))
    print(f"{len(anns)} boxes -> {args.out}  (kept old pre-labels for: "
          f"{sorted(set(CLASSES) - replaced - DROP_ALWAYS)}; person filtered: {bool(people)})")


if __name__ == "__main__":
    main()
