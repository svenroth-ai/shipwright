"""Filesystem-facing wiring for ``_project_gate_extras.py``'s four pure
gate functions, split out of ``project_checks.py`` the moment that file
crossed the 300-LOC bloat-baseline guideline (same precedent as
``grill_trace_glossary.py`` splitting out of
``verify_grill_trace_completeness.py``). Each ``check_*`` here reads
whatever filesystem state its gate needs and adapts the pure ``GateResult``
into a ``CheckResult``; ``project_checks.run_project_checks`` calls all four
in sequence, exactly like it calls ``check_grill_trace_completeness``.
Split-manifest reading (declared split names, their ``spec.md`` texts) now
lives in the sibling ``_project_gate_manifest.py`` — split out of THIS file
the moment several Tier-3 PR-review rounds (PR #729) pushed it over 300
lines again, specifically by growing that manifest-reading logic."""

from __future__ import annotations

import json
from pathlib import Path

from . import _project_gate_extras as _extras
from ._project_gate_manifest import _read_spec_texts, _unreadable_result
from .common import CheckResult, Severity


def _read_project_scope(
    project_root: Path, name: str,
) -> tuple[str | None, CheckResult | None, bool]:
    """``shipwright_project_config.json``'s ``scope`` field, shared by
    every scope-aware gate in this module (round 5 extraction — two gates
    had grown near-identical try/except blocks). Returns ``(scope,
    error_result, config_exists)``: a non-``None`` ``error_result`` must be
    returned by the caller UNCHANGED (fail-loud parse/shape failure,
    external code review round 4 low + round 5 medium); ``config_exists``
    lets a caller distinguish "nothing written yet" from a config that
    exists but has no ``scope`` key (``scope is None`` either way)."""
    path = project_root / "shipwright_project_config.json"
    if not path.exists():
        return None, None, False
    try:
        scope = json.loads(path.read_text(encoding="utf-8")).get("scope")
    except (json.JSONDecodeError, OSError) as exc:
        return None, CheckResult(
            name, False,
            f"unverifiable — shipwright_project_config.json could not be parsed: {exc}",
        ), True
    except AttributeError:
        return None, CheckResult(
            name, False,
            "unverifiable — shipwright_project_config.json is not a JSON object",
        ), True
    return scope, None, True


def check_basis_forbids_assumed(project_root: Path) -> CheckResult:
    """FR-01.02 #4 + #15 (merged) — see ``_project_gate_extras.basis_forbids_assumed``.

    **NOT scoped to greenfield, unlike #11.** Round 5 added an
    extension-scope skip, reasoning #4's greenfield text and #15's
    allow-with-settlement text both scope to a freshly-authored project.
    Required Tier-3 PR review (PR #729) found that stale after the round-1
    spec-review REJECT: the merged function no longer enforces #4's
    literally-greenfield ban (reverted, stricter than the ledger's
    ceiling) — it enforces ONLY #15's un-scoped form obligation ("name
    what would settle `assumed`"). An extension run still runs an
    interview (a PO is present) — unlike `/shipwright-adopt` — so #15 is
    reachable there too, unlike #11's unrelated skip. Fixed by removing it."""
    name = "Basis column forbids bare 'assumed' (FR-01.02 #4/#15)"
    _scope, error, _config_exists = _read_project_scope(project_root, name)
    if error:
        return error
    spec_texts, unreadable = _read_spec_texts(project_root)
    if bad := _unreadable_result(name, unreadable):
        return bad
    if not spec_texts:
        return CheckResult(name, True, "no spec.md written yet", severity=Severity.SKIPPED.value)
    result = _extras.basis_forbids_assumed(spec_texts)
    return CheckResult(name, result.ok, result.detail)


def check_criteria_free_of_implementation_detail(project_root: Path) -> CheckResult:
    """FR-01.02 #5 — see ``_project_gate_extras.criteria_free_of_implementation_detail``."""
    name = "acceptance criteria free of implementation detail (FR-01.02 #5)"
    spec_texts, unreadable = _read_spec_texts(project_root)
    if bad := _unreadable_result(name, unreadable):
        return bad
    if not spec_texts:
        return CheckResult(name, True, "no spec.md written yet", severity=Severity.SKIPPED.value)
    result = _extras.criteria_free_of_implementation_detail(spec_texts)
    return CheckResult(name, result.ok, result.detail)


def check_no_empty_split(project_root: Path) -> CheckResult:
    """FR-01.02 #10 — see ``_project_gate_extras.no_empty_split``."""
    name = "no split has zero active FR rows (FR-01.02 #10)"
    spec_texts, unreadable = _read_spec_texts(project_root)
    if bad := _unreadable_result(name, unreadable):
        return bad
    if not spec_texts:
        return CheckResult(name, True, "no spec.md written yet", severity=Severity.SKIPPED.value)
    result = _extras.no_empty_split(spec_texts)
    return CheckResult(name, result.ok, result.detail)


def check_starting_guidance_present(project_root: Path) -> CheckResult:
    """FR-01.02 #11 — see ``_project_gate_extras.starting_guidance_present``.

    Extension scope never writes CLAUDE.md / agent_docs (they already
    exist on the target repo) — same "Full Application only" carve-out
    ``step-8-completion.md`` items 3 and 4 already state in prose.
    """
    name = "starting guidance present and non-empty (FR-01.02 #11)"
    scope, error, config_exists = _read_project_scope(project_root, name)
    if error:
        return error
    if not config_exists:
        return CheckResult(name, True, "no project config yet", severity=Severity.SKIPPED.value)
    if scope == "extension":
        return CheckResult(
            name, True, "extension scope — CLAUDE.md/agent_docs pre-exist",
            severity=Severity.SKIPPED.value,
        )
    result = _extras.starting_guidance_present(project_root)
    return CheckResult(name, result.ok, result.detail)


__all__ = [
    "check_basis_forbids_assumed",
    "check_criteria_free_of_implementation_detail",
    "check_no_empty_split",
    "check_starting_guidance_present",
]
