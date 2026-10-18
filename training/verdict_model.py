"""Second-opinion verdict model: violation / no violation per video, from pipeline features.

    python training/verdict_model.py --detections runs/v5/det_all --labels ../open/open_labels.xlsx --out runs/verdict

Features per video = statistics of the rule engine's smoothed signals (share of frames with the
safe open, cash on the desk, ...; counts of visits, entries and departures) plus which rules
fired. Model = L2-regularised logistic regression in NumPy (25 training videos: anything larger
would memorise them). Evaluated by leave-one-group-out on train (a recording group never sits on
both sides), then once on validation. Test videos are never used. It gives no type, timecode or
evidence, so it can only gate or second-guess the rule engine, not replace it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import rules  # noqa: E402

from eval_rules import read_labels  # noqa: E402
from splits import GROUPS, is_duplicate, norm_video_id, split_of  # noqa: E402

CODES = ("ID", "INCOMPLETE", "TABLE", "SAFE", "EXIT", "DOOR", "PERSONAL")


def features(doc: dict) -> tuple[dict[str, float], bool]:
    res = rules.evaluate(doc)
    fr = res.frames
    n = max(len(fr), 1)
    share = lambda pred: sum(1 for f in fr if pred(f)) / n  # noqa: E731
    feats = {
        "share_customer": share(lambda f: f.people >= 2),
        "share_empty": share(lambda f: f.people == 0),
        "share_door_open": share(lambda f: f.door == "open"),
        "share_safe_open": share(lambda f: f.safe == "open"),
        "share_laptop_open": share(lambda f: f.laptop == "open"),
        "share_cash_desk": share(lambda f: f.cash_desk > 0),
        "share_cash_counter": share(lambda f: f.cash_counter),
        "share_id": share(lambda f: f.id_card),
        "share_personal": share(lambda f: f.personal_desk),
        "max_cash_desk": max((f.cash_desk for f in fr), default=0),
        "n_visits": len(res.debug.get("visits", [])),
        "n_departures": len(res.debug.get("departures", [])),
        "cash_desk_at_end": float(fr[-1].cash_desk > 0) if fr else 0.0,
        "n_review": sum(v.needs_review for v in res.violations),
    }
    for c in CODES:
        feats[f"rule_{c}"] = float(any(v.code == c for v in res.violations))
    return feats, bool(res.violations)


def fit(X: np.ndarray, y: np.ndarray, l2: float, steps: int = 3000, lr: float = 0.1) -> np.ndarray:
    w = np.zeros(X.shape[1] + 1)
    Xb = np.hstack([X, np.ones((len(X), 1))])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-Xb @ w))
        grad = Xb.T @ (p - y) / len(y)
        grad[:-1] += l2 * w[:-1]  # no penalty on the bias
        w -= lr * grad
    return w


def predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(np.hstack([X, np.ones((len(X), 1))]) @ w)))


def group_of(vid: str) -> int:
    n = int(vid[2:])
    return next(i for i, g in enumerate(GROUPS) if n in g)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detections", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--l2", type=float, default=0.5)
    ap.add_argument("--threshold", type=float, default=0.35,
                    help="probability above which the model says violation; low on purpose (misses are worse)")
    args = ap.parse_args()

    labels = read_labels(args.labels)
    data = {}
    for path in sorted(args.detections.glob("X-*.json"), key=lambda p: int(p.stem[2:])):
        vid = norm_video_id(path.stem)
        if is_duplicate(vid) or vid not in labels or split_of(vid) == "test":
            continue
        feats, rule_says = features(json.loads(path.read_text(encoding="utf-8")))
        data[vid] = (feats, rule_says, labels[vid][0], split_of(vid))
    names = list(next(iter(data.values()))[0])
    train = [v for v in data if data[v][3] == "train"]
    valid = [v for v in data if data[v][3] == "valid"]
    mat = lambda vids: np.array([[data[v][0][k] for k in names] for v in vids], dtype=float)  # noqa: E731
    lab = lambda vids: np.array([float(data[v][2]) for v in vids])  # noqa: E731

    Xtr, ytr = mat(train), lab(train)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    norm = lambda X: (X - mu) / sd  # noqa: E731

    # Leave-one-group-out on train.
    groups = np.array([group_of(v) for v in train])
    oof = np.zeros(len(train))
    for g in np.unique(groups):
        tr, te = groups != g, groups == g
        m, s = Xtr[tr].mean(0), Xtr[tr].std(0) + 1e-6
        w = fit((Xtr[tr] - m) / s, ytr[tr], args.l2)
        oof[te] = predict(w, (Xtr[te] - m) / s)

    w = fit(norm(Xtr), ytr, args.l2)
    pva = predict(w, norm(mat(valid))) if valid else np.array([])

    def report(name, vids, prob):
        y = lab(vids)
        model = prob >= args.threshold
        rule = np.array([data[v][1] for v in vids])
        both = model & rule
        for tag, pred in (("rules only", rule), ("model only", model), ("rules AND model", both)):
            tp = int(((pred == 1) & (y == 1)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
            fp = int(((pred == 1) & (y == 0)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
            print(f"  {name:22} {tag:16} acc {(tp + tn) / len(y):4.0%}  missed {fn}/{tp + fn}  false alarms {fp}/{fp + tn}")
        for v, p in zip(vids, prob):
            flag = "V" if p >= args.threshold else "-"
            print(f"    {v:5} label {'V' if data[v][2] else '-'}  rules {'V' if data[v][1] else '-'}  model {flag} ({p:.2f})")

    print(f"{len(train)} train / {len(valid)} valid videos, {len(names)} features, l2={args.l2}, threshold={args.threshold}")
    report("train (leave-group-out)", train, oof)
    report("valid", valid, pva)

    order = np.argsort(-np.abs(w[:-1]))
    print("\nstrongest features (standardised weight):")
    for i in order[:8]:
        print(f"  {names[i]:20} {w[i]:+.2f}")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "verdict_model.json").write_text(json.dumps({
        "features": names, "mean": mu.tolist(), "std": sd.tolist(), "weights": w.tolist(),
        "threshold": args.threshold, "l2": args.l2, "trained_on": train,
        "detections": str(args.detections)}, indent=1), encoding="utf-8")
    print(f"\nsaved {args.out / 'verdict_model.json'}")


if __name__ == "__main__":
    main()
