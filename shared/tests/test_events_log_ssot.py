"""SSoT drift-protection for shipwright_events.jsonl path resolution.

``shared/scripts/lib/events_log.py::resolve_events_path`` is the single
source of truth for *locating* the event log. The log is repo-scoped, so
any code that may run from inside a ``/shipwright-iterate`` worktree MUST
resolve it via that helper — a literal ``project_root /
"shipwright_events.jsonl"`` reads/writes a throwaway worktree copy.

This meta-test pins the invariant in both directions (mirrors the
"Registry-driven SSoT meta-test rule" in shipwright-iterate SKILL.md):

- Forward: every file reached during iterate finalization from inside a
  worktree uses ``resolve_events_path``.
- Coverage: every raw event-log path-join in ``shared/scripts`` is either
  the resolver itself, a helper consumer, or an allowlisted main-repo-only
  site (each with a documented reason).
- Reverse: every allowlist entry still exists and still has a raw join —
  a migrated file must be dropped from the allowlist, not left to rot.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.events_log import resolve_events_path  # noqa: F401  (import == helper exists)

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# Files reached during iterate finalization (F5b dashboard, F7 record_event,
# F11 verifier) from INSIDE a worktree — MUST resolve the log via the helper.
_WORKTREE_REACHABLE = {
    "tools/record_event.py",
    "tools/verifiers/iterate_checks.py",
    "lib/config.py",
}

# The resolver itself — its fallback legitimately constructs the raw path.
_RESOLVER = "lib/events_log.py"

# Files that build a raw event-log path but run ONLY in main-repo phases,
# where ``project_root`` is always the main repo so the raw join is correct.
# Each entry carries the reason it does not need the worktree-aware helper.
# If one of these is ever invoked from a worktree, move it to the helper.
_MAIN_REPO_ONLY = {
    "tools/convert_configs_to_events.py":
        "one-time config->events migration tool; never run from an iterate worktree",
    "tools/validate_event_log.py":
        "manual event-log health-check CLI; run against the main repo",
    "tools/verifiers/common.py":
        "generic verifier helper for build/adopt phase verifiers (main-repo phases)",
    "tools/verifiers/adopt_compliance.py":
        "/shipwright-adopt A7 verifier; adopt executes in the main repo",
    "lib/phase_quality.py":
        "Phase-Quality Stop hook; runs with cwd = main project root",
}

# A path-join onto the event log: `<expr> / EVENT_FILE` or
# `<expr> / "shipwright_events.jsonl"` (single or double quoted).
_JOIN_RE = re.compile(r"""/\s*\(?(?:EVENT_FILE\b|["']shipwright_events\.jsonl["'])""")


def _prod_py_files():
    """All production .py under shared/scripts (test files excluded)."""
    for p in sorted(_SHARED_SCRIPTS.rglob("*.py")):
        rel = p.relative_to(_SHARED_SCRIPTS).as_posix()
        if "/tests/" in f"/{rel}" or p.name.startswith("test_"):
            continue
        yield p, rel


def _has_raw_join(path: Path) -> bool:
    """True if the file builds a raw event-log path (ignoring # comments)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        if _JOIN_RE.search(line):
            return True
    return False


def test_worktree_reachable_files_use_the_resolver():
    """Forward: the files reached from inside a worktree resolve via the helper."""
    for rel in sorted(_WORKTREE_REACHABLE):
        path = _SHARED_SCRIPTS / rel
        assert path.exists(), f"_WORKTREE_REACHABLE entry {rel} no longer exists"
        src = path.read_text(encoding="utf-8")
        assert "resolve_events_path" in src, (
            f"{rel} is reached from inside an iterate worktree but does not "
            "use events_log.resolve_events_path — it would read/write a "
            "throwaway worktree copy of shipwright_events.jsonl."
        )


def test_no_unaccounted_raw_event_log_joins():
    """Coverage: every raw event-log join in shared/scripts is the resolver,
    a helper consumer, or an allowlisted main-repo-only site."""
    violations = []
    for path, rel in _prod_py_files():
        if rel == _RESOLVER:
            continue
        if not _has_raw_join(path):
            continue
        if "resolve_events_path" in path.read_text(encoding="utf-8"):
            continue  # helper consumer — raw join already migrated away
        if rel in _MAIN_REPO_ONLY:
            continue  # allowlisted; reason documented in _MAIN_REPO_ONLY
        violations.append(rel)
    assert not violations, (
        "Raw `project_root / shipwright_events.jsonl` join(s) in files that "
        "are neither helper consumers nor allowlisted main-repo-only sites: "
        f"{violations}. Resolve the log via events_log.resolve_events_path, "
        "or — if the file only ever runs in a main-repo phase — add it to "
        "_MAIN_REPO_ONLY with a reason."
    )


def test_allowlist_entries_are_not_stale():
    """Reverse: every _MAIN_REPO_ONLY entry still exists and still has a raw
    join — a file migrated to the helper must be dropped from the allowlist."""
    for rel in sorted(_MAIN_REPO_ONLY):
        path = _SHARED_SCRIPTS / rel
        assert path.exists(), (
            f"_MAIN_REPO_ONLY entry {rel} no longer exists — drop it."
        )
        assert _has_raw_join(path), (
            f"_MAIN_REPO_ONLY entry {rel} no longer builds a raw event-log "
            "path — it was migrated; drop it from the allowlist."
        )
