"""Rule engine on synthetic detector frames (no model, no dataset footage)."""

from __future__ import annotations

from pipeline import rules

W, H = 464, 848
COUNTER = [200, 400, 260, 460]
LAPTOP = [120, 400, 180, 450]
SAFE = [300, 250, 380, 350]
DOOR = [0, 0, 140, 430]
CASHIER = [150, 300, 250, 600]
CUSTOMER = [300, 500, 420, 800]


def det(label, box, score=0.9):
    return {"label": label, "score": score, "box_xyxy": box}


def scene(seconds, fps=5, **spans):
    """spans: name -> list of (t0, t1) when that thing is visible; furniture always present."""
    frames = []
    for i in range(int(seconds * fps)):
        t = i / fps
        on = {k: any(a <= t < b for a, b in v) for k, v in spans.items()}
        d = [det("counter_machine", COUNTER), det("door_closed" if not on.get("door_open") else "door_open", DOOR),
             det("safe_open" if on.get("safe_open") else "safe_closed", SAFE),
             det("laptop_open" if on.get("laptop_open", True) else "laptop_closed", LAPTOP)]
        if on.get("cashier", True):
            d.append(det("person", CASHIER))
        if on.get("customer"):
            d.append(det("person", CUSTOMER))
        if on.get("reflection"):
            d.append(det("person", [10, 50, 120, 300], score=0.4))  # faint figure in the glass door
        if on.get("id"):
            d.append(det("id_card", [250, 480, 270, 495]))
        if on.get("cash_desk"):
            d.append(det("cash_stack", [150, 460, 190, 480]))
        if on.get("cash_counter"):
            d.append(det("cash_stack", [210, 410, 250, 440]))
        if on.get("personal"):
            d.append(det("personal_item", [130, 470, 150, 490]))
        frames.append({"frame_index": i * 6, "pts_sec": round(t, 2), "width": W, "height": H, "detections": d})
    return {"frames": frames, "sampling": {"target_fps": fps}}


def codes(doc):
    return sorted({v.code for v in rules.evaluate(doc).violations})


def test_clean_deposit_has_no_violation():
    doc = scene(30, customer=[(2, 25)], id=[(4, 7)], cash_desk=[(8, 10), (14, 17)], cash_counter=[(10, 14)],
                safe_open=[(17, 20)])
    assert codes(doc) == []


def test_cash_without_id_is_flagged_at_handover():
    doc = scene(30, customer=[(2, 25)], cash_desk=[(8, 10), (14, 17)], cash_counter=[(10, 14)], safe_open=[(17, 20)])
    v = [x for x in rules.evaluate(doc).violations if x.code == "ID"]
    assert v and 7.5 <= v[0].t <= 9.0 and 1 <= len(v[0].evidence) <= 3


def test_customer_leaves_with_cash_on_desk():
    doc = scene(30, customer=[(2, 15)], id=[(4, 7)], cash_desk=[(8, 30)])
    assert "INCOMPLETE" in codes(doc)


def test_clip_ending_with_customer_present_is_in_progress_not_violation():
    doc = scene(15, customer=[(2, 15)], id=[(4, 7)], cash_desk=[(8, 15)])
    assert "INCOMPLETE" not in codes(doc)


def test_next_customer_while_previous_cash_on_desk():
    doc = scene(40, customer=[(2, 15), (20, 38)], id=[(4, 7), (22, 24)], cash_desk=[(8, 40)])
    assert "TABLE" in codes(doc)


def test_safe_open_while_counting():
    doc = scene(20, safe_open=[(0, 20)], cash_counter=[(8, 14)])
    assert "SAFE" in codes(doc)


def test_safe_closed_before_counting_is_fine():
    doc = scene(20, safe_open=[(0, 5)], cash_counter=[(8, 14)])
    assert "SAFE" not in codes(doc)


def test_leaving_with_laptop_open():
    doc = scene(20, cashier=[(0, 12)], laptop_open=[(0, 20)])
    assert "EXIT" in codes(doc)


def test_leaving_properly():
    doc = scene(20, cashier=[(0, 12)], laptop_open=[(0, 8)])
    assert codes(doc) == []


def test_door_left_open_while_working():
    doc = scene(20, cashier=[(2, 20)], door_open=[(1, 20)])
    assert "DOOR" in codes(doc)


def test_door_open_only_while_entering_is_fine():
    doc = scene(20, cashier=[(2, 20)], door_open=[(1, 5)])
    assert "DOOR" not in codes(doc)


def test_cashier_seen_through_glass_before_door_opens():
    # detected at 1 s, door only opens at 3 s and never closes again: still a violation
    doc = scene(20, cashier=[(1, 20)], door_open=[(3, 20)])
    assert "DOOR" in codes(doc)


def test_cashier_already_working_at_clip_start_gives_no_entry_to_judge():
    doc = scene(20, door_open=[(0, 20)])
    assert "DOOR" not in codes(doc)


def test_glass_reflection_is_not_a_customer():
    doc = scene(20, reflection=[(0, 20)], cash_desk=[(5, 20)])
    assert rules.evaluate(doc).debug["visits"] == []


def test_personal_items_next_to_cash():
    doc = scene(20, personal=[(5, 15)], cash_desk=[(4, 16)])
    assert "PERSONAL" in codes(doc)
