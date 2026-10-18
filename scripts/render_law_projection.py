"""Render generic legal guidance from YAML; never ingest spreadsheet/video data.

Only sections 2 and 5 are regenerated. Sections 3 and 4 remain opaque bytes.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def cell(value: object) -> str:
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value)
    return str(value or "—").replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def render(data: dict) -> tuple[bytes, bytes]:
    classes = data.get("classifications")
    if not isinstance(classes, dict) or not classes:
        raise ValueError("YAML classifications mapping is required")
    rules = data["rules"]
    rows = [
        "## 2. Conditional classification guidance (generated)", "",
        "<!-- GENERATED: law-classifications:start -->",
        "Generated from `config/rules_legal.yaml`; edit the catalogue and run "
        "`.venv/bin/python scripts/render_law_projection.py`. A class is a candidate, never a fixed verdict.", "",
        "| Class | Name / candidate code | Candidate rule and official source | Status | Conditions | Limitations |",
        "|---|---|---|---|---|---|",
    ]
    for code, entry in classes.items():
        refs = []
        for rid in entry.get("candidate_rule_ids", []):
            rule = rules[rid]
            refs.append(f"`{rid}` — {cell(rule['punkt'])} "
                        f"([official source]({rule['url']}))")
        values = [f"**{cell(code)}**", f"{cell(entry['name'])} / `{cell(entry.get('type_code'))}`",
                  "; ".join(refs) or "No confirmed direct rule — review only",
                  cell(entry.get("status")), cell(entry.get("conditions")), cell(entry.get("limitations"))]
        rows.append("| " + " | ".join(values) + " |")
    rows += ["", "<!-- GENERATED: law-classifications:end -->", "", "---", "", ""]
    description = [
        "## 5. Conditional `description` assembly (generated)", "",
        "<!-- GENERATED: law-description:start -->",
        "1. Describe only the observation at `timecode_sec`; keep each event and its evidence separate.",
        "2. Map the class through the generated table to a candidate `type_code` and `rule_id`.",
        "3. Check classification conditions and limitations, then the selected rule's "
        "`required_observations`, `limitations`, and `evidence_mode` in the catalogue. "
        "A candidate rule is not proof of applicability; missing records must not be invented.",
        "4. Only after context checks, append the selected catalogue citation, applicability limits, "
        "and official URL. Pending references remain possible grounds requiring review. "
        "No confirmed rule means an observation for review without an asserted legal violation.",
        "5. Preserve multiple independent events and 1–3 evidence frames per event. "
        "Do not derive a new-video verdict from historical worksheet labels or this document's archived rows.", "",
        "Public schema stays unchanged: `type`, `timecode_sec`, `description`, `evidence_frames`. "
        "The backend appends verified catalogue citation text to `description`; "
        "it does not generate legal text or validate context automatically.", "",
        "Never invent amounts, postings, banknote authenticity, identity/document ownership, "
        "internal-bank policy, or criminal intent. No face identification or audio analysis. "
        "No dataset or observations are sent to government sites.", "",
        "<!-- GENERATED: law-description:end -->", "",
    ]
    return "\n".join(rows).encode(), "\n".join(description).encode()


def sections(raw: bytes) -> tuple[int, int, int]:
    def start(number: int) -> int:
        match = re.search(rb"(?m)^## " + str(number).encode() + rb"\. ", raw)
        if match is None:
            raise ValueError(f"Missing section {number}")
        return match.start()
    return start(2), start(3), start(5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check generated blocks without writing")
    args = parser.parse_args()
    data = yaml.safe_load((ROOT / "config/rules_legal.yaml").read_text(encoding="utf-8"))
    target = ROOT / "pipeline_law_projection.md"
    original = target.read_bytes()
    second, third, fifth = sections(original)
    table, guidance = render(data)
    updated = original[:second] + table + original[third:fifth] + guidance
    if args.check:
        if updated != original:
            print("Generated legal guidance is stale; run scripts/render_law_projection.py")
            return 1
        print("Generated legal guidance is current")
        return 0
    target.write_bytes(updated)
    print("Rendered generic legal guidance; archived sections 3–4 preserved byte-for-byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
