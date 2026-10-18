"""Print compact per-second timelines of the rule engine's smoothed signals, for rule debugging.

    python training/rule_timelines.py --detections runs/v4/det_all --videos X-11,X-20,X-22

One character per second and signal: people count (0-9), door/safe/laptop o=open c=closed .=unseen,
cash on desk count, C = cash in the counting machine, I = ID card, P = personal item on desk,
K = keys at the safe.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import rules  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detections", type=Path, required=True)
    ap.add_argument("--videos", required=True)
    args = ap.parse_args()
    for vid in args.videos.split(","):
        res = rules.evaluate(json.loads((args.detections / f"{vid}.json").read_text(encoding="utf-8")))
        per_sec: dict[int, rules.Frame] = {}
        for f in res.frames:
            per_sec.setdefault(int(f.t), f)
        secs = sorted(per_sec)
        def line(fn):
            return "".join(fn(per_sec[s]) for s in secs)
        st = lambda v: {"open": "o", "closed": "c", None: "."}[v]  # noqa: E731
        print(f"== {vid}  ({len(secs)} s)  fired: {[f'{v.code}@{v.t:g}' for v in res.violations]}")
        print("  sec    " + "".join(str(s % 10) for s in secs))
        print("  people " + line(lambda f: str(min(f.people, 9))))
        print("  door   " + line(lambda f: st(f.door)))
        print("  safe   " + line(lambda f: st(f.safe)))
        print("  laptop " + line(lambda f: st(f.laptop)))
        print("  cash   " + line(lambda f: str(min(f.cash_desk, 9)) if f.cash_desk else "."))
        print("  flags  " + line(lambda f: ("C" if f.cash_counter else "") + ("I" if f.id_card else "")
                                 + ("P" if f.personal_desk else "") + ("K" if f.keys_in_safe else "") or "."
                                 if True else ""))


if __name__ == "__main__":
    main()
