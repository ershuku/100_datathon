"""Synthetic class-to-rule mappings: selection never proves applicability."""

import pytest
import yaml

from app.analysis.legal import LegalCatalog
from app.analysis.port import DetectedEvent, EvidenceRef
from app.results import public_view, stored_result, stored_violation
from test_results import _done_record


def _config():
    return {
        "types": {
            "SAFE": {"name": "Canonical safe", "allowed_rule_ids": ["A", "B"], "requires_rule_id": True},
            "OTHER": {"name": "Other", "allowed_rule_ids": ["C"]},
            "LEGACY": {"name": "Legacy"},
        },
        "rules": {rid: {"document": "Synthetic", "punkt": rid} for rid in ("A", "B", "C")},
        "classifications": {
            "V1": {"name": "Class one", "type_code": "SAFE", "candidate_rule_ids": ["A", "B"],
                   "status": "conditional", "conditions": ["Human verifies context"], "limitations": "Not automatic"},
            "V12": {"name": "No basis", "type_code": "SAFE", "candidate_rule_ids": [],
                    "status": "unmapped", "conditions": [], "limitations": []},
        },
    }


def _load(tmp_path, config=None):
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(_config() if config is None else config), encoding="utf-8")
    return LegalCatalog.load(path)


def test_classes_require_explicit_candidate_and_preserve_conditions(tmp_path):
    catalog = _load(tmp_path)
    assert catalog.type_name("V1") == "Canonical safe"
    assert catalog.legal_ref("V1") is None
    assert catalog.legal_ref("V1", "A").punkt == "A"
    assert catalog.legal_ref("V1", "B").punkt == "B"
    assert catalog.classifications["V1"].conditions == ("Human verifies context",)
    assert catalog.classifications["V1"].limitations == ("Not automatic",)
    assert catalog.legal_ref("V12") is None
    assert catalog.legal_ref("V12", "A") is None


def test_unrelated_unknown_and_legacy_rules(tmp_path):
    catalog = _load(tmp_path)
    for code, rule in (("V1", "C"), ("SAFE", "C"), ("UNKNOWN", "A"), ("V1", "MISSING")):
        assert catalog.legal_ref(code, rule) is None
    assert catalog.legal_ref("LEGACY", "C").punkt == "C"
    assert catalog.type_name("UNKNOWN", "Fallback") == "Fallback"


@pytest.mark.parametrize("invalid", ["candidate", "type", "allowlist", "default", "disallowed", "list_shape"])
def test_invalid_mappings_are_rejected(tmp_path, invalid):
    config = _config()
    if invalid == "candidate":
        config["classifications"]["V1"]["candidate_rule_ids"] = ["MISSING"]
    elif invalid == "type":
        config["classifications"]["V1"]["type_code"] = "MISSING"
    elif invalid == "allowlist":
        config["types"]["SAFE"]["allowed_rule_ids"] = ["MISSING"]
    elif invalid == "default":
        config["types"]["SAFE"]["rule_id"] = "C"
    elif invalid == "disallowed":
        config["classifications"]["V1"]["candidate_rule_ids"] = ["C"]
    else:
        config["types"]["SAFE"]["allowed_rule_ids"] = "A"
    with pytest.raises(ValueError):
        _load(tmp_path, config)


def test_public_class_event_keeps_required_fields(tmp_path):
    event = DetectedEvent(type_code="V1", timecode_sec=1.0, description="Synthetic observation.",
                          evidence=(EvidenceRef(1.0),), rule_id="A")
    violation = stored_violation(event, _load(tmp_path), [{"timestamp_sec": 1.0, "jpeg_base64": "AA=="}])
    body = public_view(_done_record(stored_result([violation], partial=False, debug={}))).model_dump()
    assert body["violations"][0]["type"] == "Canonical safe"
    assert set(body["violations"][0]) == {"type", "timecode_sec", "description", "evidence_frames"}
    assert "Synthetic" in body["violations"][0]["description"]
