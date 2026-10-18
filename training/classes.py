"""Detector label space and the zero-shot prompts used to pre-label it.

State pairs (safe/laptop/door open vs closed) cannot be told apart reliably by a zero-shot
detector, so pre-labelling emits the more common state and the annotator flips it in CVAT.
"""

from __future__ import annotations

# Order defines COCO category ids (1-based). Append new classes at the end; never reorder,
# or old exports silently get the wrong labels.
CLASSES: list[str] = [
    "person",
    "cash_stack",
    "cash_bag",
    "id_card",
    "keys",
    "safe_open",
    "safe_closed",
    "laptop_open",
    "laptop_closed",
    "door_open",
    "door_closed",
    "counter_machine",
    "uv_detector",
    "journal",
    "scissors",
    "personal_item",
]

# Grounding DINO prompt -> (class, box threshold). Each prompt runs as its own caption: in one
# combined caption the prompts compete and the model returns word fragments ("##notes").
# Thresholds come from training/debug_prompts.py --separate on sample frames; id card and
# uv lamp fire on almost every frame, hence the high bars.
PROMPTS: dict[str, tuple[str, float]] = {
    "person": ("person", 0.35),
    "stack of banknotes": ("cash_stack", 0.30),
    "cash bag": ("cash_bag", 0.40),
    "id card": ("id_card", 0.40),
    "keys": ("keys", 0.22),
    "safe": ("safe_closed", 0.30),
    "laptop": ("laptop_open", 0.35),
    "door": ("door_closed", 0.35),
    "money counting machine": ("counter_machine", 0.30),
    "uv lamp": ("uv_detector", 0.40),
    "notebook": ("journal", 0.30),
    "scissors": ("scissors", 0.35),
    "cup": ("personal_item", 0.35),
    "mobile phone": ("personal_item", 0.35),
    "jacket": ("personal_item", 0.35),
}

# Fixed furniture appears once per room; keep only the best pre-label box per frame.
MAX_PER_FRAME: dict[str, int] = {
    "safe_closed": 1, "laptop_open": 1, "counter_machine": 1, "door_closed": 1, "uv_detector": 1,
}

CATEGORY_ID: dict[str, int] = {name: i + 1 for i, name in enumerate(CLASSES)}


def coco_categories() -> list[dict]:
    return [{"id": CATEGORY_ID[n], "name": n, "supercategory": n} for n in CLASSES]
