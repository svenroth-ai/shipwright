"""Wiring tests after campaign 2026-06-08-triage-outbox-delivery / D2.

D2 RELEGATED ``reconcile_main_triage`` to a manual-CLI-only fallback:

- ``setup_iterate_worktree.setup`` no longer folds main drift into a local-main
  ``chore(triage)`` commit — it SWEEPS the gitignored outbox into the iterate
  BRANCH (see ``test_sweep_outbox.py`` + the setup-sweep tests below).
- ``integrate_main.integrate`` no longer calls ``reconcile_main_triage`` at all
  (Codex Q1: the merge runs in the worktree, never against main).
- the ``tools/reconcile_main_triage.py`` CLI still maps statuses to exit codes
  (the manual "unblock a hand pull, no imminent iterate" path survives).

CI note: the live wiring skips in CI (no auto-commit), so the CLI tests
``delenv("CI")`` / ``--allow-ci`` to exercise the real commit path.
"""

from __future__ import annotations

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
OUTBOX = ".shipwright/triage.outbox.jsonl"


def _write_outbox(work: Path, *lines: str) -> None:
    p = work / OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def _branch_triage(work: Path, slug: str) -> str:
    wt = work / ".worktrees" / slug
    return h.git(wt, "show", f"HEAD:{TRIAGE}", check=False).stdout


# --------------------------------------------------------------------------- #
# D2 — integrate_main NO LONGER reconciles main (Codex Q1)
# --------------------------------------------------------------------------- #


def test_integrate_main_does_not_reconcile_main(git_origin_repo, make_worktree, monkeypatch) -> None:
    """The integrate flow must NOT emit a reconcile step, NOT create a
    chore(triage) commit on local main, AND NOT consume/clear the D1 outbox —
    even with background producers having written the outbox (the real D1/D2
    producer path, not a tracked-log append). Delivery is the next setup's sweep,
    never integrate (external code review, OpenAI)."""
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    wt = make_worktree(work, "integ-no-recon")
    _write_outbox(work, h.item("trg-bbbb"))  # D1 background producer → outbox
    main_head_before = h.git(work, "rev-parse", "main").stdout.strip()

    result = integrate_main.integrate(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "ok", result
    # No reconcile step is recorded anymore.
    assert not any("reconcile" in s for s in result["steps"]), result["steps"]
    # Local main did NOT move (no fold commit).
    assert h.git(work, "rev-parse", "main").stdout.strip() == main_head_before
    subject = h.git(work, "log", "main", "-1", "--format=%s").stdout.strip()
    assert not subject.startswith("chore(triage):"), subject
    # integrate did NOT touch the outbox — the line is still buffered for the
    # next setup's sweep (integrate is not a delivery path).
    outbox = (work / OUTBOX).read_text(encoding="utf-8")
    assert h.item("trg-bbbb") in outbox


def test_integrate_main_worktree_merge_still_succeeds(git_origin_repo, make_worktree, monkeypatch) -> None:
    """AC-6: dropping the reconcile call must not break the worktree merge."""
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    wt = make_worktree(work, "integ-merge-ok")
    # origin/main advances so there is something real to integrate.
    h.append(work, h.item("trg-cccc"))
    h.git(work, "commit", "-am", "main advances")
    h.git(work, "push", "origin", "main")

    result = integrate_main.integrate(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "ok", result
    assert "merge-committed" in result["steps"], result["steps"]
    # The advanced main line is now reachable from the worktree branch.
    assert "trg-cccc" in h.git(wt, "show", f"HEAD:{TRIAGE}").stdout


# --------------------------------------------------------------------------- #
# D2 — setup SWEEPS the outbox into the BRANCH (no local-main fold)
# --------------------------------------------------------------------------- #


def test_setup_sweeps_outbox_into_branch_not_main(git_origin_repo, monkeypatch) -> None:
    """setup folds the gitignored outbox onto the iterate branch (ships in the
    PR); local main gets NO chore(triage) commit and the snapshot stays clean."""
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    _write_outbox(work, h.item("trg-bbbb"))  # background producer wrote the outbox
    main_head_before = h.git(work, "rev-parse", "main").stdout.strip()

    import json
    code, payload = setup_iterate_worktree.setup(str(work), "sweep-into-branch", "iterate-y")

    assert code == 0 and payload["action"] == "created", payload
    # The outbox line is committed on the BRANCH...
    assert "trg-bbbb" in _branch_triage(work, "sweep-into-branch")
    # ...and local main did NOT move (no fold commit).
    assert h.git(work, "rev-parse", "main").stdout.strip() == main_head_before
    # The snapshot baseline is clean of the triage log.
    snap = json.loads(Path(payload["snapshot_path"]).read_text(encoding="utf-8"))
    assert TRIAGE not in snap.get("dirty_paths", []), snap


def test_setup_no_outbox_is_clean(git_origin_repo, monkeypatch) -> None:
    """No outbox → setup creates the worktree with no sweep commit on the branch."""
    monkeypatch.delenv("CI", raising=False)
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))

    code, payload = setup_iterate_worktree.setup(str(work), "sweep-clean", "iterate-z")

    assert code == 0 and payload["action"] == "created", payload
    subject = h.git(work / ".worktrees" / "sweep-clean", "log", "-1", "--format=%s").stdout.strip()
    assert not subject.startswith("chore(triage):"), subject


# --------------------------------------------------------------------------- #
# Manual CLI — status → exit-code mapping (the surviving fallback path)
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
