"""The real analyzer (PIPELINE=real) end to end through the backend's result code, with the
detector faked: no torch, no weights, no footage. Proves the rule engine's events fit the analyzer
contract, the legal catalogue and the public API shape."""

from __future__ import annotations

import sys
import types

import pytest

from app.analysis.legal import LegalCatalog
from app.analysis.port import AnalyzerOutput, JobContext
from app.results import public_view, stored_result, stored_violation
from conftest import REPO
from test_results import FRAME, _done_record
from test_rules import scene

VIOLATION = scene(30, customer=[(2, 25)], cash_desk=[(8, 10), (14, 17)], cash_counter=[(10, 14)],
                  safe_open=[(17, 20)])  # cash accepted without an ID card
CLEAN = scene(30, customer=[(2, 25)], id=[(4, 7)], cash_desk=[(8, 10), (14, 17)], cash_counter=[(10, 14)],
              safe_open=[(17, 20)])


class Reporter:
    def __init__(self):
        self.progress_calls, self.events = [], []

    def progress(self, percent, stage):
        self.progress_calls.append((percent, stage))

    def event(self, event):
        self.events.append(event)


def _ctx(tmp_path) -> JobContext:
    return JobContext(job_id="0123456789abcdef", duration_sec=30.0, fps=30.0, width=464, height=848,
                      source_path=str(tmp_path / "src.mov"), work_dir=str(tmp_path), time_budget_sec=200.0)


def _analyze(monkeypatch, tmp_path, doc) -> tuple[AnalyzerOutput, Reporter]:
    fake = types.ModuleType("pipeline.detector")

    class FakeDetector:
        def __init__(self, weights, threshold=0.35, fps=5.0):
            self.weights = weights

        def run(self, path, on_progress=None):
            if on_progress:
                on_progress(1.0)
            return doc

    fake.Detector = FakeDetector
    monkeypatch.setitem(sys.modules, "pipeline.detector", fake)
    from pipeline.analyzer import create_analyzer

    rep = Reporter()
    return create_analyzer().analyze_video(str(tmp_path / "in.mp4"), _ctx(tmp_path), rep), rep


@pytest.fixture
def catalog() -> LegalCatalog:
    return LegalCatalog.load(REPO / "config" / "rules_legal.yaml")


def test_violation_flows_to_public_api(monkeypatch, tmp_path, catalog):
    out, rep = _analyze(monkeypatch, tmp_path, VIOLATION)
    assert [e.type_code for e in out.events] == ["ID"]
    ev = out.events[0]
    assert 0 <= ev.timecode_sec <= 30 and 1 <= len(ev.evidence) <= 3
    assert ev.description and "Правило" not in ev.description  # legal text comes only from the catalogue
    assert rep.events == list(out.events) and rep.progress_calls[-1][0] == 100
    assert not catalog.is_observation_only(ev.type_code)
    body = public_view(_done_record(stored_result([stored_violation(ev, catalog, FRAME)], partial=False,
                                                  debug=out.debug))).model_dump()
    assert body["verdict"] == "violation" and body["violations"][0]["timecode_sec"] == round(ev.timecode_sec, 1)
    assert "debug" not in body  # internal diagnostics never reach the public JSON


def test_clean_scene_gives_no_events(monkeypatch, tmp_path):
    out, _ = _analyze(monkeypatch, tmp_path, CLEAN)
    assert out.events == ()
    body = public_view(_done_record(stored_result([], partial=False, debug=out.debug))).model_dump()
    assert body["verdict"] == "no_violation" and body["violations"] == []


def test_every_rule_resolves_to_a_catalogue_citation(catalog):
    """Each (type, rule_id) the rule engine can emit is a reportable type whose rule_id the team's
    catalogue accepts, so the backend appends a real citation instead of silently dropping it."""
    from pipeline import rules

    for rule, (code, rule_id) in rules.CATALOGUE.items():
        assert code in catalog.types, rule
        assert not catalog.is_observation_only(code), rule
        ref = catalog.legal_ref(code, rule_id)
        assert ref is not None and ref.document and ref.punkt, f"{rule}: {code}/{rule_id} has no citation"


def test_public_description_carries_the_catalogue_citation(monkeypatch, tmp_path, catalog):
    out, _ = _analyze(monkeypatch, tmp_path, VIOLATION)
    ev = out.events[0]
    assert ev.rule_id == "CASH_ID_IN"
    v = stored_violation(ev, catalog, FRAME)
    assert v["legal_ref"] is not None
    body = public_view(_done_record(stored_result([v], partial=False, debug={}))).model_dump()
    # Wording ("Правило" / "Возможное основание ...") and limitations come from the catalogue.
    assert v["legal_ref"]["citation"] in body["violations"][0]["description"]
    assert "adilet.zan.kz" in body["violations"][0]["description"]
