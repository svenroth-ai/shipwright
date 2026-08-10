"""Decision-Drop JSON decoding for the prompt-injection scanner."""

from __future__ import annotations

import json
from pathlib import Path


class DecisionDropUnscannableError(Exception):
    """A Decision-Drop payload is too deeply nested to inspect safely."""


def _json_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [string for child in value.values() for string in _json_string_values(child)]
    if isinstance(value, list):
        return [string for child in value for string in _json_string_values(child)]
    return []


def _decision_drop_text(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return " ".join(" ".join(value.split()) for value in _json_string_values(payload))
    except RecursionError as error:
        raise DecisionDropUnscannableError from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def scan_decision_drop(path: Path, rel_path: str, scan_markdown, make_finding):
    try:
        decision_text = _decision_drop_text(path)
    except DecisionDropUnscannableError:
        return [make_finding(
            severity="high",
            rule="DECISION_DROP_UNSCANNABLE",
            description="Decision-Drop JSON is too deeply nested to scan safely.",
            affected_file=rel_path,
            affected_line=None,
            remediation_hint="Replace the deeply nested JSON with a flat decision record.",
        )]
    findings = scan_markdown(path, rel_path, False, decision_text)
    # Decision drops are runtime-consumed instructions.  CI already scans them
    # but gates only critical findings, so promote their high-confidence prompt
    # risks into that existing enforcement path instead of weakening the gate.
    for finding in findings:
        if finding.get("severity") == "high":
            finding["severity"] = "critical"
            finding["severity_score"] = 9.5
    return findings
