"""Tests for ``shared/scripts/tools/check_agent_doc_shape.py``.

Covers both modes: full-corpus (file-only, no git) and forward-only (git base
diff — the path the F11 verifier reuses), the no-git no-op, and the ``main()``
CLI surfaces (exit codes + messages).
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

from tools.check_agent_doc_shape import find_violations, main  # noqa: E402

_CANON = "- **iterate-2026-07-01-x** (2026-07-01): Component — a real thing. → decision_log (Run-ID)"
_NONCANON = "- **Campaign X** (2026-07-01): a thing. → decision_log (Run-ID)"


def _write_docs(project_root: Path, arch_updates: str = "") -> None:
    doc = project_root / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "architecture.md").write_text(
        f"# Architecture\n\n## Architecture Updates\n{arch_updates}", encoding="utf-8"
    )
    (doc / "conventions.md").write_text(
        "# Conventions\n\n## Convention Updates\n\n## Learnings\n", encoding="utf-8"
    )


# --- full-corpus mode (no git needed) ---------------------------------------


def test_full_corpus_flags_noncanonical(tmp_path: Path):
    _write_docs(tmp_path, arch_updates=f"{_NONCANON}\n")
    violations, base = find_violations(tmp_path, full_corpus=True)
    assert base is None
    assert any("Architecture Updates" in header for _f, header, _m in violations)


def test_full_corpus_clean_when_compliant(tmp_path: Path):
    _write_docs(tmp_path, arch_updates=f"{_CANON}\n")
    violations, _ = find_violations(tmp_path, full_corpus=True)
    assert violations == []


def test_full_corpus_exempts_precutoff(tmp_path: Path):
    _write_docs(
        tmp_path,
        arch_updates="- **Campaign X** (2026-05-01): legacy. → decision_log (Run-ID)\n",
    )
    violations, _ = find_violations(tmp_path, full_corpus=True)
    assert violations == []  # dated < enforced_from → grandfathered


# --- forward-only mode (git base) -------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _base_repo(tmp_path: Path, arch_updates: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _write_docs(repo, arch_updates=arch_updates)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_forward_only_flags_only_new_noncanonical(tmp_path: Path):
    repo = _base_repo(tmp_path, arch_updates="")  # clean base
    arch = repo / ".shipwright" / "agent_docs" / "architecture.md"
    arch.write_text(arch.read_text(encoding="utf-8") + f"{_NONCANON}\n", encoding="utf-8")
    violations, resolved = find_violations(repo)
    assert resolved is not None
    assert len(violations) == 1 and "Architecture Updates" in violations[0][1]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_forward_only_ignores_untouched_legacy_noncanonical(tmp_path: Path):
    repo = _base_repo(tmp_path, arch_updates=f"{_NONCANON}\n")  # legacy junk in base
    violations, _ = find_violations(repo)
    assert violations == []


def test_forward_only_no_git_is_noop(tmp_path: Path):
    _write_docs(tmp_path, arch_updates=f"{_NONCANON}\n")
    violations, base = find_violations(tmp_path)
    assert base is None and violations == []


# --- main() CLI surfaces -----------------------------------------------------


def test_cli_all_flags_and_exits_1(tmp_path: Path, monkeypatch, capsys):
    _write_docs(tmp_path, arch_updates=f"{_NONCANON}\n")
    monkeypatch.setattr(
        sys, "argv", ["check_agent_doc_shape.py", "--project-root", str(tmp_path), "--all"]
    )
    assert main() == 1
    assert "non-canonical" in capsys.readouterr().out


def test_cli_all_clean_exits_0(tmp_path: Path, monkeypatch, capsys):
    _write_docs(tmp_path, arch_updates=f"{_CANON}\n")
    monkeypatch.setattr(
        sys, "argv", ["check_agent_doc_shape.py", "--project-root", str(tmp_path), "--all"]
    )
    assert main() == 0
    assert "OK" in capsys.readouterr().out


def test_cli_no_git_base_skips(tmp_path: Path, monkeypatch, capsys):
    _write_docs(tmp_path, arch_updates=f"{_NONCANON}\n")
    monkeypatch.setattr(
        sys, "argv", ["check_agent_doc_shape.py", "--project-root", str(tmp_path)]
    )
    assert main() == 0
    assert "no git base resolvable" in capsys.readouterr().out


def test_cli_invalid_since_exits_2(tmp_path: Path, monkeypatch, capsys):
    _write_docs(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["check_agent_doc_shape.py", "--project-root", str(tmp_path), "--all", "--since", "nope"],
    )
    assert main() == 2
    assert "invalid --since" in capsys.readouterr().out
