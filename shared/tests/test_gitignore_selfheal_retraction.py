"""`self_heal_gitignore`'s SUPERSEDED (retraction) commit-path.

Sibling of ``test_gitignore_selfheal.py`` (split out to stay under the
300-line guideline, mirroring the ``test_gitignore_canon_retraction.py`` /
``test_gitignore_canon_merge.py`` split). Covers doubt-reviewer HIGH #1
(iterate-2026-08-08-track-decision-drops) end-to-end through the real commit
path, in both shapes a retracted rule can occupy on a target's ``.gitignore``:
inside the managed block (every prior scaffold/self-heal commit produces
this) and outside it (a rule scaffolded before the managed-block marker
convention existed on that project — shipwright-webui's actual, verified
2026-08-15 shape, and the one the original retraction fix's own test suite
never covered).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

import _reconcile_helpers as h  # noqa: E402  (git() + set_identity + head_count)
from lib import gitignore_selfheal as gs  # noqa: E402
from lib.churn_merge import EVENTS_LOG  # noqa: E402
from lib.gitignore_canon import BEGIN_MARKER, END_MARKER, read_canonical_rules  # noqa: E402

_STALE_RULE = "/.shipwright/agent_docs/decision-drops/"
_NARROW_REPLACEMENTS = {
    "/.shipwright/agent_docs/decision-drops/INDEX.md",
    "/.shipwright/agent_docs/decision-drops/*.tmp",
}


def _seed_managed_repo(work: Path, *, gitignore: str | None = None) -> None:
    """Track an events.jsonl (the managed-repo marker) + set commit identity."""
    h.set_identity(work)
    (work / EVENTS_LOG).write_text('{"type":"adopted"}\n', encoding="utf-8")
    if gitignore is not None:
        (work / ".gitignore").write_text(gitignore, encoding="utf-8")
    h.git(work, "add", "-A")
    h.git(work, "commit", "-m", "seed managed repo")


def _check_ignored(repo: Path, rel: str) -> bool:
    proc = h.git(repo, "check-ignore", rel, check=False)
    assert proc.returncode in (0, 1), f"check-ignore rc={proc.returncode} {proc.stderr!r}"
    return proc.returncode == 0


def test_self_heal_retracts_superseded_decision_drops_rule(git_origin_repo):
    """Already-adopted-before-2026-08-08 repo: still carries the OLD blanket
    decision-drops ignore, wrapped inside the managed block by a prior
    scaffold/self-heal commit — add-only self-heal can never undo this, so
    the directory stays ignored forever and every future iterate ADR is
    silently lost. The next iterate must both retract the stale rule AND add
    its replacements — in one commit, automatically, no operator action."""
    work, _ = git_origin_repo
    canonical = read_canonical_rules()
    pre_existing = [r for r in canonical if r not in _NARROW_REPLACEMENTS] + [_STALE_RULE]
    gitignore = "\n".join([BEGIN_MARKER, *pre_existing, END_MARKER]) + "\n"
    _seed_managed_repo(work, gitignore=gitignore)

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "committed", res
    assert res.retracted == [_STALE_RULE], res
    assert set(res.added) == _NARROW_REPLACEMENTS, res
    assert "superseded" in h.git(work, "log", "-1", "--format=%s").stdout

    gi = (work / ".gitignore").read_text(encoding="utf-8")
    assert _STALE_RULE not in gi.splitlines()

    # Empirical: a decision-drop JSON is now trackable; INDEX.md/*.tmp stay local.
    dd = work / ".shipwright" / "agent_docs" / "decision-drops"
    dd.mkdir(parents=True)
    (dd / "iterate-x_001.json").write_text("{}", encoding="utf-8")
    (dd / "INDEX.md").write_text("x", encoding="utf-8")
    assert not _check_ignored(work, ".shipwright/agent_docs/decision-drops/iterate-x_001.json")
    assert _check_ignored(work, ".shipwright/agent_docs/decision-drops/INDEX.md")


def test_self_heal_retracts_a_pre_marker_era_stale_rule_outside_the_block(
    git_origin_repo,
):
    """shipwright-webui's actual shape (verified 2026-08-15, live repo): the
    stale decision-drops rule was scaffolded by `/shipwright-adopt` on
    2026-05-20, weeks before that project's managed block first existed
    (2026-06-07) — so it sits as its own line, UNWRAPPED, ahead of the block,
    not inside it. The test above only covers the inside-block shape, which
    every prior scaffold commit produces but which this real project never
    actually had — the retraction never fired on it despite running on
    every iterate since 2026-08-08."""
    work, _ = git_origin_repo
    managed = [r for r in read_canonical_rules() if r not in _NARROW_REPLACEMENTS]
    gitignore = (
        f"# scaffolded by /shipwright-adopt before markers existed\n"
        f"{_STALE_RULE}\n\n"
        + "\n".join([BEGIN_MARKER, *managed, END_MARKER])
        + "\n"
    )
    _seed_managed_repo(work, gitignore=gitignore)

    res = gs.self_heal_gitignore(work, allow_ci=True)

    assert res.status == "committed", res
    assert res.retracted == [_STALE_RULE], res
    assert set(res.added) == _NARROW_REPLACEMENTS, res

    gi = (work / ".gitignore").read_text(encoding="utf-8")
    assert _STALE_RULE not in gi.splitlines()

    dd = work / ".shipwright" / "agent_docs" / "decision-drops"
    dd.mkdir(parents=True)
    (dd / "iterate-x_001.json").write_text("{}", encoding="utf-8")
    (dd / "INDEX.md").write_text("x", encoding="utf-8")
    assert not _check_ignored(work, ".shipwright/agent_docs/decision-drops/iterate-x_001.json")
    assert _check_ignored(work, ".shipwright/agent_docs/decision-drops/INDEX.md")
