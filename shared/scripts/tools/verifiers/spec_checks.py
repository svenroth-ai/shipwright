"""Spec-category checks (Phase-Quality PR 4 — S1-S10). See plan § 3.

Tier-1 (FAIL): S1 spec.md exists + non-empty + ≥1 FR heading; S2 iterate spec
file for medium+ (SKIP below medium); S6 CLAUDE.md non-empty; S8 README.md
non-empty. Tier-2 (WARN, ``provenance="unverified_marker"``, ``tier=2``): S3
mini-plan (medium+); S4 FR-preservation (removed FR keeps ``deprecated`` in
git history); S5 FR-coherence (Description + Acceptance Criteria per FR); S7
CLAUDE.md Structure block; S9 README-freshness (feature + UI-facing); S10
CLAUDE.md-sync (new top-level dirs). The S2/S3 run_id guard lives in
``_iterate_run_id.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py.
PLANNING_DIRNAME = ".shipwright/planning"

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import (  # noqa: E402
    extract_structure_block,
)
from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    make_finding,
)
from tools.verifiers._iterate_run_id import (  # noqa: E402
    unresolvable_run_id_skip,
)
from lib.spec_parser import (  # noqa: E402
    compute_fr_coherence,
    count_fr_headings,
    read_top_level_spec,
)


# ---------------------------------------------------------------------------
# Names + remediations
# ---------------------------------------------------------------------------

S1_NAME  = "S1 .shipwright/agent_docs/spec.md exists with ≥1 FR heading"
S2_NAME  = "S2 iterate spec file exists for medium+ complexity"
S3_NAME  = "S3 iterate mini-plan file exists for medium+ complexity"
S4_NAME  = "S4 removed FRs retain status=deprecated"
S5_NAME  = "S5 every FR has Description + Acceptance Criteria"
S6_NAME  = "S6 CLAUDE.md exists and is non-empty"
S7_NAME  = "S7 CLAUDE.md has a Structure block"
S8_NAME  = "S8 README.md exists and is non-empty"
S9_NAME  = "S9 README.md touched recently on UI-facing iterate features"
S10_NAME = "S10 CLAUDE.md touched when new top-level directories appear"

S1_REMEDIATION = (
    "Create .shipwright/agent_docs/spec.md with at least one `## FR-...` heading "
    "(see shared/templates/spec.md)."
)
S2_REMEDIATION = (
    "Create .shipwright/planning/iterate/<run_id>.md during the iterate F3 step. "
    "Medium+ complexity iterates require a per-run spec."
)
S3_REMEDIATION = (
    "Create .shipwright/planning/iterate/<run_id>-miniplan.md during the iterate "
    "Plan step. Heuristic — WARN only."
)
S4_REMEDIATION = (
    "If an FR was truly removed, mark it `status: deprecated` in the "
    "spec instead of deleting it, so traceability history is preserved."
)
S5_REMEDIATION = (
    "For each FR heading, add **Description:** ... and "
    "**Acceptance Criteria:** sections. Heuristic — tune per-project "
    "if specs use another format."
)
S6_REMEDIATION = (
    "Create a project-root CLAUDE.md describing WHAT the project does, "
    "HOW it's structured, and conventions. See docs/guide.md chapter 4."
)
S7_REMEDIATION = (
    "Add a `## Structure` block (fenced bash code) to CLAUDE.md so "
    "drift detection can verify directory layout."
)
S8_REMEDIATION = (
    "Create README.md at the project root. Every GitHub project "
    "should ship a README."
)
S9_REMEDIATION = (
    "If this iterate changed user-facing UI, update README.md so the "
    "feature list stays current. Heuristic — WARN only."
)
S10_REMEDIATION = (
    "New top-level directories should be documented in CLAUDE.md's "
    "Structure block. Heuristic — WARN only."
)


# Marker paths relative to project_root
_CLAUDE_MD = "CLAUDE.md"
_README_MD = "README.md"

# Directories whose edits count as "UI-facing" for S9 (plan § 3 S9).
_UI_PATH_PREFIXES: tuple[str, ...] = (
    "webui/client/",
    "webui/",
    "frontend/",
    "client/",
    "web/",
    "app/",
    "src/components/",
    "src/pages/",
    "mobile/",
)

# Window size for S9/S10 git-log lookback.
_GIT_RECENT_COMMITS = 10


# ---------------------------------------------------------------------------
# Iterate context resolution (run_config.iterate_history[run_id])
# ---------------------------------------------------------------------------

def _read_iterate_entry(project_root: Path, run_id: str) -> dict[str, Any] | None:
    """Return the iterate entry for ``run_id`` or ``None``.

    Reads from the merged legacy-array + per-file directory store via
    ``lib.iterate_entry.read_iterate_entries``. Falls back to the most
    recent entry when ``run_id`` is not present — mid-flow finalize may
    reach this verifier before the entry itself is written.
    """
    # Deferred import so the module stays safe to import without the
    # sibling ``lib/`` path on sys.path (pytest adds it via conftest).
    import sys
    _scripts_root = Path(__file__).resolve().parents[2]
    if str(_scripts_root) not in sys.path:
        sys.path.insert(0, str(_scripts_root))
    from lib.iterate_entry import read_iterate_entries

    entries = read_iterate_entries(project_root)
    if not entries:
        return None
    for entry in entries:
        if entry.get("run_id") == run_id:
            return entry
    return entries[-1]  # tail fallback for mid-flow finalize


def _iterate_complexity(project_root: Path, run_id: str) -> str | None:
    entry = _read_iterate_entry(project_root, run_id)
    if not entry:
        return None
    value = entry.get("complexity")
    if isinstance(value, str) and value:
        return value.lower()
    return None


def _iterate_category(project_root: Path, run_id: str) -> str | None:
    entry = _read_iterate_entry(project_root, run_id)
    if not entry:
        return None
    value = entry.get("type") or entry.get("category")
    if isinstance(value, str) and value:
        return value.lower()
    return None


def _is_medium_or_larger(complexity: str | None) -> bool:
    return (complexity or "").lower() in {"medium", "large"}


# ---------------------------------------------------------------------------
# S1 — top-level spec exists + has FR headings
# ---------------------------------------------------------------------------

def check_s1_top_level_spec(project_root: Path) -> dict[str, Any]:
    """S1 — spec.md exists, non-empty, with ≥1 FR heading."""
    content = read_top_level_spec(project_root)
    if content is None:
        return make_finding(
            "S1", STATUS_FAIL,
            ".shipwright/agent_docs/spec.md missing",
            name=S1_NAME, remediation=S1_REMEDIATION,
        )
    if not content.strip():
        return make_finding(
            "S1", STATUS_FAIL,
            ".shipwright/agent_docs/spec.md empty",
            name=S1_NAME, remediation=S1_REMEDIATION,
        )
    n = count_fr_headings(content)
    if n < 1:
        return make_finding(
            "S1", STATUS_FAIL,
            ".shipwright/agent_docs/spec.md has no FR headings",
            name=S1_NAME, remediation=S1_REMEDIATION,
        )
    return make_finding(
        "S1", STATUS_PASS,
        f".shipwright/agent_docs/spec.md has {n} FR heading(s)",
        name=S1_NAME,
    )


# ---------------------------------------------------------------------------
# S2 — iterate spec file for medium+ complexity
# ---------------------------------------------------------------------------

def _iter_spec_candidates(project_root: Path, run_id: str) -> list[Path]:
    """Return plausible iterate-spec paths for ``run_id``."""
    base = project_root / PLANNING_DIRNAME / "iterate"
    if not base.is_dir():
        return []
    # Any file whose stem contains run_id (date-desc or explicit run_id)
    # counts as a spec file. The "-miniplan" suffix is reserved for S3.
    hits: list[Path] = []
    for p in base.glob("*.md"):
        stem = p.stem.lower()
        if "miniplan" in stem:
            continue
        if run_id and run_id.lower() in stem:
            hits.append(p)
    return hits


def check_s2_iterate_spec(project_root: Path, run_id: str) -> dict[str, Any]:
    """S2 — iterate spec file exists for medium+ complexity."""
    guard = unresolvable_run_id_skip(  # AC-5/AC-6 (run_id=unknown bug)
        project_root, run_id,
        _iter_spec_candidates(project_root, run_id), "S2", S2_NAME)
    if guard is not None:
        return guard
    complexity = _iterate_complexity(project_root, run_id)
    if complexity is None:
        return make_finding(
            "S2", STATUS_SKIP,
            f"no iterate entry for run_id={run_id} — complexity unknown",
            name=S2_NAME,
        )
    if not _is_medium_or_larger(complexity):
        return make_finding(
            "S2", STATUS_SKIP,
            f"complexity={complexity} — iterate spec not required "
            "below medium",
            name=S2_NAME,
        )

    hits = _iter_spec_candidates(project_root, run_id)
    if not hits:
        return make_finding(
            "S2", STATUS_FAIL,
            f"no .shipwright/planning/iterate/*.md file contains run_id={run_id} "
            f"(complexity={complexity})",
            name=S2_NAME, remediation=S2_REMEDIATION,
        )
    rel = hits[0].relative_to(project_root).as_posix()
    return make_finding(
        "S2", STATUS_PASS,
        f"iterate spec present at {rel}",
        name=S2_NAME,
    )


# ---------------------------------------------------------------------------
# S3 — iterate mini-plan for medium+ complexity (Tier-2)
# ---------------------------------------------------------------------------

def _iter_miniplan_candidates(project_root: Path, run_id: str) -> list[Path]:
    base = project_root / PLANNING_DIRNAME / "iterate"
    if not base.is_dir():
        return []
    return [
        p for p in base.glob("*.md")
        if "miniplan" in p.stem.lower()
        and run_id and run_id.lower() in p.stem.lower()
    ]


def check_s3_iterate_miniplan(project_root: Path, run_id: str) -> dict[str, Any]:
    """S3 — mini-plan file exists for medium+ iterates (Tier-2, WARN)."""
    guard = unresolvable_run_id_skip(  # AC-5/AC-6 (same guard as S2)
        project_root, run_id,
        _iter_miniplan_candidates(project_root, run_id), "S3", S3_NAME,
        provenance="unverified_marker")
    if guard is not None:
        return guard
    complexity = _iterate_complexity(project_root, run_id)
    if complexity is None:
        return make_finding(
            "S3", STATUS_SKIP,
            f"no iterate entry for run_id={run_id}",
            name=S3_NAME, provenance="unverified_marker",
        )
    if not _is_medium_or_larger(complexity):
        return make_finding(
            "S3", STATUS_SKIP,
            f"complexity={complexity} — mini-plan not required below medium",
            name=S3_NAME,
        )

    hits = _iter_miniplan_candidates(project_root, run_id)
    if not hits:
        return make_finding(
            "S3", STATUS_WARN,
            f"no .shipwright/planning/iterate/*-miniplan.md for run_id={run_id} "
            f"(complexity={complexity})",
            name=S3_NAME, remediation=S3_REMEDIATION,
            provenance="unverified_marker",
        )
    rel = hits[0].relative_to(project_root).as_posix()
    return make_finding(
        "S3", STATUS_PASS,
        f"mini-plan present at {rel}",
        name=S3_NAME,
    )


# ---------------------------------------------------------------------------
# S4 — FR preservation (Tier-2, WARN)
# ---------------------------------------------------------------------------

def _run_git(project_root: Path, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a git command inside ``project_root``.

    Returns ``(rc, stdout, stderr)``. Git binary missing or non-repo
    returns ``(-1, "", <error msg>)`` so callers can SKIP cleanly.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            capture_output=True, text=True,
            encoding="utf-8", errors="ignore",
            timeout=timeout,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return -1, "", str(exc)


def _git_available(project_root: Path) -> bool:
    rc, _, _ = _run_git(project_root, "rev-parse", "--is-inside-work-tree")
    return rc == 0


def check_s4_fr_preservation(project_root: Path) -> dict[str, Any]:
    """S4 — removed FR ids still marked deprecated. Tier-2 WARN-only."""
    if not _git_available(project_root):
        return make_finding(
            "S4", STATUS_SKIP,
            "git unavailable or not a git work tree — partial checkout",
            name=S4_NAME, provenance="unverified_marker",
        )

    # Compare HEAD with the last commit that touched the top-level spec.
    # We look at the set of FR ids in HEAD vs 10 commits back; any id
    # that disappeared without a `status: deprecated` marker anywhere in
    # the spec body gets flagged.
    rc, log_out, _ = _run_git(
        project_root,
        "log", "-n", "10", "--pretty=format:%H", "--",
        ".shipwright/agent_docs/spec.md", PLANNING_DIRNAME,
    )
    if rc != 0 or not log_out.strip():
        return make_finding(
            "S4", STATUS_SKIP,
            "no recent spec history — nothing to compare",
            name=S4_NAME, provenance="unverified_marker",
        )
    commits = [c.strip() for c in log_out.splitlines() if c.strip()]
    if len(commits) < 2:
        return make_finding(
            "S4", STATUS_SKIP,
            "only one spec commit in history — no delta to compare",
            name=S4_NAME, provenance="unverified_marker",
        )

    baseline = commits[-1]
    rc, diff_out, _ = _run_git(
        project_root,
        "diff", baseline, "HEAD",
        "--", ".shipwright/agent_docs/spec.md",
    )
    if rc != 0:
        return make_finding(
            "S4", STATUS_SKIP,
            "git diff failed — skipping FR preservation",
            name=S4_NAME, provenance="unverified_marker",
        )

    import re as _re
    fr_pattern = _re.compile(r"FR[-\s]?\d+(?:\.\d+)*")
    removed: set[str] = set()
    added: set[str] = set()
    for line in diff_out.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            removed.update(fr_pattern.findall(line))
        elif line.startswith("+") and not line.startswith("+++"):
            added.update(fr_pattern.findall(line))

    truly_removed = removed - added
    if not truly_removed:
        return make_finding(
            "S4", STATUS_PASS,
            "no FR ids removed in last 10 spec commits",
            name=S4_NAME,
        )

    # Inspect current spec for a `status: deprecated` marker within 5
    # lines of each removed id. Anything left is a potential problem.
    content = read_top_level_spec(project_root) or ""
    undeprecated: list[str] = []
    lines = content.splitlines()
    for fr_id in sorted(truly_removed):
        window = "\n".join(
            lines[i:i + 6]
            for i, line in enumerate(lines)
            if fr_id in line
        )
        if "status: deprecated" not in window.lower():
            undeprecated.append(fr_id)

    if not undeprecated:
        return make_finding(
            "S4", STATUS_PASS,
            f"{len(truly_removed)} removed FR(s) all marked deprecated",
            name=S4_NAME,
        )

    preview = ", ".join(undeprecated[:5])
    suffix = f" (+{len(undeprecated) - 5} more)" if len(undeprecated) > 5 else ""
    return make_finding(
        "S4", STATUS_WARN,
        f"{len(undeprecated)} removed FR(s) without status=deprecated: "
        f"{preview}{suffix}",
        name=S4_NAME, remediation=S4_REMEDIATION,
        provenance="unverified_marker",
    )


# ---------------------------------------------------------------------------
# S5 — FR coherence (Tier-2, WARN)
# ---------------------------------------------------------------------------

def check_s5_fr_coherence(project_root: Path) -> dict[str, Any]:
    """S5 — every FR heading has Description + Acceptance."""
    report = compute_fr_coherence(project_root)
    if report.total_frs == 0:
        return make_finding(
            "S5", STATUS_SKIP,
            "no FR headings found — nothing to audit",
            name=S5_NAME, provenance="unverified_marker",
        )
    if report.ok:
        return make_finding(
            "S5", STATUS_PASS,
            f"all {report.total_frs} FR(s) have Description + Acceptance",
            name=S5_NAME,
        )

    issues: list[str] = []
    if report.missing_both:
        preview = ", ".join(report.missing_both[:3])
        suffix = f" (+{len(report.missing_both) - 3})" if len(report.missing_both) > 3 else ""
        issues.append(f"{len(report.missing_both)} missing both: {preview}{suffix}")
    if report.missing_description:
        preview = ", ".join(report.missing_description[:3])
        suffix = f" (+{len(report.missing_description) - 3})" if len(report.missing_description) > 3 else ""
        issues.append(f"{len(report.missing_description)} no desc: {preview}{suffix}")
    if report.missing_acceptance:
        preview = ", ".join(report.missing_acceptance[:3])
        suffix = f" (+{len(report.missing_acceptance) - 3})" if len(report.missing_acceptance) > 3 else ""
        issues.append(f"{len(report.missing_acceptance)} no accept: {preview}{suffix}")

    return make_finding(
        "S5", STATUS_WARN,
        "; ".join(issues),
        name=S5_NAME, remediation=S5_REMEDIATION,
        provenance="unverified_marker",
    )


# ---------------------------------------------------------------------------
# S6 — CLAUDE.md exists + non-empty
# ---------------------------------------------------------------------------

def _read_text_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def check_s6_claude_md_exists(project_root: Path) -> dict[str, Any]:
    content = _read_text_or_none(project_root / _CLAUDE_MD)
    if content is None:
        return make_finding(
            "S6", STATUS_FAIL,
            "CLAUDE.md missing at project root",
            name=S6_NAME, remediation=S6_REMEDIATION,
        )
    if not content.strip():
        return make_finding(
            "S6", STATUS_FAIL,
            "CLAUDE.md exists but is empty",
            name=S6_NAME, remediation=S6_REMEDIATION,
        )
    return make_finding(
        "S6", STATUS_PASS,
        f"CLAUDE.md present ({len(content)} chars)",
        name=S6_NAME,
    )


# ---------------------------------------------------------------------------
# S7 — CLAUDE.md has Structure block (Tier-2)
# ---------------------------------------------------------------------------

def check_s7_claude_md_structure(project_root: Path) -> dict[str, Any]:
    content = _read_text_or_none(project_root / _CLAUDE_MD)
    if content is None:
        return make_finding(
            "S7", STATUS_SKIP,
            "CLAUDE.md missing — S6 covers this",
            name=S7_NAME, provenance="unverified_marker",
        )
    block = extract_structure_block(content)
    if block is None:
        return make_finding(
            "S7", STATUS_WARN,
            "CLAUDE.md missing a `## Structure` code block "
            "(used by check_drift.py)",
            name=S7_NAME, remediation=S7_REMEDIATION,
            provenance="unverified_marker",
        )
    return make_finding(
        "S7", STATUS_PASS,
        f"Structure block present ({len(block.splitlines())} line(s))",
        name=S7_NAME,
    )


# ---------------------------------------------------------------------------
# S8 — README.md
# ---------------------------------------------------------------------------

def check_s8_readme_exists(project_root: Path) -> dict[str, Any]:
    content = _read_text_or_none(project_root / _README_MD)
    if content is None:
        return make_finding(
            "S8", STATUS_FAIL,
            "README.md missing at project root",
            name=S8_NAME, remediation=S8_REMEDIATION,
        )
    if not content.strip():
        return make_finding(
            "S8", STATUS_FAIL,
            "README.md exists but is empty",
            name=S8_NAME, remediation=S8_REMEDIATION,
        )
    return make_finding(
        "S8", STATUS_PASS,
        f"README.md present ({len(content)} chars)",
        name=S8_NAME,
    )


# ---------------------------------------------------------------------------
# S9 — README.md changed in last 10 commits (iterate feature + UI-facing)
# ---------------------------------------------------------------------------

def _is_ui_facing_iterate(project_root: Path) -> bool:
    """True when the latest commits touch known UI paths.

    The heuristic compares the union of paths in the last
    ``_GIT_RECENT_COMMITS`` commits against ``_UI_PATH_PREFIXES``. We
    use the last N commits (not the working tree) because iterate
    F5/F6 already committed its changes by the time the Stop hook
    fires.
    """
    rc, out, _ = _run_git(
        project_root,
        "log", f"-n{_GIT_RECENT_COMMITS}",
        "--name-only", "--pretty=format:",
    )
    if rc != 0:
        return False
    for path in out.splitlines():
        p = path.strip().replace("\\", "/")
        if not p:
            continue
        for prefix in _UI_PATH_PREFIXES:
            if p.startswith(prefix):
                return True
    return False


def _readme_touched_recently(project_root: Path) -> bool:
    rc, out, _ = _run_git(
        project_root,
        "log", f"-n{_GIT_RECENT_COMMITS}",
        "--name-only", "--pretty=format:", "--", _README_MD,
    )
    if rc != 0:
        return False
    return any(_README_MD in line for line in out.splitlines())


def check_s9_readme_freshness(
    project_root: Path, run_id: str,
) -> dict[str, Any]:
    """S9 — README.md fresh on UI-facing iterate features (Tier-2, WARN)."""
    if not _git_available(project_root):
        return make_finding(
            "S9", STATUS_SKIP,
            "git unavailable — cannot inspect recent commits",
            name=S9_NAME, provenance="unverified_marker",
        )

    category = _iterate_category(project_root, run_id)
    if category != "feature":
        return make_finding(
            "S9", STATUS_SKIP,
            f"category={category or 'unknown'} — S9 only runs for features",
            name=S9_NAME,
        )

    if not _is_ui_facing_iterate(project_root):
        return make_finding(
            "S9", STATUS_SKIP,
            "recent commits don't touch known UI paths — "
            "not a user-facing feature",
            name=S9_NAME,
        )

    if _readme_touched_recently(project_root):
        return make_finding(
            "S9", STATUS_PASS,
            f"README.md touched in last {_GIT_RECENT_COMMITS} commit(s)",
            name=S9_NAME,
        )

    return make_finding(
        "S9", STATUS_WARN,
        f"UI-facing iterate feature but README.md not touched in last "
        f"{_GIT_RECENT_COMMITS} commit(s)",
        name=S9_NAME, remediation=S9_REMEDIATION,
        provenance="unverified_marker",
    )


# ---------------------------------------------------------------------------
# S10 — CLAUDE.md touched when new top-level dirs appear (Tier-2)
# ---------------------------------------------------------------------------

def _new_top_level_dirs(project_root: Path) -> list[str]:
    """Return top-level dirs that appeared in last 10 commits but aren't
    listed in CLAUDE.md Structure block.
    """
    rc, out, _ = _run_git(
        project_root,
        "log", f"-n{_GIT_RECENT_COMMITS}",
        "--name-only", "--pretty=format:",
    )
    if rc != 0:
        return []

    recent_top: set[str] = set()
    for path in out.splitlines():
        p = path.strip().replace("\\", "/")
        if not p or "/" not in p:
            continue
        top = p.split("/", 1)[0]
        if top.startswith("."):
            continue
        recent_top.add(top)

    claude = _read_text_or_none(project_root / _CLAUDE_MD) or ""
    block = extract_structure_block(claude) or ""
    documented = set()
    for line in block.splitlines():
        stripped = line.strip().rstrip("/").split("#", 1)[0].strip()
        if stripped:
            documented.add(stripped.split("/", 1)[0])

    return sorted(recent_top - documented)


def _claude_md_touched_recently(project_root: Path) -> bool:
    rc, out, _ = _run_git(
        project_root,
        "log", f"-n{_GIT_RECENT_COMMITS}",
        "--name-only", "--pretty=format:", "--", _CLAUDE_MD,
    )
    if rc != 0:
        return False
    return any(_CLAUDE_MD in line for line in out.splitlines())


def check_s10_claude_md_sync(
    project_root: Path, run_id: str,
) -> dict[str, Any]:
    """S10 — CLAUDE.md touched when new top-level dirs appear (Tier-2)."""
    if not _git_available(project_root):
        return make_finding(
            "S10", STATUS_SKIP,
            "git unavailable — cannot inspect recent commits",
            name=S10_NAME, provenance="unverified_marker",
        )

    category = _iterate_category(project_root, run_id)
    if category not in {"feature", "bug", "bugfix"}:
        return make_finding(
            "S10", STATUS_SKIP,
            f"category={category or 'unknown'} — S10 only runs for "
            "feature/bugfix",
            name=S10_NAME,
        )

    new_dirs = _new_top_level_dirs(project_root)
    if not new_dirs:
        return make_finding(
            "S10", STATUS_PASS,
            "no new top-level directories in recent commits",
            name=S10_NAME,
        )

    if _claude_md_touched_recently(project_root):
        return make_finding(
            "S10", STATUS_PASS,
            f"new top-level dir(s) {new_dirs[:3]} present but "
            "CLAUDE.md was touched recently",
            name=S10_NAME,
        )

    return make_finding(
        "S10", STATUS_WARN,
        f"new top-level dir(s) without CLAUDE.md update: "
        f"{new_dirs[:5]}",
        name=S10_NAME, remediation=S10_REMEDIATION,
        provenance="unverified_marker",
    )


# ---------------------------------------------------------------------------
# Phase → check-list dispatch (plan § 5.1 "Plugin-Coverage")
# ---------------------------------------------------------------------------

_PROJECT_CHECKS: tuple[str, ...] = ("S1", "S5", "S6", "S7", "S8")
_ITERATE_CHECKS: tuple[str, ...] = (
    "S2", "S3", "S4", "S5", "S9", "S10",
)


def run(
    phase: str,
    project_root: Path,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return spec findings for ``phase`` per the Plugin-Coverage table."""
    if phase == "project":
        return [
            check_s1_top_level_spec(project_root),
            check_s5_fr_coherence(project_root),
            check_s6_claude_md_exists(project_root),
            check_s7_claude_md_structure(project_root),
            check_s8_readme_exists(project_root),
        ]
    if phase == "iterate":
        return [
            check_s2_iterate_spec(project_root, run_id),
            check_s3_iterate_miniplan(project_root, run_id),
            check_s4_fr_preservation(project_root),
            check_s5_fr_coherence(project_root),
            check_s9_readme_freshness(project_root, run_id),
            check_s10_claude_md_sync(project_root, run_id),
        ]
    return []


__all__ = [
    "check_s10_claude_md_sync",
    "check_s1_top_level_spec",
    "check_s2_iterate_spec",
    "check_s3_iterate_miniplan",
    "check_s4_fr_preservation",
    "check_s5_fr_coherence",
    "check_s6_claude_md_exists",
    "check_s7_claude_md_structure",
    "check_s8_readme_exists",
    "check_s9_readme_freshness",
    "run",
]
