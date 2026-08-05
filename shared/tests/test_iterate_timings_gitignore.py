"""The iterate-timings sidecar's FileLock companion must stay gitignored too.

Regression pin for a spec-reviewer finding: adding FileLock (concurrent-writer
safety) introduced a `<run_id>.iterate_timings.jsonl.lock` sibling file that
the original gitignore pattern (matching only the `.jsonl` itself) missed —
the lock file was tracked and committed by mistake in the first pass.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _has_pattern(path: Path, pattern: str) -> bool:
    return pattern in path.read_text(encoding="utf-8")


def test_gitignore_covers_the_filelock_sidecar():
    pattern = "/.shipwright/agent_docs/iterates/*.iterate_timings.jsonl.lock"
    assert _has_pattern(_REPO_ROOT / ".gitignore", pattern)
    assert _has_pattern(_REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template", pattern)
