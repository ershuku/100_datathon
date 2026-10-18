"""Unit tests: legal lookup, citation suffix, review policy, public view shape."""

from __future__ import annotations

import time

from app.analysis.legal import LegalCatalog
from app.analysis.port import DetectedEvent, EvidenceRef
from app.config import ReviewPolicy
from app.jobs.store import JobRecord
from app.results import apply_review_policy, public_view, stored_result, stored_violation, ui_view
from conftest import REPO

YAML = """
version: 1
types:
  SAFE: {name: Сейф не закрыт, document: Правила ведения кассовых операций, punkt: "12", rule_text: x, url: ""}
  DOOR: {name: Дверь кассы открыта, document: TODO, punkt: TODO}
  EXIT: {name: Рабочее место не закрыто, document: TODO, punkt: TODO, rule_id: R-7}
rules:
  R-7: {document: Инструкция, punkt: "раздел 3"}
"""


def _catalog(tmp_path) -> LegalCatalog:
    p = tmp_path / "rules.yaml"
    p.write_text(YAML, encoding="utf-8")
    return LegalCatalog.load(p)


def _event(code: str, **kw) -> DetectedEvent:
    return DetectedEvent(type_code=code, timecode_sec=12.34, description="Видно X.",
                         evidence=(EvidenceRef(12.3),), **kw)  # fmt: skip


def _done_record(result: dict) -> JobRecord:
    now = time.time()
    return JobRecord(id="0123456789abcdef", status="done", stage="done", stage_text="", progress=100, error=None,
                     error_code=None, created_at=now, started_at=now, finished_at=now, video_meta={},
                     result=result, files_deleted=False)  # fmt: skip


FRAME = [{"timestamp_sec": 12.3, "jpeg_base64": "/9j/AA=="}]


def test_filled_rule_is_appended_to_public_description(tmp_path):
    v = stored_violation(_event("SAFE"), _catalog(tmp_path), FRAME)
    body = public_view(_done_record(stored_result([v], partial=False, debug={}))).model_dump()
    assert body["violations"][0]["description"] == "Видно X. Правило: Правила ведения кассовых операций, п. 12."
    assert body["violations"][0]["type"] == "Сейф не закрыт"
    assert body["violations"][0]["timecode_sec"] == 12.3


def test_todo_rule_is_never_shown(tmp_path):
    v = stored_violation(_event("DOOR"), _catalog(tmp_path), FRAME)
    assert v["legal_ref"] is None
    body = public_view(_done_record(stored_result([v], partial=False, debug={}))).model_dump()
    assert "TODO" not in body["violations"][0]["description"]


def test_source_url_is_shared_by_public_description_and_ui(tmp_path):
    # Synthetic mapping: this tests plumbing, not the applicability of a real provision.
    source = "https://adilet.zan.kz/rus/docs/SYNTHETIC_TEST"
    p = tmp_path / "rules.yaml"
    p.write_text(YAML.replace('url: ""', f'url: "{source}"'), encoding="utf-8")
    v = stored_violation(_event("SAFE"), LegalCatalog.load(p), FRAME)
    rec = _done_record(stored_result([v], partial=False, debug={}))
    public = public_view(rec).model_dump()
    ui = ui_view(rec, queue_position=None, preview_available=False).model_dump()

    assert public["violations"][0]["description"] == (
        "Видно X. Правило: Правила ведения кассовых операций, п. 12. "
        f"Источник: {source}"
    )
    assert ui["violations"][0]["legal_ref"]["url"] == source
    assert set(public["violations"][0]) == {"type", "timecode_sec", "description", "evidence_frames"}


def test_rule_id_resolution_and_section_prefix(tmp_path):
    catalog = _catalog(tmp_path)
    assert catalog.legal_ref("EXIT").citation() == "Правило: Инструкция, раздел 3."
    assert catalog.legal_ref("DOOR", rule_id="R-7").document == "Инструкция"


def test_unknown_type_code_uses_fallback_name(tmp_path):
    v = stored_violation(_event("NEW", type_name="Новый тип"), _catalog(tmp_path), FRAME)
    assert v["type"] == "Новый тип" and v["legal_ref"] is None


def test_review_policy():
    events = (_event("SAFE"), _event("DOOR", needs_review=True))
    assert len(apply_review_policy(events, ReviewPolicy.REPORT)) == 2
    assert [e.type_code for e in apply_review_policy(events, ReviewPolicy.DROP)] == ["SAFE"]


def test_verdict_derived_from_violations():
    assert stored_result([], partial=False, debug={})["verdict"] == "no_violation"
    body = public_view(_done_record(stored_result([], partial=False, debug={}))).model_dump()
    assert body == {"job_id": "0123456789abcdef", "status": "done", "verdict": "no_violation", "violations": []}


def test_catalog_preserves_original_codes_and_requires_workstation_context():
    catalog = LegalCatalog.load(REPO / "config" / "rules_legal.yaml")
    assert set(catalog.types) >= {"ID", "THIRD", "TABLE", "INCOMPLETE", "NOCOUNT", "REJECT", "SAFE", "EXIT",
                                  "DOOR", "PERSONAL"}  # fmt: skip


    assert catalog.legal_ref("EXIT") is None
    assert catalog.legal_ref("TABLE").url == "https://adilet.zan.kz/rus/docs/V1900019680"
    assert catalog.legal_ref("DOOR", "PREMISES_ACCESS").url == "https://adilet.zan.kz/rus/docs/V2000020075"
    assert "2027" in catalog.legal_ref("DOOR", "PREMISES_ACCESS").citation()
    assert "Ограничения применимости:" in catalog.legal_ref("TABLE").citation()


def test_catalog_preserves_applicability_evidence_and_no_criminal_auto_match():
    import yaml
    from urllib.parse import urlparse

    data = yaml.safe_load((REPO / "config" / "rules_legal.yaml").read_text())
    for rule in data["rules"].values():
        assert rule["required_observations"] and rule["limitations"]
        assert urlparse(rule["url"]).hostname == "adilet.zan.kz"
    assert data["sources"]["CRIMINAL_190"]["auto_match"] is False
    assert all("190" not in rule["punkt"] for rule in data["rules"].values())
    for entry in data["types"].values():
        if "rule_id" in entry:
            assert entry["rule_id"] in data["rules"]


def test_ambiguous_types_need_explicit_rule_and_invalid_rule_does_not_fallback():
    catalog = LegalCatalog.load(REPO / "config" / "rules_legal.yaml")
    for code in ("ID", "THIRD", "SAFE", "DOOR"):
        assert catalog.legal_ref(code) is None
    assert catalog.legal_ref("TABLE", "MISSING_RULE") is None
    ref = catalog.legal_ref("DOOR", "PREMISES_ACCESS")
    assert "Возможное основание" in ref.citation()
    assert "применимость требует проверки" in ref.citation()


def test_expanded_types_resolve_only_explicit_curated_rules():
    import yaml

    data = yaml.safe_load((REPO / "config" / "rules_legal.yaml").read_text())
    catalog = LegalCatalog.load(REPO / "config" / "rules_legal.yaml")
    for code, entry in data["types"].items():
        for rid in entry["allowed_rule_ids"]:
            ref = catalog.legal_ref(code, rid)
            assert ref is not None, (code, rid)
            assert ref.url == data["sources"][data["rules"][rid]["source_id"]]["url"]
            assert "Возможное основание" in ref.citation()
        if entry.get("requires_rule_id"):
            assert catalog.legal_ref(code) is None, code


def test_extended_categories_preserve_public_shape_and_evidence():
    catalog = LegalCatalog.load(REPO / "config" / "rules_legal.yaml")
    for code, rid in [("COUNT_OUT", "CASH_COUNT_OUT"), ("ATM_CASSETTE", "CASH_ATM_CASSETTE"),
                      ("EXIT", "IS_SESSION_TIMEOUT"), ("BAG", "CASH_BAG")]:
        v = stored_violation(_event(code, rule_id=rid), catalog, FRAME)
        body = public_view(_done_record(stored_result([v], partial=False, debug={}))).model_dump()
        item = body["violations"][0]
        assert set(item) == {"type", "timecode_sec", "description", "evidence_frames"}
        assert item["evidence_frames"][0]["image_base64"] == FRAME[0]["jpeg_base64"]
        assert item["timecode_sec"] == 12.3
        assert catalog.legal_ref(code, rid).url in item["description"]


def test_team_classes_preserved_without_automatic_legal_conclusions():
    catalog = LegalCatalog.load(REPO / "config" / "rules_legal.yaml")
    assert set(catalog.classifications) == {*(f"V{i}" for i in range(1, 15)), "V1b"}
    for label, mapping in catalog.classifications.items():
        assert mapping.conditions and mapping.limitations
        assert catalog.legal_ref(label) is None
        for rid in mapping.candidate_rule_ids:
            assert catalog.legal_ref(label, rid) is not None
    assert catalog.classifications["V12"].status == "observation_only"
    assert catalog.legal_ref("V12", "CASH_PRESENT") is None
    assert catalog.legal_ref("V14", "CASH_LEAVE") is None
    timeout = catalog.legal_ref("V14", "IS_SESSION_TIMEOUT")
    assert "72" in timeout.punkt and "72" in timeout.limitations


def test_observation_only_candidate_cannot_trigger_public_violation():
    import pytest

    catalog = LegalCatalog.load(REPO / "config" / "rules_legal.yaml")
    for code in ("V12", "CASH_RETURN"):
        with pytest.raises(ValueError, match="Observation-only"):
            stored_violation(_event(code, rule_id="CASH_PRESENT"), catalog, FRAME)


def test_empty_description_gets_a_non_empty_fallback(tmp_path):
    event = DetectedEvent(type_code="SAFE", timecode_sec=1.0, description="  ", evidence=(EvidenceRef(1.0),))
    v = stored_violation(event, _catalog(tmp_path), FRAME)
    assert v["description"].startswith("Обнаружен момент") and "Сейф не закрыт" in v["description"]
