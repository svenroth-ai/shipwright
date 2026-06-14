"""Tests for ``shared/scripts/tools/check_agent_doc_budget.py``.

Covers both modes: full-corpus (file-only, no git) and forward-only (git base
diff — the path the F11 verifier reuses), plus the no-git no-op behaviour.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
for _p in (str(_SHARED_SCRIPTS), str(_SHARED_SCRIPTS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.agent_doc_budget import ENTRY_MAX_CHARS  # noqa: E402
from tools.check_agent_doc_budget import find_violations, resolve_base  # noqa: E402

_BIG = "y" * (ENTRY_MAX_CHARS + 50)


def _write_docs(project_root: Path, learnings_body: str) -> None:
    doc = project_root / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "architecture.md").write_text(
        "# Architecture\n\n## Architecture Updates\n\n- **a** (2026-06-13): short\n",
        encoding="utf-8",
    )
    (doc / "conventions.md").write_text(
        f"# Conventions\n\n## Learnings\n\n{learnings_body}\n\n## Convention Updates\n",
        encoding="utf-8",
    )


# --- full-corpus mode (no git needed) ---------------------------------------


def test_full_corpus_flags_oversize_dated_entry(tmp_path: Path):
    _write_docs(tmp_path, f"- (2026-06-13) iterate — {_BIG}")
    violations, base = find_violations(tmp_path, full_corpus=True)
    assert base is None
    assert any("Learnings" in header for _f, header, _m in violations)


def test_full_corpus_clean_when_compliant(tmp_path: Path):
    _write_docs(tmp_path, "- (2026-06-13) iterate — a tidy one-line rule. → run_id")
    violations, _ = find_violations(tmp_path, full_corpus=True)
    assert violations == []


def test_full_corpus_exempts_undated(tmp_path: Path):
    _write_docs(tmp_path, f"- a legacy rule with no parenthesised date {_BIG}")
    violations, _ = find_violations(tmp_path, full_corpus=True)
    assert violations == []


# --- forward-only mode (git base) -------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_forward_only_flags_only_new_oversize(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    # Base commit: a compliant Learnings entry.
    _write_docs(repo, "- (2026-06-01) iterate — base rule. → run_id")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = resolve_base(repo)  # resolves against 'main'/'master'
    assert base is not None
    # Working-tree change: add a NEW oversize entry INTO the Learnings section.
    conv = repo / ".shipwright" / "agent_docs" / "conventions.md"
    text = conv.read_text(encoding="utf-8")
    conv.write_text(
        text.replace(
            "\n## Convention Updates",
            f"- (2026-06-13) iterate — {_BIG}\n\n## Convention Updates",
        ),
        encoding="utf-8",
    )
    violations, resolved = find_violations(repo)
    assert resolved == base
    assert len(violations) == 1 and "Learnings" in violations[0][1]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_forward_only_ignores_untouched_legacy_oversize(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    # Base already contains an oversize entry (legacy junk).
    _write_docs(repo, f"- (2026-06-01) iterate — {_BIG}")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    # No working-tree change → the legacy oversize entry must NOT block.
    violations, _ = find_violations(repo)
    assert violations == []


def test_forward_only_no_git_is_noop(tmp_path: Path):
    # A non-git directory → no base → no violations (skipped).
    _write_docs(tmp_path, f"- (2026-06-13) iterate — {_BIG}")
    violations, base = find_violations(tmp_path)
    assert base is None and violations == []
