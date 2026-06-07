"""AC-5 / AC-6 wiring + CLI tests for ``reconcile_main_triage``.

- ``integrate_main.integrate`` folds main-tree triage drift BEFORE its merge.
- ``setup_iterate_worktree.setup`` folds it BEFORE snapshotting, so a new
  worktree's background appends are committed (durable) and the snapshot is clean.
- the ``tools/reconcile_main_triage.py`` CLI maps statuses to exit codes.

CI note: the live wiring skips in CI (no auto-commit), so these tests
``delenv("CI")`` to exercise the real commit path deterministically.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Order matters: shared/scripts must precede shared/tests on sys.path so
# ``from tools import ...`` resolves to shared/scripts/tools, not the unrelated
# shared/tests/tools test package. shared/tests stays on path for the helper.
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

import _reconcile_helpers as h  # noqa: E402
from tools import integrate_main  # noqa: E402
from tools import reconcile_main_triage as cli  # noqa: E402
from tools import setup_iterate_worktree  # noqa: E402

TRIAGE = h.TRIAGE


# --------------------------------------------------------------------------- #
# AC-5 — integrate_main reconciles before its merge
# --------------------------------------------------------------------------- #


def test_integrate_main_reconciles_before_merge(git_origin_repo, make_worktree, monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    wt = make_worktree(work, "integ-recon")
    h.append(work, h.item("trg-bbbb"))  # background drift in the MAIN tree

    result = integrate_main.integrate(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "ok", result
    steps = result["steps"]
    assert "reconciled-main-triage:committed" in steps, steps
    # The reconcile step runs before any merge bookkeeping.
    merge_steps = [s for s in steps if s in ("already-up-to-date", "merge-committed")]
    assert steps.index("reconciled-main-triage:committed") < steps.index(merge_steps[0])
    # The drift is now a chore(triage) commit on the MAIN tree.
    subject = h.git(work, "log", "-1", "--format=%s").stdout.strip()
    assert subject.startswith("chore(triage):"), subject


def test_integrate_main_reconcile_is_noop_without_drift(git_origin_repo, make_worktree, monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    wt = make_worktree(work, "integ-clean")
    before = h.head_count(work)

    result = integrate_main.integrate(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "ok", result
    assert "reconciled-main-triage:no_drift" in result["steps"], result["steps"]
    assert h.head_count(work) == before  # no spurious commit


# --------------------------------------------------------------------------- #
# AC-6 — setup_iterate_worktree reconciles before snapshotting
# --------------------------------------------------------------------------- #


def test_setup_worktree_commits_drift_and_clean_snapshot(git_origin_repo, monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))  # background drift before a new iterate

    code, payload = setup_iterate_worktree.setup(str(work), "orphan-close", "iterate-y")

    assert code == 0 and payload["action"] == "created", payload
    # Drift was committed to local main (no silent loss — AC-6).
    subject = h.git(work, "log", "-1", "--format=%s").stdout.strip()
    assert subject.startswith("chore(triage):"), subject
    assert "trg-bbbb" in h.git(work, "show", f"HEAD:{TRIAGE}").stdout
    # The snapshot baseline is clean of the triage log.
    snap = json.loads(Path(payload["snapshot_path"]).read_text(encoding="utf-8"))
    assert TRIAGE not in snap.get("dirty_paths", []), snap


# --------------------------------------------------------------------------- #
# CLI — status → exit-code mapping
# --------------------------------------------------------------------------- #


def test_cli_allow_ci_opt_in_flips_skip_to_commit(git_origin_repo, monkeypatch) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))
    monkeypatch.setenv("CI", "true")

    # Without --allow-ci the CLI must SKIP (no commit) under CI...
    rc_skip = cli.main(["--project-root", str(work)])
    assert rc_skip == 0
    assert not h.git(work, "log", "-1", "--format=%s").stdout.strip().startswith("chore(triage):")

    # ...and --allow-ci flips it to a real commit (the only state where it matters).
    rc = cli.main(["--project-root", str(work), "--allow-ci"])
    assert rc == 0
    assert h.git(work, "log", "-1", "--format=%s").stdout.strip().startswith("chore(triage):")


def test_cli_invalid_log_exits_three(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, "not json at all")

    rc = cli.main(["--project-root", str(work), "--allow-ci"])

    assert rc == 3


def test_cli_no_drift_exits_zero(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))

    rc = cli.main(["--project-root", str(work), "--allow-ci"])

    assert rc == 0
