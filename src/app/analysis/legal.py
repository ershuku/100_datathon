"""Loads config/rules_legal.yaml. Legal text is human-curated; this module never invents any."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PLACEHOLDERS = {"", "TODO", "TBD"}


def _filled(value: object) -> bool:
    return isinstance(value, str) and value.strip().upper() not in PLACEHOLDERS


@dataclass(frozen=True)
class LegalRef:
    document: str
    punkt: str
    rule_text: str | None
    url: str | None
    limitations: str | None = None
    review_required: bool = False

    def citation(self) -> str:
        """Append the human-curated rule and its source without changing the public schema."""
        punkt = self.punkt.strip().rstrip(".")
        prefix = "" if punkt.lower().startswith(("п.", "пп.", "раздел", "глава", "ст.")) else "п. "
        label = "Возможное основание (применимость требует проверки)" if self.review_required else "Правило"
        citation = f"{label}: {self.document.strip().rstrip('.')}, {prefix}{punkt}."
        if _filled(self.limitations):
            citation += f" Ограничения применимости: {self.limitations.strip()}"
        return f"{citation} Источник: {self.url.strip()}" if _filled(self.url) else citation


@dataclass(frozen=True)
class ViolationType:
    code: str
    name: str
    default_ref: LegalRef | None
    rule_id: str | None
    requires_rule_id: bool = False
    allowed_rule_ids: tuple[str, ...] | None = None
    observation_only: bool = False


@dataclass(frozen=True)
class ClassMapping:
    name: str
    type_code: str
    candidate_rule_ids: tuple[str, ...]
    status: str
    conditions: tuple[str, ...]
    limitations: tuple[str, ...]


def _strings(raw: object, field: str, *, allow_string: bool = False) -> tuple[str, ...]:
    if allow_string and isinstance(raw, str):
        return (raw,) if raw.strip() else ()
    if not isinstance(raw, list) or any(not _filled(v) for v in raw):
        raise ValueError(f"rules_legal.yaml: {field} must be a list of nonempty strings")
    if len(set(raw)) != len(raw):
        raise ValueError(f"rules_legal.yaml: {field} contains duplicates")
    return tuple(raw)


def _parse_ref(raw: dict) -> LegalRef | None:
    if not (_filled(raw.get("document")) and _filled(raw.get("punkt"))):
        return None
    return LegalRef(
        document=str(raw["document"]),
        punkt=str(raw["punkt"]),
        rule_text=str(raw["rule_text"]) if _filled(raw.get("rule_text")) else None,
        url=str(raw["url"]) if _filled(raw.get("url")) else None,
        limitations=str(raw["limitations"]) if _filled(raw.get("limitations")) else None,
        review_required=raw.get("review_status") == "source_checked_team_review_required",
    )


class LegalCatalog:
    def __init__(self, types: dict[str, ViolationType], rules: dict[str, LegalRef],
                 classifications: dict[str, ClassMapping] | None = None) -> None:
        self.types = types
        self.rules = rules
        self.classifications = classifications or {}

    @classmethod
    def load(cls, path: Path) -> LegalCatalog:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        types: dict[str, ViolationType] = {}
        for code, raw in (data.get("types") or {}).items():
            raw = raw or {}
            if not _filled(raw.get("name")):
                raise ValueError(f"rules_legal.yaml: type {code} has no name")
            types[str(code)] = ViolationType(
                code=str(code),
                name=str(raw["name"]),
                default_ref=_parse_ref(raw),
                rule_id=str(raw["rule_id"]) if _filled(raw.get("rule_id")) else None,
                requires_rule_id=bool(raw.get("requires_rule_id", False)),
                observation_only=bool(raw.get("observation_only", False)),
                allowed_rule_ids=_strings(raw["allowed_rule_ids"], f"type {code} allowed_rule_ids")
                if "allowed_rule_ids" in raw else None,
            )
        rules = {str(rid): ref for rid, raw in (data.get("rules") or {}).items() if (ref := _parse_ref(raw or {}))}
        for code, entry in types.items():
            if entry.rule_id and entry.rule_id not in rules:
                raise ValueError(f"rules_legal.yaml: type {code} references unknown rule {entry.rule_id}")
            if entry.allowed_rule_ids is not None:
                if any(rid not in rules for rid in entry.allowed_rule_ids):
                    raise ValueError(f"rules_legal.yaml: type {code} allows an unknown rule")
                if entry.rule_id and entry.rule_id not in entry.allowed_rule_ids:
                    raise ValueError(f"rules_legal.yaml: type {code} default rule is not allowed")
        classifications: dict[str, ClassMapping] = {}
        for code, raw in (data.get("classifications") or {}).items():
            if str(code) in types or not isinstance(raw, dict):
                raise ValueError(f"rules_legal.yaml: invalid classification {code}")
            type_code = raw.get("type_code")
            if type_code not in types or not _filled(raw.get("name")) or not _filled(raw.get("status")):
                raise ValueError(f"rules_legal.yaml: classification {code} needs valid type, name and status")
            candidates = _strings(raw.get("candidate_rule_ids"), f"classification {code} candidate_rule_ids")
            allowed = types[type_code].allowed_rule_ids
            if any(rid not in rules or (allowed is not None and rid not in allowed) for rid in candidates):
                raise ValueError(f"rules_legal.yaml: classification {code} has an unknown or disallowed rule")
            classifications[str(code)] = ClassMapping(
                name=raw["name"], type_code=type_code, candidate_rule_ids=candidates, status=raw["status"],
                conditions=_strings(raw.get("conditions", []), f"classification {code} conditions", allow_string=True),
                limitations=_strings(raw.get("limitations", []), f"classification {code} limitations", allow_string=True),
            )
        return cls(types, rules, classifications)

    def is_observation_only(self, code: str) -> bool:
        mapping = self.classifications.get(code)
        if mapping:
            if mapping.status == "observation_only":
                return True
            code = mapping.type_code
        entry = self.types.get(code)
        return bool(entry and entry.observation_only)

    def type_name(self, code: str, fallback: str | None = None) -> str:
        mapping = self.classifications.get(code)
        if mapping:
            code = mapping.type_code
        entry = self.types.get(code)
        if entry:
            return entry.name
        return fallback or code

    def legal_ref(self, code: str, rule_id: str | None = None) -> LegalRef | None:
        mapping = self.classifications.get(code)
        if mapping:
            # A class is a candidate mapping, never proof that its conditions hold.
            if not rule_id or rule_id not in mapping.candidate_rule_ids:
                return None
            code = mapping.type_code
        entry = self.types.get(code)
        if entry is None:
            return None
        if rule_id:
            if entry.allowed_rule_ids is not None and rule_id not in entry.allowed_rule_ids:
                return None
            return self.rules.get(rule_id)
        if entry.requires_rule_id:
            return None
        if entry.rule_id and entry.rule_id in self.rules:
            return self.rules[entry.rule_id]
        return entry.default_ref
