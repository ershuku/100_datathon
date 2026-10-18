"""Train/validation split by recording group, never by single frame or single video.

Clips recorded as variants of one scenario (same setting, violation vs clean take) share a
group so near-identical frames cannot sit on both sides of the split. Only video ids and camera
POV live here — no label content.
"""

from __future__ import annotations

import re

POV: dict[str, str] = {
    **{f"X-{n}": "behind" for n in (1, 2, 3, 4, 5, 16, 17, 18, 19, 34, 35, 37, 38, 39, 47, 48)},
    **{
        f"X-{n}": "front"
        for n in (8, 10, 11, 12, 13, 14, 15, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
                  33, 40, 43, 44, 45, 46)
    },
}

# Byte-identical files in the organiser's dataset (same SHA-256): the copy is skipped everywhere
# (frames, CVAT, training) and kept in the original's group. Its labels differ (X-4 violation at
# 57 s, X-47 at 68 s), so the copy still matters for checking rule timecodes, never for training.
DUPLICATE_OF: dict[str, str] = {"X-47": "X-4", "X-48": "X-5"}

GROUPS: list[tuple[int, ...]] = [
    (1,), (2, 3), (4, 5, 47, 48), (8,), (10,), (11, 12), (13, 14), (15,), (16, 17), (18, 19),
    (20, 21), (22, 23), (24, 25), (26, 27), (28, 29), (30, 31, 32, 33), (34, 35, 37), (38, 39),
    (40,), (43, 44, 45), (46,),
]

# ~25% of unique footage, both POVs, mix of deposit / exit / counterfeit scenarios.
DEFAULT_VAL_GROUPS: set[tuple[int, ...]] = {(4, 5, 47, 48), (38, 39), (22, 23), (43, 44, 45)}
# Final held-out test (~8% of unique footage, both POVs; each group a violation + clean take).
# Look at it ONCE, after the final model for a release is chosen: anything tuned after looking
# turns it into validation. Re-fixed 2026-10-18 after X-47/48 turned out to copy X-4/5;
# v0 and v3 predate this split and trained on (2, 3) and (24, 25), so they cannot be scored on it.
TEST_GROUPS: set[tuple[int, ...]] = {(2, 3), (24, 25), (28, 29)}


def norm_video_id(name: str) -> str:
    """'Х-3' (Cyrillic Х, as in the label sheet), 'x-3.mov', 'X-3' -> 'X-3'."""
    m = re.search(r"(\d+)", name.replace("Х", "X").replace("х", "x"))
    if not m:
        raise ValueError(f"no video number in {name!r}")
    return f"X-{int(m.group(1))}"


def is_duplicate(video_id: str) -> bool:
    return video_id in DUPLICATE_OF


def split_of(video_id: str, holdout_pov: str | None = None) -> str:
    """'train', 'valid' or 'test'. With holdout_pov, every non-test clip of that POV is validation."""
    video_id = DUPLICATE_OF.get(video_id, video_id)
    n = int(video_id.split("-")[1])
    if any(n in g for g in TEST_GROUPS):
        return "test"
    if holdout_pov:
        return "valid" if POV.get(video_id) == holdout_pov else "train"
    for g in DEFAULT_VAL_GROUPS:
        if n in g:
            return "valid"
    return "train"
