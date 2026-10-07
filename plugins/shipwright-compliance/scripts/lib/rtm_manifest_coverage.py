"""Requirement coverage read from the working-tree copy of the committed manifest.

The ``check_rtm_coverage`` commit hook used to gate on the RTM's
"Traceability coverage" line, which is the share of *build sections that have a
commit* -- not requirement coverage. An adopted project has no build sections, so
the RTM carries no such line at all and the hook allowed every commit, silently.

This module computes the number the hook's name promises, from
``.shipwright/compliance/test-traceability.json`` (the manifest the collector
commits; the hook reads the working-tree copy of that committed/cached file as-is
and never regenerates it -- the hook fires on every ``git commit``):

* **FR metric** -- counting unit: an *active* requirement. Covered when at least
  one test bound to it is ``status == "enabled"`` AND ``executed == "pass"``.
* **AC metric** -- counting unit: one acceptance criterion of an active
  requirement, covered under the same rule. Reported next to the FR metric, never
  mixed into it.

"Passing" is the manifest's own join of binding to execution result: a skipped
test (``status != "enabled"``), a test that never ran or failed, and a test whose
result is missing all count as NOT covered. A parametrized test is a single
function-level link whose ``executed`` already folds its cases.

**Accepted risk.** The join of a binding to its execution result *by commit* is
done by the traceability collector when it builds the manifest; this module does
NOT re-verify it. A result recorded for an older commit therefore reads as
passing until the manifest is regenerated (F11 / CI). The staleness WARN
(:func:`staleness_warning`) is the mitigation, not a proof.

Pure apart from reading project files and the optional ``git`` probe in
:func:`commits_behind`.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_RELPATH = Path(".shipwright") / "compliance" / "test-traceability.json"
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
    """
    try:
        text = (Path(project_root) / spec_path).read_text(encoding="utf-8-sig")
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


def read_manifest(project_root: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(manifest, None)``, ``(None, None)`` when absent, ``(None, reason)`` when unreadable."""
    path = Path(project_root) / MANIFEST_RELPATH
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, f"cannot read {MANIFEST_RELPATH.as_posix()}: {type(exc).__name__}"
    if not isinstance(data, dict):
        return None, f"{MANIFEST_RELPATH.as_posix()} is not a JSON object"
    return data, None


def commits_behind(project_root: str | Path, source_commit: str) -> int | None:
    """Commits between the manifest's ``source_commit`` and HEAD; ``None`` if unknown."""
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "rev-list", "--count", f"{source_commit}..HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def staleness_warning(manifest: dict[str, Any], project_root: str | Path,
                      now: datetime | None = None) -> str | None:
    """A WARN sentence when the manifest is old, or ``None`` when it is fresh enough."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    try:
        generated = datetime.fromisoformat(str(manifest.get("generated_at")))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age = (now - generated).days
        if age > STALE_AFTER_DAYS:
            reasons.append(f"{age} days old")
    except (TypeError, ValueError):
        reasons.append("carries no readable generated_at")
    source = manifest.get("source_commit")
    if isinstance(source, str) and re.fullmatch(r"[0-9a-fA-F]{7,64}", source):
        behind = commits_behind(project_root, source)
        if behind is not None and behind > STALE_AFTER_COMMITS:
            reasons.append(f"{behind} commits behind HEAD")
    if not reasons:
        return None
    return (
        "traceability manifest is " + " and ".join(reasons)
        + "; coverage below is computed from that snapshot "
        "(regenerate it in F11 / CI -- this hook never does)"
    )
