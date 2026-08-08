"""INTEGRATION — the decision-log index refreshes through a REAL git merge.

Mirrors ``test_adr_index_churn_integration.py``'s intent but not its exact
shape: ``decision_log.md`` is real authored content (never in
``CHURN_ALLOWLIST``), so two branches both appending to it would produce a
genuine conflict on the LOG ITSELF — correct, existing behaviour, and not
what this test is proving. Instead this proves the wiring this change adds:
``integrate_regenerate.regenerate_after_merge`` refreshes and stages
``decision_log_index.md`` after ANY real merge commit (conflicted or not —
``integrate_merge.py`` calls it unconditionally once a merge lands), through
the REAL ``integrate_main.integrate``, not just a unit test of
``_refresh_and_stage_index`` in isolation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402

from lib import gitattributes_union as gu  # noqa: E402
from lib.churn_merge import CHURN_ALLOWLIST, DECISION_LOG_INDEX, classify  # noqa: E402
from lib.decision_log_index import (  # noqa: E402
    DECISION_LOG_INDEX_FILENAME,
    DECISION_LOG_PATH,
    rebuild_decision_log_index,
)
from tools import integrate_main  # noqa: E402

_INDEX = str(Path(DECISION_LOG_PATH).parent.as_posix()) + f"/{DECISION_LOG_INDEX_FILENAME}"


def _add_decision(root: Path, num: str, title: str) -> None:
    """Append a decision and refresh the index, as the direct append path
    (write_decision_log.py) does."""
    log = root / DECISION_LOG_PATH
    log.parent.mkdir(parents=True, exist_ok=True)
    existing = log.read_text(encoding="utf-8") if log.exists() else "# Decision Log\n\n"
    log.write_text(existing + f"\n### ADR-{num}: {title}\n", encoding="utf-8")
    rebuild_decision_log_index(root)


def _show_utf8(repo: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "show", ref], cwd=str(repo),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_the_index_is_registered_as_resolvable_churn():
    assert DECISION_LOG_INDEX in CHURN_ALLOWLIST
    resolvable, blocking = classify([DECISION_LOG_INDEX])
    assert resolvable == [DECISION_LOG_INDEX] and blocking == []


def test_index_refreshes_and_ships_through_a_real_diverged_merge(
    git_origin_repo, make_worktree, monkeypatch,
):
    """No conflict on either path (mainline touches an unrelated file), but
    history diverged enough that `integrate` produces a real merge commit —
    the exact condition under which `regenerate_after_merge` runs."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "decision-log-index-churn-integration")

    _add_decision(work, "100", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed: baseline decision + index")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "dli-branch")
    _add_decision(wt, "101", "Branch decision")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: ADR-101")

    _write(work, "unrelated.txt", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "chore: unrelated")
    _git(work, "push", "origin", "main")

    result = integrate_main.integrate(
        wt, run_id="iterate-2026-08-07-decision-log-index", reason="diverged merge",
    )
    assert result.get("status") == "ok", result
    assert "decision-log-index-refreshed" in (result.get("steps") or []), result

    merge_sha = _git(wt, "rev-list", "--merges", "-1", "HEAD").stdout.strip()
    assert merge_sha, f"no merge commit was created: {result}"
    committed = _show_utf8(wt, f"HEAD:{_INDEX}")
    assert "ADR-100" in committed
    assert "ADR-101" in committed
    assert committed == (wt / _INDEX).read_text(encoding="utf-8")
    assert "<<<<<<<" not in committed


def test_a_deleted_decision_log_does_not_falsely_report_a_refresh(
    git_origin_repo, make_worktree, monkeypatch,
):
    """A source that no longer exists post-merge (decision_log.md deleted) is
    a no-op for `refresh()` (returns None, same shape as a successful
    no-warning refresh). Without a guard, `_refresh_and_stage_index` would
    still append the `-refreshed` step token even though nothing was read or
    written, falsely claiming the stale committed index was brought current."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "decision-log-index-deleted-source")
    _add_decision(work, "100", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "dli-deleted")
    (wt / DECISION_LOG_PATH).unlink()
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "chore: remove decision log")

    _write(work, "unrelated.txt", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "chore: unrelated")
    _git(work, "push", "origin", "main")

    result = integrate_main.integrate(
        wt, run_id="iterate-2026-08-07-decision-log-index-deleted", reason="deleted source",
    )
    steps = result.get("steps") or []
    assert "decision-log-index-refreshed" not in steps, result


def test_an_uncommitted_decision_log_skips_the_refresh_instead_of_staging_it(
    git_origin_repo, make_worktree, monkeypatch,
):
    """regenerate_after_merge reads the WORKING TREE. If decision_log.md has
    local uncommitted changes at merge time (e.g. write_decision_log.py ran
    but the caller has not committed yet), refreshing from it and staging the
    result would enshrine an index describing content no commit actually
    contains. It must skip, not stage."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "decision-log-index-dirty-source")
    _add_decision(work, "100", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "dli-dirty")
    # Uncommitted local edit to decision_log.md — never staged, never committed.
    log = wt / DECISION_LOG_PATH
    log.write_text(log.read_text(encoding="utf-8") + "\n### ADR-999: Uncommitted\n", encoding="utf-8")

    _write(work, "unrelated.txt", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "chore: unrelated")
    _git(work, "push", "origin", "main")

    result = integrate_main.integrate(
        wt, run_id="iterate-2026-08-07-decision-log-index-dirty", reason="dirty source",
    )
    steps = result.get("steps") or []
    assert "decision-log-index-source-dirty-skipped" in steps, result
    assert "decision-log-index-refreshed" not in steps
    committed = _show_utf8(wt, f"HEAD:{_INDEX}")
    assert "ADR-999" not in committed


def test_a_failed_index_refresh_is_reported_not_swallowed(
    git_origin_repo, make_worktree, monkeypatch,
):
    """Mirrors the ADR index's own failure-path test: a failed refresh must
    reach the caller's result, not only stderr."""
    from tools import integrate_regenerate

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "decision-log-index-churn-failpath")
    _add_decision(work, "100", "Baseline decision")
    _write(work, ".gitattributes", gu.merge_into(None)[0])
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "dli-fail")
    _add_decision(wt, "104", "My decision")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: ADR-104")
    _write(work, "unrelated.txt", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "chore: unrelated")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(
        integrate_regenerate, "dli_refresh_best_effort", lambda _root: "index is unwritable",
    )
    result = integrate_main.integrate(
        wt, run_id="iterate-2026-08-07-decision-log-index-fail", reason="fail path",
    )
    steps = result.get("steps") or []
    assert "decision-log-index-refresh-failed" in steps, (
        f"a failed index refresh must reach the caller's result, not just stderr: {result}"
    )
    assert "decision-log-index-refreshed" not in steps
