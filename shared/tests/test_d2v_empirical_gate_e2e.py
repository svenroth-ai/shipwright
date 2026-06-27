"""D2V — EMPIRICAL verification gate: e2e proofs (abandoned-branch / exactly-once
/ no-main-pollution) over the REAL setup + integrate paths.

Campaign 2026-06-08-triage-outbox-delivery / D2V. Methods 2-4 of the HARD gate;
method 1 (concurrency stress) lives in ``test_d2v_empirical_gate.py``. Split for
the 300-LOC guideline. Everything here drives REAL git + the REAL
``tools.setup_iterate_worktree.setup`` (which calls the real sweep) and the REAL
``tools.integrate_main.integrate`` (dedup-provided exactly-once) — no mocks.

* METHOD 2 — ABANDONED-BRANCH E2E: real outbox → real ``setup`` (sweeps onto a
  real iterate branch) → DELETE the branch unmerged (``git worktree remove
  --force`` + ``git branch -D``) → next real ``setup`` → the line is RE-SWEPT and
  present (survives in the outbox, never stranded).
* METHOD 3 — EXACTLY-ONCE AFTER A REAL MERGE: two committed sides each carry the
  swept line; the REAL ``integrate_main.integrate`` (whose unconditional dedup —
  not bare ``merge=union`` — provides exactly-once, per the D2 ADR) merges them;
  the line appears EXACTLY once and ``validate_triage_text`` passes. CRLF +
  ordering covered.
* METHOD 4 — NO MAIN POLLUTION: after a full real ``setup``, local ``main`` HEAD
  carries NO new ``chore(triage)`` fold commit (delivery rides the branch).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))  # helpers (precede scripts)
sys.path.insert(0, str(_SHARED_SCRIPTS))  # shared/scripts — wins for ``tools``

import _d2v_helpers as ev  # noqa: E402
import _sweep_helpers as h  # noqa: E402
import triage  # noqa: E402
from lib.churn_merge import validate_triage_text  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from tools import integrate_main, setup_iterate_worktree  # noqa: E402

TRIAGE = h.TRIAGE


@pytest.fixture
def repo(git_origin_repo):
    work, _origin = git_origin_repo
    h.set_identity(work)
    return work


def _main_head_subjects(work: Path) -> list[str]:
    """Commit subjects reachable from local ``main`` HEAD (most-recent first)."""
    proc = h.git(work, "log", "--format=%s", "main")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


# --------------------------------------------------------------------------- #
# METHOD 2 — abandoned-branch end-to-end (real setup + real branch deletion)
# --------------------------------------------------------------------------- #


def test_method2_abandoned_branch_survives_and_resweeps(repo, _evidence) -> None:
    """The orphaned-branch data-loss mode Codex flagged: a swept line on a branch
    that is DELETED unmerged must NOT be stranded — it survives in the durable
    gitignored outbox and is re-swept onto the next iterate branch."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    line = h.item("trg-abandon")
    h.write_outbox(work, line)
    refs: dict[str, str] = {}
    passed = True
    detail = ""
    try:
        # First real setup → sweeps the line onto iterate/d2v-aband-1.
        rc1, p1 = setup_iterate_worktree.setup(str(work), "d2v-aband-1", "run-aband-1")
        assert rc1 == 0, p1
        # ``setup`` returns the created worktree path under ``project_root``.
        wt1 = Path(p1["project_root"])
        refs["branch1_head"] = h.git(wt1, "rev-parse", "HEAD").stdout.strip()
        assert line in h.branch_triage_lines(wt1), "line was not swept onto branch 1"
        # Origin never advanced → GC kept the line in the durable outbox.
        assert line in h.outbox_lines(work), "swept line vanished from the outbox pre-merge"

        # ABANDON branch 1 UNMERGED (real teardown the way iterate cleanup does).
        h.git(work, "worktree", "remove", "--force", str(wt1))
        h.git(work, "branch", "-D", "iterate/d2v-aband-1")

        # Next real setup → the line is RE-SWEPT onto the new branch (not stranded).
        rc2, p2 = setup_iterate_worktree.setup(str(work), "d2v-aband-2", "run-aband-2")
        assert rc2 == 0, p2
        wt2 = Path(p2["project_root"])
        refs["branch2_head"] = h.git(wt2, "rev-parse", "HEAD").stdout.strip()
        assert line in h.branch_triage_lines(wt2), (
            "line STRANDED — not re-swept onto branch 2 after branch 1 abandoned"
        )
        detail = (
            "real setup sweeps line onto branch 1; branch 1 deleted unmerged "
            "(worktree remove --force + branch -D); next real setup RE-SWEEPS it "
            "onto branch 2 — survived in the durable outbox, never stranded."
        )
    except AssertionError as exc:
        passed = False
        detail = f"FAILED: {exc}"
        raise
    finally:
        _evidence.record(ev.MethodResult(
            name="METHOD 2 — abandoned-branch e2e (real setup + branch -D)",
            passed=passed, iterations=2, detail=detail, git_refs=refs,
            sample_before=[line], sample_after=sorted(h.outbox_lines(work))[:6],
        ))


# --------------------------------------------------------------------------- #
# METHOD 3 — exactly-once after a REAL merge (integrate-dedup-provided)
# --------------------------------------------------------------------------- #


def test_method3_exactly_once_after_real_merge(repo, _evidence) -> None:
    """Two iterate branches each sweep the SAME line; the REAL integrate path
    (unconditional dedup, NOT bare merge=union) collapses them to EXACTLY ONE in
    the final origin log, which validates. Covers CRLF + ordering: the seeded log
    keeps a header-first ordering and the swept line carries a CRLF in the outbox
    that must normalize to the canonical LF wire form before the dedup match."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    # Outbox line carries a CRLF terminator (Windows-edited shape) — the producer
    # path writes LF, but a human/tool edit can introduce CRLF; the sweep must
    # normalize it so the two branches' tracked copies are byte-identical.
    crlf_line = h.item("trg-once")
    p = work / ev.OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes((crlf_line + "\r\n").encode("utf-8"))

    refs: dict[str, str] = {}
    passed = True
    detail = ""
    try:
        wtx = h.make_worktree(work, "d2v-once-x")
        rx = sweep_outbox_to_branch(work, wtx, default_branch="main")
        assert rx.status == "committed" and rx.swept == 1, rx.to_dict()
        wty = h.make_worktree(work, "d2v-once-y")
        ry = sweep_outbox_to_branch(work, wty, default_branch="main")
        assert ry.status == "committed" and ry.swept == 1, ry.to_dict()

        # X lands first via a REAL ``git merge`` governed by the seeded
        # ``.gitattributes merge=union`` driver (external-review gemini-M /
        # openai-M3: prove the union driver itself, not only integrate's dedup).
        h.git(work, "fetch", "origin")
        h.git(work, "merge", "--no-ff", "--no-edit", "iterate/d2v-once-x")
        h.git(work, "push", "origin", "main")
        refs["origin_after_x"] = h.git(work, "rev-parse", "origin/main").stdout.strip()
        # The union merge DELIVERED the line to origin (no loss at the merge layer).
        origin_after_x = h.git(work, "show", f"origin/main:{TRIAGE}").stdout
        assert any(ln.strip() == crlf_line for ln in origin_after_x.splitlines()), (
            "merge=union driver dropped the swept line during the X merge"
        )

        # Integrate origin into Y via the REAL integrate — both sides carry the
        # line, so only integrate's dedup collapses them to one.
        res = integrate_main.integrate(wty, "iterate-d2v-once", do_fetch=True)
        assert res["status"] == "ok", res
        h.git(wty, "push", "origin", "HEAD:main")
        refs["origin_after_y"] = h.git(work, "rev-parse", "origin/main").stdout.strip()

        origin_text = h.git(work, "show", f"origin/main:{TRIAGE}").stdout
        occurrences = sum(1 for ln in origin_text.splitlines() if ln.strip() == crlf_line)
        assert occurrences == 1, f"expected exactly-once, got {occurrences}\n{origin_text}"
        assert validate_triage_text(origin_text) == [], "final origin log failed validation"
        # Ordering: the schema header is still line 1 after both merges.
        first = origin_text.splitlines()[0].strip()
        assert '"schema":"triage"' in first, f"header not first after merge: {first!r}"
        detail = (
            "two branches sweep the same CRLF-terminated line; X merged to origin, "
            "origin integrated into Y via the REAL integrate (dedup-provided), Y "
            "pushed; final origin log carries the line EXACTLY once, validates, "
            "header still ordered first."
        )
    except AssertionError as exc:
        passed = False
        detail = f"FAILED: {exc}"
        raise
    finally:
        _evidence.record(ev.MethodResult(
            name="METHOD 3 — exactly-once after a real integrate merge (CRLF+order)",
            passed=passed, iterations=1, detail=detail, git_refs=refs,
            sample_before=[crlf_line + "  <CRLF>"], sample_after=[crlf_line],
        ))


# --------------------------------------------------------------------------- #
# METHOD 4 — no main pollution after a full real setup
# --------------------------------------------------------------------------- #


def test_method4_no_main_fold_commit_after_setup(repo, _evidence) -> None:
    """After a full real ``setup`` (which sweeps the outbox onto the iterate
    branch), local ``main`` HEAD must carry NO new ``chore(triage)`` fold commit —
    the whole point of the campaign (delivery rides the PR branch, never local
    main)."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    main_subjects_before = _main_head_subjects(work)
    # Append via the REAL producer to the outbox (not a fixture write).
    triage.append_triage_item(
        work, source="plugin-sync", severity="low", kind="maintenance",
        title="trg-nopol", detail="d", to_outbox=True,
    )
    refs: dict[str, str] = {"main_before": h.git(work, "rev-parse", "main").stdout.strip()}
    passed = True
    detail = ""
    try:
        rc, p = setup_iterate_worktree.setup(str(work), "d2v-nopol", "run-nopol")
        assert rc == 0, p
        wt = Path(p["project_root"])
        refs["main_after"] = h.git(work, "rev-parse", "main").stdout.strip()
        refs["branch_head"] = h.git(wt, "rev-parse", "HEAD").stdout.strip()

        # main HEAD is byte-identical before/after (no fold commit landed).
        assert refs["main_before"] == refs["main_after"], (
            "local main HEAD MOVED during setup — a fold commit polluted main"
        )
        main_subjects_after = _main_head_subjects(work)
        assert main_subjects_before == main_subjects_after, "new commit subject on main"
        new_fold = [s for s in main_subjects_after if s.startswith("chore(triage)")
                    and s not in main_subjects_before]
        assert not new_fold, f"chore(triage) fold commit polluted main: {new_fold}"
        # And the append DID get delivered onto the branch (delivery rode the PR).
        assert any('"title":"trg-nopol"' in ln for ln in h.branch_triage_lines(wt)), (
            "append was not delivered onto the iterate branch"
        )
        detail = (
            "real setup with a producer-appended outbox line; local main HEAD "
            "unchanged (no chore(triage) fold), append delivered onto the iterate "
            "branch instead."
        )
    except AssertionError as exc:
        passed = False
        detail = f"FAILED: {exc}"
        raise
    finally:
        _evidence.record(ev.MethodResult(
            name="METHOD 4 — no chore(triage) fold commit on local main after setup",
            passed=passed, iterations=1, detail=detail, git_refs=refs,
        ))
