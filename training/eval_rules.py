"""Score the rule engine against the organiser labels (verdict + timecode per video).

    python training/eval_rules.py --detections runs/v5/det_all --labels ../open/open_labels.xlsx

--detections holds tracker-format JSON per video (<video>.json, from infer_video.py). Videos in
the test split are refused unless --include-test is given: test is looked at once, at the end.
Duplicates (splits.DUPLICATE_OF) are skipped. Labels give one timecode per violating video and no
type, so this measures the verdict and the timing of the nearest flagged event only.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import rules  # noqa: E402

from splits import is_duplicate, norm_video_id, split_of  # noqa: E402


def read_labels(path: Path) -> dict[str, tuple[bool, float | None]]:
    """open_labels.xlsx -> {video: (is_violation, timecode_sec)} using only the stdlib."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S):
            shared.append(html.unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", si, re.S))))
    sheet = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))[0]
    out = {}
    for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(sheet).decode(), re.S):
        cells = {}
        for attrs, inner in re.findall(r"<c ([^>]*?)(?:/>|>(.*?)</c>)", row, re.S):
            col = re.search(r'r="([A-Z]+)', attrs).group(1)
            v = re.search(r"<v>(.*?)</v>", inner or "", re.S)
            if 't="s"' in attrs and v:
                cells[col] = shared[int(v.group(1))]
            elif 't="inlineStr"' in attrs:
                cells[col] = html.unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", inner or "", re.S)))
            elif v:
                cells[col] = v.group(1)
        name, verdict = cells.get("A", ""), cells.get("C", "").strip().lower()
        if not re.search(r"\d", name) or verdict not in ("нарушение", "без нарушения"):
            continue
        t = None
        if verdict == "нарушение":
            m = re.findall(r"(\d+)\s*мин", cells.get("B", ""))
            s = re.findall(r"(\d+)\s*сек", cells.get("B", ""))
            t = (int(m[0]) * 60 if m else 0) + (int(s[0]) if s else 0)
        out[norm_video_id(name)] = (verdict == "нарушение", t)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detections", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--tolerance", type=float, default=3.0, help="seconds for a 'timecode hit'")
    ap.add_argument("--include-test", action="store_true")
    args = ap.parse_args()

    labels = read_labels(args.labels)
    rows, by_split = [], {}
    fired = Counter()
    for path in sorted(args.detections.glob("X-*.json"), key=lambda p: int(p.stem[2:])):
        vid = norm_video_id(path.stem)
        split = split_of(vid)
        if is_duplicate(vid) or vid not in labels:
            continue
        if split == "test" and not args.include_test:
            print(f"refusing to score test video {vid} (use --include-test once, at the end)")
            continue
        res = rules.evaluate(json.loads(path.read_text(encoding="utf-8")))
        pred = bool(res.violations)
        truth, t_true = labels[vid]
        dt = min((abs(v.t - t_true) for v in res.violations), default=None) if truth and pred else None
        fired.update(v.rule for v in res.violations)
        rows.append((split, vid, truth, t_true, pred, dt, [f"{v.code}@{v.t:g}{'?' if v.needs_review else ''}"
                                                           for v in res.violations]))
        c = by_split.setdefault(split, Counter())
        c[("TP" if pred else "FN") if truth else ("FP" if pred else "TN")] += 1
        if dt is not None and dt <= args.tolerance:
            c["time_hit"] += 1

    print(f"{'split':6} {'video':6} {'label':>14} {'pred':>5} {'|dt|':>6}  events")
    for split, vid, truth, t_true, pred, dt, ev in rows:
        lab = f"violation@{t_true}" if truth else "clean"
        mark = "" if truth == pred else ("  <-- MISS" if truth else "  <-- FALSE ALARM")
        print(f"{split:6} {vid:6} {lab:>14} {('V' if pred else '-'):>5} {('' if dt is None else f'{dt:.1f}'):>6}  "
              f"{' '.join(ev)}{mark}")
    for split, c in sorted(by_split.items()):
        n = sum(c[k] for k in ("TP", "FP", "TN", "FN"))
        acc = (c["TP"] + c["TN"]) / n if n else 0
        print(f"\n{split}: {n} videos  TP {c['TP']}  FN {c['FN']}  FP {c['FP']}  TN {c['TN']}  "
              f"verdict accuracy {acc:.0%}  missed violations {c['FN']}/{c['TP'] + c['FN']}  "
              f"timecode within {args.tolerance:g}s {c['time_hit']}/{c['TP']}")
    print("\nrules fired:", dict(fired.most_common()))


if __name__ == "__main__":
    main()
