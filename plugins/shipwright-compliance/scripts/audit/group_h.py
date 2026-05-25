"""Group H — Bloat-policy detective audit (Campaign A.review).

H0 baseline meta (skip absent / fail malformed); H1 drift (oversize file
not in baseline); H2 ratchet-suggestion (current > on-disk LOC); H3
anti-ratchet bypass (state=anti-ratchet); H4 exception without ADR; H5
deferred-plan without plan_ref; H6 stale-entry (path missing on disk OR
escapes project_root). H1/H2 reuse the producer's ``bloat_baseline.scan``
+ ``_file_newlines`` so audit semantics cannot drift from writer
(external-review OpenAI #2/#3). All Findings: source=detective-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
    load_shared_lib,
)


_bb = load_shared_lib("bloat_baseline")


# ---------------------------------------------------------------------------
# Names + severities
# ---------------------------------------------------------------------------

_NAME_BY_CHECK = {
    "H0": "Bloat baseline file",
    "H1": "Bloat drift (oversize file not in baseline)",
    "H2": "Bloat ratchet-suggestion (baseline current > actual)",
    "H3": "Bloat anti-ratchet bypass committed",
    "H4": "Bloat exception state without ADR ref",
    "H5": "Bloat deferred-plan state without plan_ref",
    "H6": "Bloat baseline entry missing on disk",
}

_SEVERITY_BY_CHECK = {
    "H0": "MEDIUM",
    "H1": "HIGH",
    "H2": "MEDIUM",
    "H3": "HIGH",
    "H4": "HIGH",
    "H5": "HIGH",
    "H6": "MEDIUM",
}


def _mk(
    check_id: str,
    status: str,
    detail: str,
    *,
    evidence: list[str] | None = None,
    severity: str | None = None,
    suggested: str | None = None,
) -> Finding:
    return Finding(
        group="H",
        check_id=check_id,
        name=_NAME_BY_CHECK[check_id],
        severity=severity or _SEVERITY_BY_CHECK[check_id],
        source=SOURCE_DETECTIVE_ONLY,
        status=status,
        detail=detail,
        evidence=list(evidence or []),
        suggested_iterate_cmd=suggested,
    )


# ---------------------------------------------------------------------------
# H0 — meta. Distinguishes absent (greenfield → skip) from corrupt (fail).
# ---------------------------------------------------------------------------


def _check_h0(project_root: Path) -> tuple[list[Finding], dict | None]:
    """([h0], doc_or_None). doc=None → callers skip H1-H6 (no data)."""
    if not (project_root / _bb.BASELINE_FILENAME).is_file():
        return ([_mk("H0", "skip",
                     f"no {_bb.BASELINE_FILENAME} (greenfield / pre-adopt)")],
                None)
    doc = _bb.load(project_root)
    if doc is None:
        # File exists but malformed — external-review #4
        return ([_mk("H0", "fail",
                     f"{_bb.BASELINE_FILENAME} unreadable / malformed JSON; "
                     "fix or delete")], None)
    return ([_mk("H0", "pass",
                 f"baseline loaded ({len(doc.get('entries', []))} entries)")],
            doc)


# ---------------------------------------------------------------------------
# Path resolution + traversal guard
# ---------------------------------------------------------------------------


def _resolve_under_root(project_root: Path,
                        rel: str) -> tuple[Path | None, str | None]:
    """Resolve ``rel`` under root; (None, err) on any traversal failure."""
    if not rel:
        return None, "empty path"
    try:
        resolved = (project_root / rel).resolve()
    except (OSError, RuntimeError) as exc:
        return None, f"could not resolve: {exc!r}"
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return None, f"path escapes project_root: {rel!r}"
    return resolved, None


# ---------------------------------------------------------------------------
# H1 — Drift. Reuses producer's scan so writer + audit cannot disagree.
# ---------------------------------------------------------------------------


def _check_h1(project_root: Path, baseline_paths: set[str]) -> Finding:
    oversize = _bb.scan(project_root)
    drift = [e for e in oversize if e["path"] not in baseline_paths]
    if not drift:
        return _mk(
            "H1", "pass",
            f"all {len(oversize)} oversize file(s) are listed in baseline"
            if oversize else "no oversize files on disk",
        )
    detail = "; ".join(
        f"{e['path']} ({e['current']} > {e['limit']})" for e in drift[:5]
    )
    if len(drift) > 5:
        detail += f"; (+{len(drift) - 5} more)"
    evidence = [json.dumps(e, sort_keys=True) for e in drift]
    return _mk("H1", "fail", detail, evidence=evidence,
               suggested=("/shipwright-iterate --type change "
                          "\"add files to shipwright_bloat_baseline.json "
                          "or split them — see Group H1\""))


# ---------------------------------------------------------------------------
# H6 — stale entries (missing on disk OR path-traversal). Run FIRST so
# H2-H5 can skip stale entries safely.
# ---------------------------------------------------------------------------


def _partition_entries(
    project_root: Path,
    entries: list[dict],
) -> tuple[list[tuple[dict, Path]], list[tuple[dict, str]]]:
    """Split entries into (resolvable, stale) lists.

    A resolvable entry is one whose ``path`` exists on disk AND lives
    under ``project_root`` (path-traversal guard).
    """
    resolvable: list[tuple[dict, Path]] = []
    stale: list[tuple[dict, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if not isinstance(rel, str):
            stale.append((entry, "path field missing or non-string"))
            continue
        resolved, err = _resolve_under_root(project_root, rel)
        if resolved is None or err is not None:
            stale.append((entry, err or "unresolvable"))
            continue
        if not resolved.is_file():
            stale.append((entry, "file does not exist on disk"))
            continue
        resolvable.append((entry, resolved))
    return resolvable, stale


def _check_h6(stale: list[tuple[dict, str]]) -> Finding:
    if not stale:
        return _mk("H6", "pass", "all baseline entries resolve on disk")
    detail = "; ".join(
        f"{entry.get('path', '?')}: {reason}" for entry, reason in stale[:5]
    )
    if len(stale) > 5:
        detail += f"; (+{len(stale) - 5} more)"
    evidence = [f"{e.get('path', '?')}: {r}" for e, r in stale]
    return _mk("H6", "fail", detail, evidence=evidence,
               suggested=("/shipwright-iterate --type change "
                          "\"prune stale entries from "
                          "shipwright_bloat_baseline.json\""))


# ---------------------------------------------------------------------------
# H2 / H3 / H4 / H5 — entry-shape audits. All scoped to resolvable entries.
# ---------------------------------------------------------------------------


def _check_h2(resolvable: list[tuple[dict, Path]]) -> Finding:
    suggestions: list[tuple[str, int, int]] = []  # path, recorded, actual
    for entry, path in resolvable:
        recorded = entry.get("current")
        if not isinstance(recorded, int):
            continue
        actual = _bb._file_newlines(path)
        if actual < recorded:
            suggestions.append((entry["path"], recorded, actual))
    if not suggestions:
        return _mk("H2", "pass",
                   "baseline current matches on-disk LOC for all entries")
    detail = "; ".join(
        f"{p}: recorded={r} actual={a}" for p, r, a in suggestions[:5]
    )
    if len(suggestions) > 5:
        detail += f"; (+{len(suggestions) - 5} more)"
    evidence = [f"{p}: recorded={r} actual={a}"
                for p, r, a in suggestions]
    return _mk("H2", "fail", detail, evidence=evidence,
               suggested=("/shipwright-iterate --type change "
                          "\"tighten shipwright_bloat_baseline.json — "
                          "see Group H2 ratchet-suggestions\""))


def _check_state_with_required(
    check_id: str,
    state_value: str,
    required_field: str,
    resolvable: list[tuple[dict, Path]],
) -> Finding:
    """Common pattern for H3/H4/H5: entries with a given state must
    carry a non-empty ``required_field`` (or, for H3, just the state's
    presence is itself the bypass signal)."""
    offenders: list[str] = []
    matched_total = 0
    for entry, _path in resolvable:
        if entry.get("state") != state_value:
            continue
        matched_total += 1
        if required_field == "":
            # H3 — presence of state IS the finding (no required field)
            offenders.append(entry.get("path", "?"))
            continue
        value = entry.get(required_field)
        if not isinstance(value, str) or not value.strip():
            offenders.append(entry.get("path", "?"))
    if not offenders:
        if matched_total == 0:
            return _mk(check_id, "pass",
                       f"no entries with state={state_value!r}")
        return _mk(check_id, "pass",
                   f"all {matched_total} entries with state={state_value!r} "
                   f"carry {required_field!r}")
    detail = "; ".join(offenders[:5])
    if len(offenders) > 5:
        detail += f"; (+{len(offenders) - 5} more)"
    return _mk(check_id, "fail", detail, evidence=list(offenders))


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


def run(
    project_root: Path,
    config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run H0-H6 and return Findings in canonical ID order."""
    project_root = Path(project_root)
    out, doc = _check_h0(project_root)
    if doc is None:
        # H0 already reported skip/fail; no entries to audit downstream.
        return out

    entries = doc.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    resolvable, stale = _partition_entries(project_root, entries)
    baseline_paths = {
        e.get("path") for e in entries if isinstance(e, dict)
        and isinstance(e.get("path"), str)
    }

    out.append(_check_h1(project_root, baseline_paths))
    out.append(_check_h2(resolvable))
    out.append(_check_state_with_required(
        "H3", "anti-ratchet", "", resolvable,
    ))
    out.append(_check_state_with_required(
        "H4", "exception", "adr", resolvable,
    ))
    out.append(_check_state_with_required(
        "H5", "deferred-plan", "plan_ref", resolvable,
    ))
    out.append(_check_h6(stale))
    return out
