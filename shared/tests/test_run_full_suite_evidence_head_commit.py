"""``scripts/run_full_suite_evidence.py`` --head-commit resolution (Stage-2 review follow-up).

Split out of ``test_run_full_suite_evidence.py`` (300-LOC guideline) rather than
grown there. Pins the fix for a real bug: an unset ``--head-commit`` used to stage
evidence with ``head_commit=""``, which ``_layer_coverage_evidence.fresh_evidence``
hard-rejects — silently discarding a whole 20-60 minute full-suite pass's evidence
rather than failing loud. The default now resolves via a real ``git rev-parse HEAD``
in ``--project-root``; when that cannot resolve and no explicit flag was given, the
tool refuses to run rather than waste the pass on evidence the gate will discard.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBJECT = REPO_ROOT / "scripts" / "run_full_suite_evidence.py"


def _load_subject(name: str = "_full_suite_evidence_head_commit_probe"):
    spec = importlib.util.spec_from_file_location(name, _SUBJECT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # ADR-045: register BEFORE exec
    spec.loader.exec_module(module)
    return module


rfse = _load_subject()


def _git_init_with_one_commit(root: Path) -> str:
    """A real, throwaway git repo (never the live worktree — tmp_path only) so
    `git rev-parse HEAD` genuinely resolves. Returns the commit sha."""
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(root), check=True)
    (root / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(root), check=True)
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_head_commit_defaults_to_git_rev_parse_head_when_not_given(tmp_path):
    sha = _git_init_with_one_commit(tmp_path)
    (tmp_path / "conftest.py").write_text(
        "def discover_test_roots(repo_root):\n    return set()\n", encoding="utf-8",
    )
    rc = rfse.main(["--project-root", str(tmp_path), "--run-id", "iterate-x", "--skip-sync"])
    assert rc == 1  # zero roots is still a hard failure — this test is ONLY about head_commit
    prov_path = tmp_path / ".shipwright" / "compliance" / "evidence" / "_provenance.json"
    assert json.loads(prov_path.read_text(encoding="utf-8"))["head_commit"] == sha


def test_head_commit_refuses_to_run_when_unresolvable_and_unset(tmp_path):
    # A --project-root that is not a git repo and no explicit --head-commit: fail
    # loud rather than stage evidence the gate will silently discard wholesale.
    (tmp_path / "conftest.py").write_text(
        "def discover_test_roots(repo_root):\n    return set()\n", encoding="utf-8",
    )
    rc = rfse.main(["--project-root", str(tmp_path), "--run-id", "iterate-x", "--skip-sync"])
    assert rc == 1
    prov_path = tmp_path / ".shipwright" / "compliance" / "evidence" / "_provenance.json"
    assert not prov_path.is_file()  # refused before even attempting to stage


def test_explicit_head_commit_still_wins_over_the_default(tmp_path):
    _git_init_with_one_commit(tmp_path)  # a real HEAD exists but must NOT be used
    (tmp_path / "conftest.py").write_text(
        "def discover_test_roots(repo_root):\n    return set()\n", encoding="utf-8",
    )
    rc = rfse.main([
        "--project-root", str(tmp_path), "--run-id", "iterate-x", "--skip-sync",
        "--head-commit", "explicit-value",
    ])
    assert rc == 1  # zero roots — unrelated to head_commit
    prov_path = tmp_path / ".shipwright" / "compliance" / "evidence" / "_provenance.json"
    assert json.loads(prov_path.read_text(encoding="utf-8"))["head_commit"] == "explicit-value"


if __name__ == "__main__":
    import pytest  # noqa: PLC0415

    sys.exit(pytest.main([__file__, "-q"]))
