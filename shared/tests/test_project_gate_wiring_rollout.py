"""Real-git, end-to-end tests proving the rollout-transition grace
(`trg-9583d3a8`) actually lands in the ``CheckResult`` the two wiring
functions return — ``check_criteria_free_of_implementation_detail`` (#5) and
``check_no_empty_split`` (#10) in ``_project_gate_wiring.py``. The unit-level
pieces (commit resolution, snapshot reading, grace comparators) are each
covered in their own file; this file is the one that proves they compose
correctly through the lazy-rollout-build wiring path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verifiers._project_gate_wiring import (  # noqa: E402
    check_criteria_free_of_implementation_detail,
    check_no_empty_split,
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit_at(root: Path, msg: str, iso_date: str, *, on_trunk: bool = True) -> str:
    """``on_trunk=True`` (the default) also advances a simulated
    ``origin/main`` to the new commit — standing in for "this content is
    already merged", the trust anchor `resolve_rollout_commit` now requires
    (`trg-4380c61a`)."""
    _git(root, "add", "-A")
    proc = subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", msg],
        capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git commit failed: {proc.stderr}")
    sha = _git(root, "rev-parse", "HEAD")
    if on_trunk:
        _git(root, "update-ref", "refs/remotes/origin/main", sha)
    return sha


_BEFORE_ROLLOUT = "2026-09-06T00:00:00+00:00"
_AFTER_ROLLOUT = "2026-09-13T00:00:00+00:00"

_MANIFEST = json.dumps({"splits": [{"name": "01-a", "status": "not_started"}]})

_SPEC_WITH_BAD_CRITERION = (
    "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
    "| FR-01.01 | widget export | Must | export widgets | interview |\n\n"
    "### FR-01.01\n"
    "- (E) Given the handler in export_service.py runs, then a file is written.\n"
)


def test_check_criteria_free_of_implementation_detail_grants_grace_for_pre_existing_content(tmp_path):
    _init(tmp_path)
    _write(tmp_path, "shipwright_project_config.json", _MANIFEST)
    _write(tmp_path, ".shipwright/planning/01-a/spec.md", _SPEC_WITH_BAD_CRITERION)
    _commit_at(tmp_path, "pre-rollout: legacy content with a bad criterion", _BEFORE_ROLLOUT)
    _write(tmp_path, "README.md", "unrelated touch")
    _commit_at(tmp_path, "post-rollout: unrelated change", _AFTER_ROLLOUT)

    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is False
    assert r.severity == "warning"
    assert r.strict_exempt is True
    assert "FR-01.01" in r.detail


def test_check_criteria_free_of_implementation_detail_hard_blocks_a_new_violation(tmp_path):
    """The same shape, but the violating criterion is introduced AFTER the
    gate's own rollout — no pre-existing content to grandfather, so it stays
    a hard, default-severity failure."""
    _init(tmp_path)
    _write(tmp_path, "shipwright_project_config.json", _MANIFEST)
    _write(
        tmp_path, ".shipwright/planning/01-a/spec.md",
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | interview |\n\n"
        "### FR-01.01\n"
        "- (E) Given a signed-in user, when they export, then a file "
        "download begins.\n",
    )
    _commit_at(tmp_path, "pre-rollout: clean spec", _BEFORE_ROLLOUT)
    _write(tmp_path, ".shipwright/planning/01-a/spec.md", _SPEC_WITH_BAD_CRITERION)
    _commit_at(tmp_path, "post-rollout: introduces a bad criterion", _AFTER_ROLLOUT)

    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is False
    assert r.severity == "error"
    assert r.strict_exempt is False
    assert "FR-01.01" in r.detail


def test_check_criteria_free_of_implementation_detail_still_fails_hard_in_a_greenfield_repo(tmp_path):
    """No git history at all predating the gate's rollout (an ordinary
    /shipwright-project run today) — build_rollout_snapshot cannot resolve a
    snapshot, so the check behaves exactly as it did before this iterate."""
    _init(tmp_path)
    _write(tmp_path, "shipwright_project_config.json", _MANIFEST)
    _write(tmp_path, ".shipwright/planning/01-a/spec.md", _SPEC_WITH_BAD_CRITERION)
    _commit_at(tmp_path, "only commit, well after rollout", _AFTER_ROLLOUT)

    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is False
    assert r.severity == "error"
    assert r.strict_exempt is False


def test_check_no_empty_split_grants_grace_for_a_split_declared_and_empty_before_rollout(tmp_path):
    _init(tmp_path)
    _write(tmp_path, "shipwright_project_config.json", _MANIFEST)
    _write(tmp_path, ".shipwright/planning/01-a/spec.md", "# spec\n\nNothing here yet.\n")
    _commit_at(tmp_path, "pre-rollout: declared, empty split", _BEFORE_ROLLOUT)
    _write(tmp_path, "README.md", "unrelated touch")
    _commit_at(tmp_path, "post-rollout: unrelated change", _AFTER_ROLLOUT)

    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert r.severity == "warning"
    assert r.strict_exempt is True
    assert "01-a" in r.detail


def test_check_no_empty_split_hard_blocks_a_split_newly_declared_after_rollout(tmp_path):
    _init(tmp_path)
    _write(tmp_path, "README.md", "nothing declared yet")
    _commit_at(tmp_path, "pre-rollout: no manifest at all", _BEFORE_ROLLOUT)
    _write(tmp_path, "shipwright_project_config.json", _MANIFEST)
    _write(tmp_path, ".shipwright/planning/01-a/spec.md", "# spec\n\nNothing here yet.\n")
    _commit_at(tmp_path, "post-rollout: new split declared, still empty", _AFTER_ROLLOUT)

    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert r.severity == "error"
    assert r.strict_exempt is False
    assert "01-a" in r.detail
