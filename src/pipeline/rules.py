"""Rule engine: detector frames -> smoothed scene signals -> events -> violations.

Pure Python on purpose (no torch): it runs on the tracker-format detector JSON, so rules can be
tested and tuned offline on CPU. Design follows Aibar.md:

- Deadlines are events, never timers: "before the customer leaves", "before the next customer
  enters", "before the cashier leaves", "before counting starts". The only time constants here
  are perception debounces (a state must hold for ~1 s of sampled frames before it counts),
  which filter detector flicker and are not rule deadlines.
- Every rule runs on its own; one violation never suppresses another.
- Weak or contradictory evidence produces needs_review=True instead of a silent "compliant".
- A clip that ends with an obligation still pending is "in progress", not a violation.

Roles are inferred from people count: 0 = room empty, 1 = cashier alone, >=2 = cashier with a
customer (or collector). Only confident person boxes count (glass-door reflections score lower).
Not implemented yet (need counter-machine states / ID-to-person matching):
NOCOUNT, REJECT, THIRD.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

DEBOUNCE_FRAMES = 5  # ~1 s at 5 fps: a state must persist this long to count as a change
PERSON_MIN_SCORE = 0.5  # detector threshold is 0.35; people need more, reflections score low
PERSONAL_MIN_SCORE = 0.55  # personal_item over-fires on desk clutter at low scores

DESCRIPTIONS = {
    "ID": "Клиент передаёт наличные (или сумку) кассиру, но предъявление удостоверения личности "
          "до приёма на видео не наблюдается.",
    "INCOMPLETE": "Клиент уходит, когда принятые наличные ещё на столе и не убраны в сейф.",
    "TABLE": "К кассе подходит следующий клиент, а на столе остаются наличные предыдущего клиента.",
    "SAFE_OPEN": "Сейф открыт, пока кассир пересчитывает наличные на счётной машинке.",
    "SAFE_EXIT": "Кассир покидает рабочее место, сейф остаётся открытым.",
    "SAFE_KEYS": "Кассир покидает рабочее место, ключи остаются в замке сейфа.",
    "EXIT_LAPTOP": "Кассир покидает рабочее место, ноутбук остаётся открытым.",
    "EXIT_ITEMS": "Кассир покидает рабочее место, на столе остаются {items}.",
    "DOOR": "Кассир находится на рабочем месте, входная дверь кассы остаётся открытой.",
    "PERSONAL": "На рабочем столе рядом с наличными находятся личные вещи кассира.",
}
ITEM_NAMES = {"cash_stack": "наличные", "journal": "журнал", "cash_bag": "сумка"}


@dataclass
class Frame:
    t: float
    people: int = 0
    door: str | None = None  # "open" | "closed" | None (not seen)
    safe: str | None = None
    laptop: str | None = None
    cash_desk: int = 0  # cash stacks on the desk area
    cash_counter: bool = False  # cash overlapping the counting machine
    id_card: bool = False
    bag: bool = False
    journal: bool = False
    personal_desk: bool = False
    keys_in_safe: bool = False


@dataclass(frozen=True)
class Violation:
    code: str  # type key in config/rules_legal.yaml
    t: float
    description: str
    evidence: tuple[float, ...]
    needs_review: bool = False
    rule: str = ""  # internal rule name, for debug/eval
    rule_id: str | None = None  # catalogue rule; several types (ID, SAFE, EXIT, DOOR, ...) cite only with it


# Internal rule -> (catalogue type, catalogue rule_id), following the class mapping in
# pipeline_law_projection.md §2 (generated from config/rules_legal.yaml). The catalogue, not this
# code, holds the legal text; a missing or disallowed rule_id means no citation is shown.
CATALOGUE = {
    "id_before_cash": ("ID", "CASH_ID_IN"),                       # V1, ПКО п. 19 пп. 1)
    "id_after_cash": ("ID", "CASH_ID_IN"),
    "customer_left_cash_unsecured": ("INCOMPLETE", "CASH_PRESENT"),  # V6, ПКО п. 20 абз. 1
    "customer_left_during_count": ("INCOMPLETE", "CASH_PRESENT"),
    "table_on_next_customer": ("TABLE", "CASH_STORAGE"),          # V2, ПКО п. 20
    "safe_open_while_counting": ("SAFE", "CASH_STORAGE"),         # V4, ПКО п. 20
    "left_safe_open": ("SAFE", "CASH_STORAGE"),
    "left_keys_in_safe": ("KEYS", "CASH_KEYS"),                   # V5, ПКО п. 76, 80
    "left_laptop_open": ("EXIT", "IS_SESSION_TIMEOUT"),           # V14, ТИБ п. 71 пп. 9) — needs records
    "left_cash_on_desk": ("TABLE", "CASH_STORAGE"),               # V3, ПКО п. 20
    "left_journal_on_desk": ("UNATTENDED_ITEMS", "IS_PAPER_PROTECTION"),  # V13
    "left_bag_on_desk": ("UNATTENDED_ITEMS", "CASH_KEYS"),       # V13 (ценности, п. 80)
    "door_open_while_working": ("DOOR", "PREMISES_ACCESS"),       # V11, ПОУП п. 8, 16 пп. 1)
    "personal_items_with_cash": ("PERSONAL", "CASH_PERSONAL"),    # V8, ПКО п. 12
}


@dataclass
class Result:
    violations: list[Violation]
    frames: list[Frame]
    debug: dict = field(default_factory=dict)


# ---------------------------------------------------------------- geometry

def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    return _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def _inside_frac(a, b):
    """Share of box a that lies inside box b."""
    return _inter(a, b) / _area(a) if _area(a) else 0.0


def _center_in(a, b):
    cx, cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    return b[0] <= cx <= b[2] and b[1] <= cy <= b[3]


def _grow(b, frac, w, h):
    dx, dy = (b[2] - b[0]) * frac, (b[3] - b[1]) * frac
    return [max(0, b[0] - dx), max(0, b[1] - dy), min(w, b[2] + dx), min(h, b[3] + dy)]


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


# ---------------------------------------------------------------- per-frame signals

def _best(dets, labels):
    cands = [d for d in dets if d["label"] in labels]
    return max(cands, key=lambda d: d["score"]) if cands else None


def frame_signals(raw: dict, desk_zone: list[float] | None) -> Frame:
    dets = raw["detections"]
    w, h = raw.get("width", 10_000), raw.get("height", 10_000)
    door = _best(dets, ("door_open", "door_closed"))
    safe = _best(dets, ("safe_open", "safe_closed"))
    laptop = _best(dets, ("laptop_open", "laptop_closed"))
    counter = _best(dets, ("counter_machine",))
    f = Frame(t=raw["pts_sec"])
    f.door = door["label"].split("_")[1] if door else None
    f.safe = safe["label"].split("_")[1] if safe else None
    f.laptop = laptop["label"].split("_")[1] if laptop else None
    # People: confident boxes only (glass-door reflections score lower), and boxes that mostly
    # overlap an already counted person are the same person. Note: a door-box filter does not work
    # here; from the overhead camera the door lies behind the cashier in the image.
    people: list[list[float]] = []
    for d in sorted((d for d in dets if d["label"] == "person"), key=lambda d: -d["score"]):
        if d["score"] >= PERSON_MIN_SCORE and all(_inside_frac(d["box_xyxy"], p) < 0.5 for p in people):
            people.append(d["box_xyxy"])
    f.people = len(people)
    zone = desk_zone or [0, 0, w, h]
    for d in dets:
        b, lab = d["box_xyxy"], d["label"]
        if lab == "cash_stack":
            if counter and _inside_frac(b, _grow(counter["box_xyxy"], 0.15, w, h)) > 0.5:
                f.cash_counter = True
            elif _center_in(b, zone) and not (safe and _inside_frac(b, safe["box_xyxy"]) > 0.5):
                f.cash_desk += 1
        elif lab == "id_card":
            f.id_card = True
        elif lab == "cash_bag" and _center_in(b, zone):
            f.bag = True
        elif lab == "journal" and _center_in(b, zone):
            f.journal = True
        elif lab == "personal_item" and d["score"] >= PERSONAL_MIN_SCORE and _center_in(b, zone):
            f.personal_desk = True
        elif lab == "keys" and safe and _inter(b, _grow(safe["box_xyxy"], 0.1, w, h)) > 0:
            f.keys_in_safe = True
    return f


def desk_zone_of(frames: list[dict]) -> list[float] | None:
    """The work surface: around the (static) counting machine and laptop, median over the video."""
    boxes = []
    for raw in frames:
        parts = [d["box_xyxy"] for d in raw["detections"] if d["label"] in ("counter_machine", "laptop_open", "laptop_closed")]
        if parts:
            boxes.append(_union(parts))
    if not boxes:
        return None
    med = [median(b[i] for b in boxes) for i in range(4)]
    w, h = frames[0].get("width", 10_000), frames[0].get("height", 10_000)
    return _grow(med, 0.6, w, h)


def _smooth(frames: list[Frame], k: int) -> list[Frame]:
    """Centered majority (categorical/bool) and median (counts) over 2k+1 frames."""
    out = []
    for i, f in enumerate(frames):
        win = frames[max(0, i - k): i + k + 1]
        g = Frame(t=f.t)
        for name in ("door", "safe", "laptop"):
            vals = [getattr(x, name) for x in win if getattr(x, name) is not None]
            setattr(g, name, Counter(vals).most_common(1)[0][0] if vals else None)
        for name in ("people", "cash_desk"):
            setattr(g, name, int(median(getattr(x, name) for x in win)))
        for name in ("cash_counter", "id_card", "bag", "journal", "personal_desk", "keys_in_safe"):
            setattr(g, name, sum(getattr(x, name) for x in win) * 2 > len(win))
        out.append(g)
    return out


# ---------------------------------------------------------------- segments and visits

def _runs(frames: list[Frame], pred) -> list[tuple[int, int]]:
    """Index ranges [start, end] where pred holds."""
    runs, start = [], None
    for i, f in enumerate(frames):
        if pred(f):
            start = i if start is None else start
        elif start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(frames) - 1))
    return runs


def _evidence(frames: list[Frame], i: int) -> tuple[float, ...]:
    idx = sorted({max(0, i - 3), i, min(len(frames) - 1, i + 3)})
    return tuple(round(frames[j].t, 2) for j in idx)


def _v(code, rule, frames, i, text, review=False):
    code, rule_id = CATALOGUE.get(rule, (code, None))
    return Violation(code, round(frames[i].t, 1), text, _evidence(frames, i), review, rule, rule_id)


# ---------------------------------------------------------------- rules

def rule_customer(frames: list[Frame]) -> list[Violation]:
    """ID before accepting cash; cash secured before the customer leaves / the next one enters."""
    out = []
    visits = _runs(frames, lambda f: f.people >= 2)
    prev_had_cash = False
    for n, (s, e) in enumerate(visits):
        base = frames[s].cash_desk
        id_at = next((i for i in range(s, e + 1) if frames[i].id_card), None)
        cash_at = next((i for i in range(s, e + 1)
                        if frames[i].cash_desk > base or frames[i].cash_counter or frames[i].bag), None)
        # Next customer enters while cash from the previous visit is still on the desk.
        if n > 0 and prev_had_cash and frames[s].cash_desk > 0:
            out.append(_v("TABLE", "table_on_next_customer", frames, s, DESCRIPTIONS["TABLE"]))
        if cash_at is not None:
            if id_at is None:
                # Behind/front views can hide the ID: flagged, but kept for review when the
                # customer was only briefly visible before the hand-over.
                out.append(_v("ID", "id_before_cash", frames, cash_at, DESCRIPTIONS["ID"],
                              review=cash_at - s < DEBOUNCE_FRAMES))
            elif id_at > cash_at:
                out.append(_v("ID", "id_after_cash", frames, cash_at, DESCRIPTIONS["ID"], review=True))
            left = e < len(frames) - 1  # the clip ending is not a departure
            safe_used = any(frames[i].safe == "open" for i in range(cash_at, e + 1))
            if left and frames[e].cash_desk > 0 and not safe_used:
                out.append(_v("INCOMPLETE", "customer_left_cash_unsecured", frames, e, DESCRIPTIONS["INCOMPLETE"]))
            elif left and frames[e].cash_counter:
                out.append(_v("INCOMPLETE", "customer_left_during_count", frames, e, DESCRIPTIONS["INCOMPLETE"]))
        prev_had_cash = cash_at is not None or frames[e].cash_desk > 0
    return out


def rule_safe_open_while_counting(frames: list[Frame]) -> list[Violation]:
    """After a withdrawal the safe must be closed before counting resumes: counting that STARTS
    while the safe is open. In a deposit the cash is still in the machine when the safe is opened
    to store it, which is fine, so the counter must be empty when the safe opens."""
    for s, e in _runs(frames, lambda f: f.safe == "open"):
        if frames[s].cash_counter:
            continue
        for i in range(s, e + 1):
            if frames[i].cash_counter and frames[i].people >= 1:
                return [_v("SAFE", "safe_open_while_counting", frames, i, DESCRIPTIONS["SAFE_OPEN"])]
    return []


def rule_departure(frames: list[Frame]) -> list[Violation]:
    """At cashier departure: safe closed, keys taken, laptop closed, desk cleared."""
    out = []
    empty = _runs(frames, lambda f: f.people == 0)
    for s, e in empty:
        if s == 0:
            continue  # room empty from the start: no departure observed
        i = s - 1  # last frame with the cashier present
        # Look at the state just after leaving (furniture is easier to see without the cashier).
        j = min(e, s + DEBOUNCE_FRAMES)
        after = frames[s: j + 1]
        if any(f.safe == "open" for f in after):
            out.append(_v("SAFE", "left_safe_open", frames, i, DESCRIPTIONS["SAFE_EXIT"]))
        if any(f.keys_in_safe for f in after):
            out.append(_v("SAFE", "left_keys_in_safe", frames, i, DESCRIPTIONS["SAFE_KEYS"], review=True))
        # The catalogue's session rule needs system records (> 30 min inactivity); video alone
        # cannot confirm it, so the open laptop is reported for review.
        if sum(f.laptop == "open" for f in after) * 2 > len(after):
            out.append(_v("EXIT", "left_laptop_open", frames, i, DESCRIPTIONS["EXIT_LAPTOP"], review=True))
        # Each item is its own event with its own catalogue rule: cash -> storage rule; a journal or
        # bag is not automatically a regulated value (catalogue V13 limitation) -> review.
        for item, attr, rule, review in (("cash_stack", "cash_desk", "left_cash_on_desk", False),
                                         ("journal", "journal", "left_journal_on_desk", True),
                                         ("cash_bag", "bag", "left_bag_on_desk", True)):
            if sum(bool(getattr(f, attr)) for f in after) * 2 > len(after):
                text = DESCRIPTIONS["EXIT_ITEMS"].format(items=ITEM_NAMES[item])
                out.append(_v("EXIT", rule, frames, i, text, review=review))
    return out


def rule_door(frames: list[Frame]) -> list[Violation]:
    """Room entry: enter -> close the entrance door -> start work (Aibar.md §10). Applies only to an
    OBSERVED entry (room empty, then the cashier is present); a cashier already at work when the
    clip starts gives no entry to judge. The cashier is often detected through the glass before
    the door opens, so what matters is what happens AFTER the door has been opened: compliant if it
    is then seen closed again (stably); otherwise the cashier works with the door open, flagged at
    the first stable open moment once nobody is still coming through."""
    for s, _ in _runs(frames, lambda f: f.people >= 1):
        if s == 0 or frames[s - 1].people != 0:
            continue
        # The entry opening may start a moment before the cashier is first detected.
        start = max(0, s - 2 * DEBOUNCE_FRAMES)
        after = frames[start:]
        opened = next((b for b, e in _runs(after, lambda f: f.door == "open") if e - b + 1 > DEBOUNCE_FRAMES), None)
        if opened is None:
            continue
        if any(e - b + 1 > DEBOUNCE_FRAMES for b, e in _runs(after[opened:], lambda f: f.door == "closed")):
            continue
        for k in range(opened, len(after)):
            f = after[k]
            settled = all(g.people == f.people for g in after[max(0, k - DEBOUNCE_FRAMES): k + 1])
            if f.door == "open" and f.people >= 1 and settled:
                return [_v("DOOR", "door_open_while_working", frames, start + k, DESCRIPTIONS["DOOR"])]
    return []


def rule_personal(frames: list[Frame]) -> list[Violation]:
    """No personal belongings on the work surface while cash is being handled there. Only while the
    cashier is alone: during a visit the wallet/phone on the desk is usually the customer's."""
    for s, e in _runs(frames, lambda f: f.personal_desk and f.people == 1 and (f.cash_desk > 0 or f.cash_counter)):
        if e - s + 1 > DEBOUNCE_FRAMES:
            return [_v("PERSONAL", "personal_items_with_cash", frames, s, DESCRIPTIONS["PERSONAL"])]
    return []


RULES = (rule_customer, rule_safe_open_while_counting, rule_departure, rule_door, rule_personal)


def evaluate(doc: dict) -> Result:
    """doc: tracker-format detector JSON ({"frames": [...], "sampling": {...}, ...})."""
    raw = doc["frames"]
    if not raw:
        return Result([], [], {"reason": "no frames"})
    zone = desk_zone_of(raw)
    frames = _smooth([frame_signals(r, zone) for r in raw], DEBOUNCE_FRAMES // 2)
    violations = sorted((v for rule in RULES for v in rule(frames)), key=lambda v: v.t)
    debug = {
        "desk_zone": [round(x, 1) for x in zone] if zone else None,
        "visits": [(round(frames[s].t, 1), round(frames[e].t, 1)) for s, e in _runs(frames, lambda f: f.people >= 2)],
        "departures": [round(frames[s - 1].t, 1) for s, _ in _runs(frames, lambda f: f.people == 0) if s > 0],
        "rules_fired": [v.rule for v in violations],
        "not_implemented": ["NOCOUNT", "REJECT", "THIRD"],
    }
    return Result(violations, frames, debug)
