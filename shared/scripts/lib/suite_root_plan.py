"""Pytest-root invocation planning — the ONE derivation of "which base does this
test root rebase JUnit ids onto" (iterate-2026-08-26-r1b-ci-manifest-regen-gate,
AC2/AC4).

Extracted from `scripts/run_full_suite_evidence.py` (R1a) so a second consumer —
F0's suite runner (`run_test_suite.py`, local retention) and ci.yml's end-of-job
manifest-drift step (AC4) — can share the exact same rule instead of each
re-deriving it. Both AC2 and AC4 depend on this staying ONE function: if F0's
retained side-manifest and CI's "did every root get staged" assertion ever
computed `base` differently, a real root could silently vanish from one side's
view while looking present on the other's.

Pure planning only — no subprocess, no filesystem I/O beyond `Path.relative_to`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RootPlan:
    root: Path          # absolute path to the discovered `tests/` dir
    rel_root: str        # repo-root-relative posix path to that `tests/` dir (for display)
    cwd: Path              # absolute cwd the pytest process runs in
    pytest_arg: str         # the path argument passed to pytest, relative to `cwd`
    base: str                # id-rebase base (repo-root-relative posix, "" = no rebase)
    marker_expr: str | None   # -m expression, or None (rely on the root's own addopts)
    junit_out: Path            # absolute path this root's --junitxml is written to


def base_for_root(repo_root: Path, root: Path) -> str:
    """The id-rebase base for one test root: its plugin dir if it is a
    `plugins/<name>/tests` root, else `""` (already project-root-relative).

    The one piece of `plan_root()` a caller needs when it only cares about
    JUnit id-rebasing, not the pytest invocation itself (F0's retention side-
    manifest is exactly this case — it never re-runs pytest, so `junit_out`/
    `pytest_arg`/`marker_expr` would all be unused noise).
    """
    plugins_dir = repo_root / "plugins"
    try:
        under_plugins = root.relative_to(plugins_dir)
    except ValueError:
        return ""
    plugin_dir = plugins_dir / under_plugins.parts[0]
    return plugin_dir.relative_to(repo_root).as_posix()


def plan_root(repo_root: Path, root: Path, raw_dir: Path, index: int) -> RootPlan:
    """Derive one root's invocation plan structurally from its OWN path — no
    hand-maintained per-root table. ``index`` only picks the junit filename."""
    rel_root = root.relative_to(repo_root).as_posix()
    junit_out = raw_dir / f"{index:02d}-{rel_root.replace('/', '_')}.xml"
    base = base_for_root(repo_root, root)

    if base:
        plugin_dir = repo_root / base
        return RootPlan(
            root=root, rel_root=rel_root, cwd=plugin_dir,
            pytest_arg=root.relative_to(plugin_dir).as_posix(),
            base=base, marker_expr=None, junit_out=junit_out,
        )

    marker_expr = None
    try:
        root.relative_to(repo_root / "shared")
        marker_expr = "not slow and not cross_plugin"
    except ValueError:
        pass
    return RootPlan(
        root=root, rel_root=rel_root, cwd=repo_root,
        pytest_arg=rel_root, base="", marker_expr=marker_expr, junit_out=junit_out,
    )


def plan_all_roots(repo_root: Path, roots, raw_dir: Path) -> list[RootPlan]:
    """Deterministic order (sorted by repo-relative path) so console output and the
    staged junit numbering are stable across runs — an unordered ``set`` otherwise
    makes every invocation's report/base pairing arbitrary."""
    ordered = sorted(roots, key=lambda p: p.relative_to(repo_root).as_posix())
    return [plan_root(repo_root, root, raw_dir, i) for i, root in enumerate(ordered, start=1)]
