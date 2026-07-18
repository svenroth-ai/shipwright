"""Accepted-risk rows for the compliance dashboard — pure + offline.

Extracted from ``ci_security`` (which was at 269 LOC and would have crossed the
300-line cap) and widened at the same time. The old view had three defects, all
of which let a real suppression stay invisible:

1. It read only ``.trivyignore.yaml|.yml`` while the SCANNER
   (``oss_backend._resolve_trivy_ignorefile``) *also* honours the classic
   flat-text ``.trivyignore`` — a repo using that form got real suppression with
   zero dashboard visibility.
2. It dropped ``statement``, ``paths`` and ``purls`` — the justification and the
   scope, i.e. exactly the fields an auditor needs.
3. It could not show a Semgrep or CI-posture acceptance at all, because the only
   register it knew was a Trivy ignore file.

Rows are correlated, not concatenated: one logical row per acceptance, carrying
both the register metadata (why, until when, on whose authority) and whether the
operational suppression is actually in place. A suppression with no register
entry renders as DRIFT rather than as an accepted risk — being suppressed is not
the same as being accepted, and conflating them is how an unrecorded
suppression hides in plain sight.

Degradation is visible, never silent: if the shared register reader cannot be
reached or the register is malformed, the section says so instead of rendering
an empty (and therefore reassuring) table.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

#: ``shared/scripts`` relative to this file: plugins/<p>/scripts/lib/<this>.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"

_TRIVYIGNORE_YAML_NAMES = (".trivyignore.yaml", ".trivyignore.yml")
_TRIVYIGNORE_FLAT_NAME = ".trivyignore"

SOURCE_REGISTERED_ACTIVE = "registered+active"
SOURCE_REGISTERED_ONLY = "registered"
SOURCE_UNREGISTERED = "unregistered"


def _coerce_date(value: Any) -> date | None:
    """Best-effort ``date`` from a YAML date or an ISO ``YYYY-MM-DD`` string.

    ``datetime`` is tested first because it is a *subclass* of ``date``.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _load_shared():
    """The shared register reader + suppression discovery, or ``None``.

    Lazily bootstrapped: this module is reached through cross-plugin import
    chains (contracts.iterate -> update_compliance -> _control_block ->
    ci_security), and a hard module-level dependency on ``shared/scripts`` would
    break those in a plugin that cannot see it (ADR-045).
    """
    try:
        # APPEND, never insert(0): shared/scripts also contains `lib/`, `tools/`
        # and `normalizers/`, and putting it first would let those shadow a
        # plugin's own same-named packages (the ADR-044/045 failure). Both
        # modules below have unique top-level names, so appending resolves them
        # without changing precedence for anything else.
        if str(_SHARED_SCRIPTS) not in sys.path:
            sys.path.append(str(_SHARED_SCRIPTS))
        import accepted_risk_scan  # noqa: PLC0415
        import accepted_risks  # noqa: PLC0415

        return accepted_risks, accepted_risk_scan
    except ImportError:
        return None


def parse_trivyignore(project_root: Path | str) -> list[dict[str, Any]]:
    """Entries from whichever ``.trivyignore`` form the repo uses.

    Returns ``{id, expired_at, scope}`` dicts. Tolerant of a missing/malformed
    file (``[]``) — the register reader, not this one, is the fail-closed seam.
    """
    root = Path(project_root)
    for name in _TRIVYIGNORE_YAML_NAMES:
        path = root / name
        if path.is_file():
            import yaml  # noqa: PLC0415

            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                return []
            if not isinstance(doc, dict):
                return []
            out = []
            for entry in doc.get("vulnerabilities") or []:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                out.append({
                    "id": str(entry["id"]),
                    "expired_at": entry.get("expired_at"),
                    "scope": entry.get("paths") or entry.get("purls") or [],
                })
            return out
    flat = root / _TRIVYIGNORE_FLAT_NAME
    if flat.is_file():
        # Classic form: one id per line with `#` comments — NOT YAML.
        try:
            lines = flat.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        return [
            {"id": stripped, "expired_at": None, "scope": []}
            for raw in lines
            if (stripped := raw.split("#", 1)[0].strip())
        ]
    return []


def _row(*, rid: str, target: str, rule: str, expires: str, expired: bool,
         ref: str, statement: str, source: str) -> dict[str, Any]:
    return {
        "id": rid, "target": target, "rule": rule, "expires": expires,
        "expired": expired, "rationale_ref": ref, "statement": statement,
        "source": source,
    }


def accepted_risk_rows(
    project_root: Path | str, *, now: date
) -> tuple[list[dict[str, Any]], str | None]:
    """Correlated accepted-risk rows plus an optional degradation note.

    The note is non-``None`` when the register could not be read; the caller
    MUST surface it, so an unreadable register never renders as "none accepted".
    """
    shared = _load_shared()
    trivy = parse_trivyignore(project_root)
    trivy_by_id = {e["id"]: e for e in trivy}

    if shared is None:
        note = (
            "register reader unavailable - showing the Trivy ignore file only; "
            "Semgrep and posture acceptances are NOT listed"
        )
        rows = [
            _row(rid=e["id"], target="trivy-ignore", rule=e["id"],
                 expires=(d.isoformat() if (d := _coerce_date(e["expired_at"])) else ""),
                 expired=bool(d and d < now), ref="", statement="",
                 source=SOURCE_REGISTERED_ACTIVE)
            for e in trivy
        ]
        return rows, note

    accepted_risks, scan = shared
    try:
        entries = accepted_risks.load_register(project_root)
    except accepted_risks.RegisterError as exc:
        return [], f"accepted-risk register is INVALID and was not read: {exc}"

    try:
        discovered = scan.discovered_suppressions(project_root)
    except Exception:  # noqa: BLE001 - never let the dashboard crash on this
        discovered = {}

    rows: list[dict[str, Any]] = []
    recorded_rules: dict[str, set[str]] = {}
    for entry in entries:
        recorded_rules.setdefault(entry.target, set()).add(entry.rule)
        active = entry.rule in discovered.get(entry.target, set())
        if entry.target == "github-dismissal":
            # Not verifiable offline; say so rather than implying it was checked.
            source = SOURCE_REGISTERED_ONLY
        else:
            source = SOURCE_REGISTERED_ACTIVE if active else SOURCE_REGISTERED_ONLY
        rows.append(_row(
            rid=entry.id, target=entry.target, rule=entry.rule,
            expires=entry.expires.isoformat(), expired=entry.is_expired(now),
            ref=entry.rationale_ref, statement=entry.statement, source=source,
        ))

    # Suppressions nobody recorded — surfaced as drift, never as "accepted".
    for target, rules in sorted(discovered.items()):
        for rule in sorted(rules - recorded_rules.get(target, set())):
            entry = trivy_by_id.get(rule, {})
            parsed = _coerce_date(entry.get("expired_at"))
            rows.append(_row(
                rid=rule, target=target, rule=rule,
                expires=parsed.isoformat() if parsed else "",
                expired=bool(parsed and parsed < now), ref="", statement="",
                source=SOURCE_UNREGISTERED,
            ))
    return rows, None


def parse_accepted_risks(
    project_root: Path | str, *, now: date
) -> list[dict[str, Any]]:
    """Back-compat shim for the original ``ci_security`` signature.

    Keeps ``{id, expired_at, expired}`` and ADDS the wider fields, so existing
    callers (and the grade re-export bridge) are unaffected.
    """
    rows, _note = accepted_risk_rows(project_root, now=now)
    return [{**r, "expired_at": r["expires"]} for r in rows]
