"""Tests for ``shared/scripts/tools/check_agent_doc_budget.py``.

Covers both modes: full-corpus (file-only, no git) and forward-only (git base
diff — the path the F11 verifier reuses), plus the no-git no-op behaviour.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
for _p in (str(_SHARED_SCRIPTS), str(_SHARED_SCRIPTS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.agent_doc_budget import CLAUDE_MD_MAX_NEW_LINES, ENTRY_MAX_CHARS  # noqa: E402
from tools.check_agent_doc_budget import find_violations, main, resolve_base  # noqa: E402
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

_GIT_HINT = "git not on PATH — CI provisions it via actions/checkout"
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


def test_forward_only_flags_only_new_oversize(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
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


def test_forward_only_ignores_untouched_legacy_oversize(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
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


# --- CLAUDE.md net-growth gate (forward-only) --------------------------------


def _growth_repo(tmp_path: Path, base_lines: int) -> Path:
    """A git repo with compliant agent docs and a committed CLAUDE.md."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _write_docs(repo, "- (2026-06-01) iterate — base rule. → run_id")
    (repo / "CLAUDE.md").write_text(
        "".join(f"line {i}\n" for i in range(base_lines)), encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _grow_claude_md(repo: Path, extra_lines: int) -> None:
    p = repo / "CLAUDE.md"
    p.write_text(
        p.read_text(encoding="utf-8")
        + "".join(f"extra {i}\n" for i in range(extra_lines)),
        encoding="utf-8",
    )


def test_claude_md_growth_over_cap_flagged(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    repo = _growth_repo(tmp_path, base_lines=10)
    _grow_claude_md(repo, CLAUDE_MD_MAX_NEW_LINES + 1)
    violations, base = find_violations(repo)
    assert base is not None
    assert len(violations) == 1 and violations[0][0] == "CLAUDE.md"


def test_claude_md_growth_within_cap_clean(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    repo = _growth_repo(tmp_path, base_lines=10)
    _grow_claude_md(repo, CLAUDE_MD_MAX_NEW_LINES)
    violations, _ = find_violations(repo)
    assert violations == []


def test_claude_md_new_file_at_worktree_skipped(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    # CLAUDE.md absent at base (first-time creation) → creation is not
    # accretion → growth check skipped even when the new file is large.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _write_docs(repo, "- (2026-06-01) iterate — base rule. → run_id")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "CLAUDE.md").write_text(
        "".join(f"line {i}\n" for i in range(CLAUDE_MD_MAX_NEW_LINES * 3)),
        encoding="utf-8",
    )
    violations, _ = find_violations(repo)
    assert violations == []


def test_claude_md_deleted_in_worktree_skipped(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    repo = _growth_repo(tmp_path, base_lines=10)
    (repo / "CLAUDE.md").unlink()
    violations, _ = find_violations(repo)
    assert violations == []


def test_claude_md_replaced_by_directory_skipped(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    # A non-regular-file CLAUDE.md (odd repo state) must skip, never crash.
    repo = _growth_repo(tmp_path, base_lines=10)
    (repo / "CLAUDE.md").unlink()
    (repo / "CLAUDE.md").mkdir()
    violations, _ = find_violations(repo)
    assert violations == []


def test_claude_md_growth_opt_out_param(tmp_path: Path):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    # check_claude_md=False (the env-override path in CLI/verifier) skips ONLY
    # the growth rule — entry budgets still enforced.
    repo = _growth_repo(tmp_path, base_lines=10)
    _grow_claude_md(repo, CLAUDE_MD_MAX_NEW_LINES + 20)
    conv = repo / ".shipwright" / "agent_docs" / "conventions.md"
    conv.write_text(
        conv.read_text(encoding="utf-8").replace(
            "\n## Convention Updates",
            f"- (2026-06-13) iterate — {_BIG}\n\n## Convention Updates",
        ),
        encoding="utf-8",
    )
    violations, _ = find_violations(repo, check_claude_md=False)
    assert len(violations) == 1 and "Learnings" in violations[0][1]


def test_full_corpus_mode_never_checks_claude_md_growth(tmp_path: Path):
    # --all is file-only (no git base) — growth is a diff concept and must
    # not be evaluated there.
    _write_docs(tmp_path, "- (2026-06-13) iterate — fine. → run_id")
    (tmp_path / "CLAUDE.md").write_text(
        "".join(f"line {i}\n" for i in range(CLAUDE_MD_MAX_NEW_LINES * 3)),
        encoding="utf-8",
    )
    violations, base = find_violations(tmp_path, full_corpus=True)
    assert base is None and violations == []


# --- main() stdout surfaces (the AC-called-out CLI notes) ---------------------


def test_cli_all_mode_prints_growth_not_evaluated_note(tmp_path: Path, monkeypatch, capsys):
    _write_docs(tmp_path, "- (2026-06-13) iterate — fine. → run_id")
    monkeypatch.delenv("SHIPWRIGHT_CLAUDE_MD_GROWTH_OK", raising=False)
    monkeypatch.setattr(
        sys, "argv",
        ["check_agent_doc_budget.py", "--project-root", str(tmp_path), "--all"],
    )
    assert main() == 0
    out = capsys.readouterr().out
    assert "not evaluated in --all mode" in out


def test_cli_env_override_prints_skip_note(tmp_path: Path, monkeypatch, capsys):
    _write_docs(tmp_path, "- (2026-06-13) iterate — fine. → run_id")
    monkeypatch.setenv("SHIPWRIGHT_CLAUDE_MD_GROWTH_OK", "1")
    monkeypatch.setattr(
        sys, "argv",
        ["check_agent_doc_budget.py", "--project-root", str(tmp_path)],
    )
    assert main() == 0
    out = capsys.readouterr().out
    assert "CLAUDE.md growth check skipped (SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1)" in out
