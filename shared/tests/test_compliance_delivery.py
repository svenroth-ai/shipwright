"""The on-demand documents-only pull request, end to end.

Subject: ``shared/scripts/tools/compliance_delivery.py``
(iterate-2026-07-31-derived-docs-at-release, AC-8 / AC-8b).

The claim under test is **"nothing else can ride along"**, and it is tested by
planting something else and proving it did not. Split from
``test_refresh_compliance_docs.py`` when the PR protocol moved into its own
module — it has its own preconditions, its own failure states and its own cleanup
obligation, and those are what this file covers.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Unconditional, and in this order: `shared/tests` carries its own `tools/`
# package and must never sit ahead of `shared/scripts` (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import (  # noqa: E402
    DASHBOARD, git, head_sha, seed_repo,
)
from lib.compliance_refresh import branch_name  # noqa: E402
from tools import compliance_delivery as docs  # noqa: E402
from tools import compliance_refresh_produce as produce_mod  # noqa: E402


@pytest.fixture
def compliance_refresh_repo(tmp_path: Path) -> Path:
    """:func:`seed_repo` as a fixture — see that module for why it is declared
    here rather than shared."""
    return seed_repo(tmp_path / "repo")

@pytest.fixture
def cloned(compliance_refresh_repo: Path, tmp_path: Path) -> Path:
    """The seeded repo with a bare ``origin`` it is up to date with — the state
    ``--pr`` requires before it will do anything."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    git(compliance_refresh_repo, "remote", "add", "origin", str(origin))
    git(compliance_refresh_repo, "push", "-u", "origin", "main")
    git(compliance_refresh_repo, "remote", "set-head", "origin", "main")
    return compliance_refresh_repo


def _committed_paths(root: Path, ref: str = "HEAD") -> set[str]:
    out = git(root, "show", "--name-only", "--pretty=format:", ref).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


# --- AC-8: the on-demand path ------------------------------------------------


def test_the_docs_pr_commit_carries_only_the_seven(cloned, monkeypatch):
    """AC-8. Take-the-set: the producers legitimately write the triage log and the
    compliance config too. None of it may reach the commit."""
    base = head_sha(cloned)
    (cloned / ".shipwright" / "triage.jsonl").write_text('{"x":1}\n', encoding="utf-8")
    (cloned / "stray.txt").write_text("nope\n", encoding="utf-8")
    payload = dict(produce_mod.capture(cloned))
    payload[DASHBOARD] = b"# dashboard\n\n" + b"row\n" * 60

    monkeypatch.setattr(docs, "_gh_pr_create",
                        lambda *a, **k: (0, "https://example.invalid/pr/1"))
    result = docs.deliver_pr(
        cloned,
        {"status": "ok", "base": base, "default_branch": "main",
         "ci_security": {"note": "fresh"}},
        payload,
    )
    assert result["status"] == "pr_opened"
    committed = _committed_paths(cloned, branch_name(base))
    assert committed == {DASHBOARD}
    assert "stray.txt" not in committed
    assert ".shipwright/triage.jsonl" not in committed


def test_the_docs_pr_returns_to_the_branch_it_started_on(cloned, monkeypatch):
    monkeypatch.setattr(docs, "_gh_pr_create",
                        lambda *a, **k: (0, "https://example.invalid/pr/1"))
    payload = dict(produce_mod.capture(cloned))
    payload[DASHBOARD] = b"# dashboard\n\n" + b"row\n" * 60
    docs.deliver_pr(cloned, {"status": "ok", "base": head_sha(cloned),
                             "default_branch": "main",
                             "ci_security": {"note": "fresh"}}, payload)
    assert git(cloned, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"


def test_an_unchanged_refresh_is_a_noop_not_an_empty_pr(cloned):
    result = docs.deliver_pr(
        cloned,
        {"status": "ok", "base": head_sha(cloned), "default_branch": "main",
         "ci_security": {"note": "fresh"}},
        produce_mod.capture(cloned),
    )
    assert result["status"] == "noop"


def test_a_base_that_moved_aborts_before_pushing_and_says_where_the_work_is(
    cloned, monkeypatch,
):
    """AC-8b. Recomputing is cheap; shipping a knowingly-stale refresh is not."""
    base = head_sha(cloned)
    payload = dict(produce_mod.capture(cloned))
    payload[DASHBOARD] = b"# dashboard\n\n" + b"row\n" * 60
    monkeypatch.setattr(docs, "_remote_tip", lambda root, branch: "f" * 40)
    result = docs.deliver_pr(
        cloned,
        {"status": "ok", "base": base, "default_branch": "main",
         "ci_security": {"note": "fresh"}},
        payload,
    )
    assert result["status"] == "base_moved"
    assert branch_name(base) in result["detail"]
    # The branch still exists locally: the work is kept, not discarded.
    assert git(cloned, "rev-parse", "--verify", branch_name(base)).stdout.strip()


# --- preflight ---------------------------------------------------------------


def test_a_dirty_tree_refuses_rather_than_repairing(cloned):
    (cloned / DASHBOARD).write_text("# local edit\n", encoding="utf-8")
    refusal = docs.preflight_pr(cloned, {})
    assert refusal and "uncommitted changes" in refusal


def test_being_behind_the_default_branch_refuses(cloned):
    (cloned / "extra.txt").write_text("x\n", encoding="utf-8")
    git(cloned, "add", "-A")
    git(cloned, "commit", "-m", "local only")
    refusal = docs.preflight_pr(cloned, {})
    assert refusal and "not origin/main" in refusal


def test_a_clean_up_to_date_checkout_passes_preflight(cloned):
    result: dict = {}
    assert docs.preflight_pr(cloned, result) is None
    assert result["default_branch"] == "main"
