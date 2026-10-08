"""Requirement coverage read from the traceability manifest being COMMITTED.

The commit hook used to gate on the RTM's "Traceability coverage" line -- the
share of build sections with a commit, absent for an adopted project (so every
commit was allowed, silently). This module computes requirement coverage from
``.shipwright/compliance/test-traceability.json`` as staged in the index (else as
committed at ``HEAD``). The working-tree copy is not trusted (the local pipeline
regenerates it fail-closed, every link ``not_run``, which would read as 0%); it is
read silently only outside a repo or when git has no such file, and with one WARN
naming why for any other git failure (``rtm_manifest_read``, which also states the
PreToolUse ordering limit: a manifest staged by the commit command itself is
measured from its previous index / HEAD copy). Never regenerated here. A
non-current schema or a manifest with no executed result is *unmeasurable* (WARN),
never 0%:

* **FR metric** -- counting unit: an *active* requirement. Covered when at least
  one test bound to it is ``status == "enabled"`` AND ``executed == "pass"``.
* **AC metric** -- counting unit: one acceptance criterion of an active
  requirement, covered under the same rule. Reported next to the FR metric, never
  mixed into it.

A skipped, never-run, failed or result-less test counts as NOT covered; a
parametrized test is one function-level link whose ``executed`` folds its cases.

**Accepted risk.** The binding-to-result join *by commit* is the collector's; this
module does NOT re-verify it, so an older result reads as passing until the
manifest is regenerated (F11 / CI). The staleness WARN mitigates, it does not prove.

Pure apart from reading project files and the ``git`` probes.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rtm_commit_distance import NOT_IN_HISTORY, commits_behind

# The index-then-HEAD read lives in its own module; re-exported so callers keep one import.
from rtm_manifest_read import (  # noqa: F401
    MANIFEST_RELPATH,
    UNREADABLE,
    read_manifest,
    read_manifest_noted,
)

# Mirrors audit/_group_d_manifest.MANIFEST_SCHEMA_VERSION (drift-guarded by a test).
MANIFEST_SCHEMA_VERSION = 4
STALE_AFTER_DAYS = 14
STALE_AFTER_COMMITS = 300


def _passing(link: Any) -> bool:
    return (
        isinstance(link, dict)
        and link.get("status") == "enabled"
        and link.get("executed") == "pass"
    )


def _any_passing(tests: Any) -> bool:
    if not isinstance(tests, dict):
        return False
    return any(
        _passing(link)
        for links in tests.values()
        if isinstance(links, list)
        for link in links
    )


def _pct(covered: int, total: int) -> int | None:
    return int(covered * 100 / total) if total else None


_AC_LINE = re.compile(r"^\s*[-*]\s*(?:\(\w+\)\s*)?\[(AC\d+)\]")
_HEADING = re.compile(r"^#{1,6}\s+(.*)")


def spec_ac_inventory(project_root: str | Path, spec_path: str) -> dict[str, set[str]] | None:
    """``{FR id: {AC ids}}`` read from a spec file, or ``None`` when unreadable.

    The manifest only carries an ``acs`` node for criteria some test is tagged
    to, so an untagged AC is absent from it -- the spec is the full inventory.
    A ``spec_path`` resolving outside the project root (``..``, absolute) is never
    read: ``None``, so the caller falls back to the manifest's inventory.
    """
    try:
        root = Path(project_root).resolve()
        spec = (root / spec_path).resolve()
        if not spec.is_relative_to(root):
            return None
        text = spec.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return None
    inventory: dict[str, set[str]] = {}
    current: set[str] | None = None
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = _HEADING.match(line)
        if heading:
            fr = re.match(r"(FR-[\w.\-]+?)(?:\s|$|[:—-]\s)", heading.group(1))
            current = inventory.setdefault(fr.group(1), set()) if fr else None
            continue
        ac = _AC_LINE.match(line)
        if ac and current is not None:
            current.add(ac.group(1))
    return inventory


def compute_coverage(manifest: dict[str, Any],
                     project_root: str | Path | None = None) -> dict[str, Any]:
    """FR and AC coverage of the *active* requirements in *manifest*.

    AC counting unit: one acceptance criterion of an active requirement. The
    inventory is the spec's full AC list (``project_root`` given and the spec
    readable), unioned with any AC the manifest knows; an AC with no tagged
    test is therefore UNCOVERED, not absent. Without a readable spec the
    inventory degrades to the manifest's tagged ACs and ``ac.source`` says
    ``"manifest"`` -- an optimistic floor, never reported as the full figure.

    ``pct`` is ``None`` when the denominator is zero: nothing to measure is not
    100%, and the caller must say so rather than pass silently.
    """
    fr_total = fr_cov = ac_total = ac_cov = excluded = 0
    sources: set[str] = set()
    uncovered: list[str] = []
    specs: dict[str, dict[str, set[str]] | None] = {}
    requirements = manifest.get("requirements")
    if not isinstance(requirements, dict):
        requirements = {}
    for key, req in requirements.items():
        if not isinstance(req, dict):
            continue
        if req.get("status") != "active":
            excluded += 1
            continue
        fr_total += 1
        fr_id = str(req.get("id") or key)
        if _any_passing(req.get("tests")):
            fr_cov += 1
        else:
            uncovered.append(fr_id)
        acs = req.get("acs")
        acs = acs if isinstance(acs, dict) else {}
        inventory = set(acs)
        spec_path = req.get("spec_path")
        if project_root is not None and isinstance(spec_path, str) and spec_path:
            if spec_path not in specs:
                specs[spec_path] = spec_ac_inventory(project_root, spec_path)
            from_spec = (specs[spec_path] or {}).get(fr_id)
            if from_spec:
                inventory |= from_spec
                sources.add("spec")
            else:
                sources.add("manifest")
        else:
            sources.add("manifest")
        for ac_id in inventory:
            ac_total += 1
            ac = acs.get(ac_id)
            if isinstance(ac, dict) and _any_passing(ac.get("tests")):
                ac_cov += 1
    source = "spec" if sources == {"spec"} else "manifest" if sources <= {"manifest"} else "mixed"
    return {
        "fr": {"covered": fr_cov, "total": fr_total, "pct": _pct(fr_cov, fr_total)},
        "ac": {"covered": ac_cov, "total": ac_total, "pct": _pct(ac_cov, ac_total),
               "source": source},
        "excluded_inactive": excluded,
        "uncovered_requirements": uncovered,
    }


def _links(manifest: dict[str, Any]):
    """Every link dict bound to a requirement or to one of its ACs."""
    reqs = manifest.get("requirements")
    for req in reqs.values() if isinstance(reqs, dict) else ():
        if not isinstance(req, dict):
            continue
        acs = req.get("acs")
        for node in [req, *(acs.values() if isinstance(acs, dict) else ())]:
            tests = node.get("tests") if isinstance(node, dict) else None
            for links in tests.values() if isinstance(tests, dict) else ():
                if isinstance(links, list):
                    yield from (link for link in links if isinstance(link, dict))


def schema_problem(manifest: dict[str, Any]) -> str | None:
    """A WARN when the manifest is not the current schema (mirrors Group D's read)."""
    version = manifest.get("schema_version")
    if type(version) is int and version == MANIFEST_SCHEMA_VERSION:
        return None
    return (
        f"traceability manifest schema_version {version!r} is not the current "
        f"{MANIFEST_SCHEMA_VERSION}; coverage is not measurable -- regenerate it (F11 / CI)"
    )


def execution_problem(manifest: dict[str, Any]) -> str | None:
    """A WARN when no link carries an executed result (no ``pass`` and no ``fail``)."""
    if any(link.get("executed") in ("pass", "fail") for link in _links(manifest)):
        return None
    return (
        "traceability manifest records no executed test result (every link is "
        "not_run, e.g. a fail-closed local regeneration); coverage is not measurable, "
        "not 0% -- regenerate it from a real test run (F11 / CI)"
    )


_ZERO_SHA = re.compile(r"0{7,64}")


def _provenance_unknown(manifest: dict[str, Any]) -> bool:
    """Epoch ``generated_at`` or an all-zero ``source_commit``: a placeholder stamp."""
    source = manifest.get("source_commit")
    return str(manifest.get("generated_at")).startswith("1970-01-01") or (
        isinstance(source, str) and _ZERO_SHA.fullmatch(source) is not None)


def staleness_warning(manifest: dict[str, Any], project_root: str | Path,
                      now: datetime | None = None) -> str | None:
    """A WARN sentence when the manifest is old, or ``None`` when it is fresh enough."""
    if _provenance_unknown(manifest):
        # no git probe: an all-zero SHA names no commit
        return (
            "traceability manifest provenance is unknown (epoch generated_at or "
            "all-zero source_commit); its age cannot be told -- regenerate it in "
            "F11 / CI (this hook never does)"
        )
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    try:
        generated = datetime.fromisoformat(str(manifest.get("generated_at")))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age = (now - generated).days
        if age > STALE_AFTER_DAYS:
            reasons.append(f"is {age} days old")
    except (TypeError, ValueError):
        reasons.append("carries no readable generated_at")
    source = manifest.get("source_commit")
    if isinstance(source, str) and re.fullmatch(r"[0-9a-fA-F]{7,64}", source):
        behind = commits_behind(project_root, source)
        if behind == NOT_IN_HISTORY:
            reasons.append("has commit distance unknown (source_commit not in local history)")
        elif behind is not None and behind > STALE_AFTER_COMMITS:
            reasons.append(f"is {behind} commits behind HEAD")
    if not reasons:
        return None
    return (
        "traceability manifest " + "; ".join(reasons)
        + "; coverage below is computed from that snapshot "
        "(regenerate it in F11 / CI -- this hook never does)"
    )
