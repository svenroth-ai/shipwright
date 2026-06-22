"""Policy guardrail for the monorepo's Trivy accepted-risk register.

The repo-root ``.trivyignore.yaml`` lets us accept a security finding we have
assessed as non-reachable (wired into the scanner via
``oss_backend._run_trivy --ignorefile``, iterate-2026-06-22-trivy-risk-accept).
Because such an accept suppresses a finding *before* it reaches ``findings.json``
(and therefore the critical-gate), every entry MUST be a documented, scoped,
time-bounded acceptance — not a blanket suppression:

  - ``id``                 — the CVE / GHSA being accepted
  - ``paths`` or ``purls`` — a scope (no repo-wide silencing)
  - ``expired_at``         — a re-review date (accepts auto-expire, never forgotten)
  - ``statement``          — the justification (why it is non-reachable / accepted)

This makes the discipline mechanical rather than convention: a sloppy accept
fails CI. The register is OPTIONAL — if the file is absent (fresh checkout, or
every accept expired and was removed) the tests pass.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# shared/tests/<this file> -> parents[2] is the repo root.
REGISTER = Path(__file__).resolve().parents[2] / ".trivyignore.yaml"


def _entries(register: Path = REGISTER) -> list[dict]:
    if not register.is_file():
        return []
    data = yaml.safe_load(register.read_text(encoding="utf-8")) or {}
    return data.get("vulnerabilities", []) or []


def _violations(entry: dict) -> list[str]:
    """Return the discipline violations for one accept entry (empty == OK)."""
    cid = entry.get("id", "?")
    out: list[str] = []
    for field in ("id", "expired_at", "statement"):
        if not entry.get(field):
            out.append(f"{cid}: missing required '{field}'")
    if not (entry.get("paths") or entry.get("purls")):
        out.append(f"{cid}: no `paths`/`purls` scope — no blanket suppression")
    return out


def test_register_is_well_formed_if_present():
    if not REGISTER.is_file():
        return  # the register is optional
    data = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    assert data is None or isinstance(data, dict), "register must be a YAML mapping"
    vulns = (data or {}).get("vulnerabilities", [])
    assert isinstance(vulns, list), "`vulnerabilities` must be a list"
    for entry in vulns:
        assert isinstance(entry, dict), f"non-mapping register entry: {entry!r}"


def test_accepts_are_scoped_timebound_and_justified():
    problems = [p for entry in _entries() for p in _violations(entry)]
    assert not problems, (
        "Accepted-risk discipline violations in .trivyignore.yaml (every accept "
        "must be scoped + time-bounded + justified):\n  - " + "\n  - ".join(problems)
    )


def test_policy_rejects_a_sloppy_accept():
    # A guard that never rejects is worthless — pin that it catches the bad cases.
    assert _violations({"id": "CVE-X"}), "must reject an entry missing expiry/scope/statement"
    assert _violations(
        {"id": "CVE-Y", "expired_at": "2027-01-01", "statement": "x"}
    ), "must reject an unscoped (repo-wide) accept"
    assert _violations(
        {"id": "CVE-Z", "paths": ["a/b"], "expired_at": "2027-01-01", "statement": "x"}
    ) == [], "must accept a well-formed, scoped, time-bounded, justified entry"


def test_passes_when_register_absent(tmp_path):
    assert _entries(tmp_path / "nonexistent.trivyignore.yaml") == []
