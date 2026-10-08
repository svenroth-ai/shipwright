"""Support for the ``check_rtm_coverage`` commit hook (kept out of the hook file).

Threshold/baseline config, the measurement cascade (manifest first, legacy RTM
section line only when no manifest file exists), the legacy RTM readers and the
exact-rational gate comparison, and which repo a commit command targets. Pure apart
from reading project files (and scoping ``GIT_DIR`` around a measurement).
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import compliance_override as override  # noqa: F401 - the hook reaches it as lib.override
import rtm_manifest_coverage as manifest_cov
from git_commit_target import commit_targets

DEFAULT_THRESHOLD = 0.80
_RTM_RELPATH = Path(".shipwright/compliance/traceability-matrix.md")
_NOT_EVALUATING = "the 80% commit gate is NOT evaluating"


def pct_text(value: float) -> str:
    """A fraction as a percent without float noise (0.29 -> '29', 0.795 -> '79.5')."""
    return f"{round(value * 100, 6):g}"


def _exact(value: float) -> Fraction:
    return Fraction(str(round(value, 6)))


def get_coverage_from_rtm(project_root: str) -> int | None:
    """Legacy: the RTM's 'Traceability coverage NN%' (build sections with a commit)."""
    try:
        content = (Path(project_root) / _RTM_RELPATH).read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"Traceability coverage\s*\|\s*(\d+)%", content)
    return int(match.group(1)) if match else None


def find_uncovered_sections(project_root: str) -> list[str]:
    """Legacy: RTM table rows whose commit cell is empty."""
    uncovered: list[str] = []
    try:
        with open(Path(project_root) / _RTM_RELPATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("|") and "| — |" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3 and parts[2]:
                        uncovered.append(parts[2])
    except OSError:
        pass
    return uncovered


@contextmanager
def git_env(env: dict[str, str]):
    """``GIT_DIR`` / ``GIT_WORK_TREE`` for the git reads inside the block, then restored."""
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _below_threshold(root: str, env: dict[str, str]) -> bool:
    with git_env(env):
        measured, _warnings = measure(root)
    return measured is not None and not meets(measured, read_threshold(root)[0])


def target_root(command: str, cwd: Any,
                default: Callable[[], str]) -> tuple[str, dict[str, str], list[str]]:
    """``(project root, git env, warnings)`` for the repo *command* commits to.

    *default* (the managed project root) for a commit naming no location
    (``git_commit_target``) or a directory that does not exist (WARN). The git env
    carries ``GIT_DIR`` / ``GIT_WORK_TREE`` for a ``--git-dir`` commit. A command
    committing to several repos is judged on the first one below its threshold
    (else the first), with a WARN naming them all.
    """
    cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    warnings: list[str] = []
    roots: dict[str, dict[str, str]] = {}  # insertion-ordered, one entry per repo
    for target in commit_targets(command, cwd):
        if target is not None and not target.project_root.is_dir():
            warnings.append(f"the commit names {target.project_root}, which is not a "
                            f"directory; measured {default()} instead")
            target = None
        if target is None:
            roots.setdefault(default(), {})
        else:
            roots.setdefault(str(target.project_root), {} if target.git_dir is None else {
                "GIT_DIR": str(target.git_dir), "GIT_WORK_TREE": str(target.project_root)})
    if not roots:
        return default(), {}, warnings
    chosen = next(iter(roots))
    if len(roots) > 1:
        chosen = next((root for root, env in roots.items() if _below_threshold(root, env)),
                      chosen)
        warnings.append(f"this command commits to {len(roots)} repos ("
                        + ", ".join(roots) + f"); judged on {chosen}, the first below "
                        "threshold or else the first -- commit to each repo separately")
    return chosen, roots[chosen], warnings


def read_threshold(project_root: str) -> tuple[float, list[str], float | None]:
    """Effective threshold, WARN lines for config that could not be honoured, baseline.

    ``enforcement.rtm_coverage_min`` (default 0.80) is the target. A project far
    below it records its measured coverage as ``enforcement.rtm_coverage_baseline``
    and the gate ratchets from there (``min`` of the two) -- otherwise the
    soft-block fires on every commit and its override turns into noise.
    """
    warnings: list[str] = []
    baseline: float | None = None
    config_path = os.path.join(project_root, "shipwright_compliance_config.json")
    if not os.path.exists(config_path):
        return DEFAULT_THRESHOLD, warnings, baseline
    try:
        with open(config_path, encoding="utf-8") as f:
            enforcement = json.load(f).get("enforcement", {})
        if not isinstance(enforcement, dict):
            raise ValueError("enforcement is not an object")
    except (json.JSONDecodeError, OSError, AttributeError, ValueError):
        return DEFAULT_THRESHOLD, [
            "shipwright_compliance_config.json is unreadable; using the default "
            f"{pct_text(DEFAULT_THRESHOLD)}% threshold"
        ], baseline
    threshold = DEFAULT_THRESHOLD
    for key in ("rtm_coverage_min", "rtm_coverage_baseline"):
        if key not in enforcement:
            continue
        value = enforcement[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            warnings.append(f"enforcement.{key} must be a number between 0 and 1; ignored")
        elif key == "rtm_coverage_min":
            threshold = float(value)
        else:
            baseline = float(value)
            threshold = min(threshold, baseline)
    return threshold, warnings, baseline


def measure(project_root: str) -> tuple[dict[str, Any] | None, list[str]]:
    """``(measurement, warnings)``; measurement is ``None`` when nothing is measurable.

    Requirement coverage from the committed manifest; the legacy section line only
    when there is no manifest at all (an unexpected git failure with no working-tree
    copy is "unreadable", not "absent": WARN, never the section line). A non-current schema or a manifest with no
    executed result is unmeasurable (WARN), never 0%. Every case that used to allow
    silently says why in a WARN -- except a project with no compliance data at all.
    """
    warnings: list[str] = []
    manifest, problem, notes = manifest_cov.read_manifest_noted(project_root)
    warnings.extend(notes)  # the git (index / HEAD) read failed unexpectedly
    if problem:
        warnings.append(problem)
    if manifest is not None:
        schema = manifest_cov.schema_problem(manifest)
        if schema:  # never relabel a stale-shape read as coverage, nor fall back
            return None, [*warnings, schema, _NOT_EVALUATING]
        cov = manifest_cov.compute_coverage(manifest, project_root)
        stale = manifest_cov.staleness_warning(manifest, project_root)
        if stale:
            warnings.append(stale)
        unmeasured = cov["fr"]["not_measured"]
        if unmeasured and cov["fr"]["total"]:
            warnings.append(
                f"{unmeasured} of {unmeasured + cov['fr']['total']} requirements not measured "
                "(every linked test not_run in the last evidence run); left out of the "
                "figure, neither covered nor uncovered")
        if cov["fr"]["pct"] is None and not unmeasured:
            warnings.append(
                "traceability manifest lists no active requirements; nothing to measure "
                f"({_NOT_EVALUATING})"
            )
            return None, warnings
        unexecuted = manifest_cov.execution_problem(manifest)
        if unexecuted:
            return None, [*warnings, unexecuted, _NOT_EVALUATING]
        return {"kind": "requirements", "pct": cov["fr"]["pct"], "coverage": cov,
                "source_commit": manifest.get("source_commit")}, warnings
    if problem or any(n.startswith(manifest_cov.UNREADABLE) for n in notes):
        # present but unreadable, or git failed unexpectedly with no working-tree copy:
        # never relabel build-section coverage as the answer
        warnings.append(_NOT_EVALUATING)
        return None, warnings
    legacy = get_coverage_from_rtm(project_root)
    if legacy is not None:
        return {"kind": "sections", "pct": legacy}, warnings
    compliance_dir = Path(project_root) / ".shipwright" / "compliance"
    if compliance_dir.is_dir() and any(compliance_dir.iterdir()):
        warnings.append(
            "compliance data exists but no coverage figure could be read "
            "(no manifest requirements, no RTM 'Traceability coverage' line); "
            "the 80% commit gate is NOT evaluating"
        )
    return None, warnings


def ratio(m: dict[str, Any]) -> Fraction:
    """The measured coverage as an exact fraction of 1 (the display pct is floored)."""
    if m["kind"] == "requirements":
        fr = m["coverage"]["fr"]
        return Fraction(fr["covered"], fr["total"])
    return Fraction(m["pct"], 100)


def meets(m: dict[str, Any], threshold: float) -> bool:
    """Exact comparison ``covered/total >= threshold``; never rounds a shortfall away."""
    return ratio(m) >= _exact(threshold)


def above_baseline(m: dict[str, Any], baseline: float) -> bool:
    return ratio(m) > _exact(baseline)


def describe(m: dict[str, Any]) -> str:
    if m["kind"] != "requirements":
        return (
            f"RTM build-section coverage {m['pct']}% (share of build sections with a "
            "commit; no requirement manifest)"
        )
    fr, ac = m["coverage"]["fr"], m["coverage"]["ac"]
    return (
        f"Requirement coverage {fr['pct']}% ({fr['covered']}/{fr['total']} active requirements "
        f"have an executed-passing bound test; ACs {ac['covered']}/{ac['total']}"
        + (f" = {ac['pct']}%" if ac["pct"] is not None else "")
        + f", AC inventory from {ac.get('source', 'manifest')}"
        + (f"; {fr['not_measured']} more not measured" if fr.get("not_measured") else "")
        + ")"
    )
