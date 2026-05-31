"""Filesystem + workflow-YAML scanning for the CI gate-coverage guard.

The I/O layer for ``tools/check_ci_gate_coverage.py``: discovers test-dir roots
and flattens ``.github/workflows/*.yml`` into ``Step`` records. Kept separate
from the policy checks so the guard module stays small and the boundary
(``yaml.safe_load`` of untrusted-ish workflow text) is tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml  # PyYAML — declared root dependency

_EXCLUDE_PARTS = {
    "fixtures", "node_modules", ".venv", "venv", "__pycache__",
    ".worktrees", ".git", ".pytest_cache",
}


@dataclass
class Step:
    workflow: str  # workflow file basename (e.g. "ci.yml")
    job: str
    name: str
    run: str
    uses: str
    continue_on_error: bool


def _has_test_files(d: Path) -> bool:
    return any(d.rglob("test_*.py"))


def _excluded(rel: Path) -> bool:
    return any(part in _EXCLUDE_PARTS for part in rel.parts)


def discover_test_dirs(root: Path) -> list[str]:
    """Return posix-relative test-dir roots that ought to be CI-covered.

    Roots: ``plugins/<seg>/tests`` (single segment), every ``tests``-named dir
    under ``shared/``, and top-level ``integration-tests``. A dir counts only
    if it (recursively) contains a ``test_*.py`` and sits on no excluded path
    (fixtures / vendored / worktrees).
    """
    found: set[str] = set()
    for d in root.glob("plugins/*/tests"):
        rel = d.relative_to(root)
        # Mirror ci.yml's plugin loop predicate (`[ -f pyproject.toml ]`): a
        # plugin without pyproject.toml is skipped by CI, so discovery must not
        # claim it covered. discovery == execution.
        if (d.is_dir() and not _excluded(rel) and _has_test_files(d)
                and (d.parent / "pyproject.toml").exists()):
            found.add(rel.as_posix())
    for d in root.glob("shared/**/tests"):
        rel = d.relative_to(root)
        if d.is_dir() and rel.name == "tests" and not _excluded(rel) and _has_test_files(d):
            found.add(rel.as_posix())
    integ = root / "integration-tests"
    if integ.is_dir() and _has_test_files(integ):
        found.add("integration-tests")
    return sorted(found)


def parse_workflows(root: Path) -> list[Step]:
    """Flatten every ``.github/workflows/*.yml`` into a list of Steps."""
    steps: list[Step] = []
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return steps
    for wf in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for st in job.get("steps") or []:
                if not isinstance(st, dict):
                    continue
                coe = st.get("continue-on-error")
                steps.append(Step(
                    workflow=wf.name,
                    job=str(job_name),
                    name=str(st.get("name") or st.get("id") or st.get("uses") or ""),
                    run=str(st.get("run") or ""),
                    uses=str(st.get("uses") or ""),
                    continue_on_error=(coe is True) or (
                        isinstance(coe, str) and coe.strip().lower() not in ("", "false")
                    ),
                ))
    return steps
