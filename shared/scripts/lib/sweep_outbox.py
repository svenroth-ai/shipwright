"""Sweep the gitignored main-tree triage outbox into the iterate PR branch.

Campaign 2026-06-08-triage-outbox-delivery / D2. The D1 outbox
(``.shipwright/triage.outbox.jsonl``) is a per-tree, GITIGNORED buffer that
idle-main background producers append to (so the tracked log never accrues
drift). D2 DELIVERS those buffered appends: at iterate-worktree setup, the
outbox lines are folded into the *worktree's* tracked ``triage.jsonl`` and
committed on the ``iterate/<slug>`` branch — so they ride the PR to ``origin``
and ``main`` never gets a local fold commit (which previously orphaned on local
main and piled up; Codex Q1).

Three invariants make this loss-proof:

* **Whole-section lock (Codex Q4):** the canonical triage ``_FileLock`` is held
  across adopt-drift -> read-outbox -> read-worktree-tracked -> materialize ->
  branch-commit -> GC. A concurrent background producer appending to the outbox
  serializes against the ENTIRE sweep — it is never read-then-lost.
* **Origin-delivered GC (Codex unlisted failure mode):** an outbox line is
  dropped ONLY once present in ``origin/<default>``'s tracked log — matched by
  CANONICAL FORM, with raw text for anything that has none (see
  :mod:`lib.sweep_gc`; the earlier id-only rule for appends was audit finding 14).
  A just-swept line stays until origin-delivered;
  re-sweeping is harmless (``merge=union`` + dedup → exactly-once).
  NEVER reset-after-read.
* **No undelivered channel (iterate-2026-07-14-sweep-drift-dismiss-loss):** an
  append that lands in MAIN's TRACKED log is routed into the outbox first
  (:mod:`lib.sweep_drift`) — else it reaches no branch, its ``status`` looks like an
  orphan, and the quarantine DESTROYS the operator's dismiss. Nothing may be
  quarantined while its append is merely undelivered.

The EOL-normalize + dedup + validate pipeline (now in :mod:`lib.sweep_quarantine`,
which also quarantines orphan-status lines) is byte-compatible with
:mod:`lib.reconcile_triage` (Codex Q3) so the union merge driver agrees.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Wire up shared/scripts so sibling lib/ + triage import regardless of caller.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import triage  # noqa: E402  — canonical lock + outbox path SSoT
from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.churn_merge import TRIAGE_LOG  # noqa: E402
from lib.ci_env import ci_active  # noqa: E402
from lib.git_base import HOOK_GIT_TIMEOUT, TIMEOUT_RETURNCODE, run_git_soft  # noqa: E402
# The two guards moved to lib.main_tree_guards (iterate-2026-08-07-shared-op-predicates)
# — reconcile_triage.py already re-exported them under these historical private names;
# this file now does too. No `is_detached`: see lib/main_tree_guards.py's docstring for
# why sweep_outbox does not need it (the worktree it commits into is never detached).
from lib.main_tree_guards import (  # noqa: E402,F401  (re-export: see lib/main_tree_guards.py)
    has_staged_changes as _has_staged_changes,
    op_in_progress as _op_in_progress,
)
from lib.sweep_drift import commit_main_tracked_drift, plan_main_tracked_drift  # noqa: E402
from lib.sweep_gc import delivered_membership, partition_outbox  # noqa: E402
from lib.sweep_quarantine import append_quarantine, decide as quarantine_decide, quarantine_path  # noqa: E402
from lib.sweep_result import SweepResult, sweep_warnings, with_adopt_note as _with  # noqa: E402,F401  (re-export: callers import both from here)
from lib.sweep_text import normalize_lines, read_text_verbatim  # noqa: E402


def _ci_active() -> bool:
    """Delegates to the shared leaf — see :mod:`lib.ci_env` for why this is not
    a local copy."""
    return ci_active()


def sweep_outbox_to_branch(
    main_root: Path | str,
    worktree_path: Path | str,
    *,
    default_branch: str,
    allow_ci: bool = False,
) -> SweepResult:
    """Fold the main-tree outbox into the worktree's tracked triage log + commit
    it on the iterate branch, then GC origin-delivered outbox lines. Never raises
    for an expected condition — returns a structured :class:`SweepResult`.

    The canonical triage lock is held across the ENTIRE read->commit->GC critical
    section (Codex Q4) so a concurrent background outbox producer serializes
    against the whole sweep rather than racing a read-then-lost window.

    **``LockTimeout`` propagates** (trg-dc013d82): a canonical lock stuck for the
    whole budget is a host fault, not a ``SweepResult`` — and it used to hang here
    forever rather than return at all.
    """
    main_root = Path(main_root)
    worktree_path = Path(worktree_path)

    # --- cheap guards (no lock needed) -------------------------------------
    if _ci_active() and not allow_ci:
        return SweepResult(status="skipped", reason="ci_without_optin")
    # The commit lands in the WORKTREE, so the op-in-progress / staged-changes
    # guards probe the worktree (not main_root): a half-finished merge or a
    # user's staged WIP THERE is what a ``git commit -- <triage>`` would corrupt.
    if _op_in_progress(worktree_path):
        return SweepResult(status="skipped", reason="op_in_progress")
    if _has_staged_changes(worktree_path):
        return SweepResult(status="skipped", reason="staged_changes")

    outbox_path = triage._outbox_path(main_root)
    worktree_triage = worktree_path / TRIAGE_LOG
    lock_path = triage._lock_path(main_root)

    # --- critical section: ONE lock across plan->read->materialize->commit->GC
    with triage._FileLock(lock_path):
        # An append stranded in MAIN's TRACKED log is delivered by NOTHING, and a `status`
        # for it then looks like an orphan — which is how the sweep used to eat operator
        # dismisses. PLAN its adoption (read-only) so it can ride the branch like any other
        # buffered append. A refusal means the repair does not understand main's state:
        # touch NOTHING and surface it (sweep_drift).
        plan = plan_main_tracked_drift(main_root, outbox_path)
        if plan.status == "refused":
            return SweepResult(status="skipped", reason=plan.reason)

        outbox_raw = read_text_verbatim(outbox_path)
        # The EOL is deliberately NOT kept from this read — the survivor write below
        # takes it from its own re-read, so it reflects the file as it stands then.
        outbox_lines_norm, _ = normalize_lines(outbox_raw)
        # The planned drift joins the outbox VIRTUALLY: the sweep decides against the log it
        # WOULD produce, and only then does anything get written. Adopting first would move
        # the operator's data out of the tracked log into a gitignored buffer and only then
        # discover the sweep must abort — main would look clean while the sole copy sat in a
        # file `git clean -x` deletes (code review, high).
        outbox_lines = [ln for ln in outbox_lines_norm if ln.strip()] + plan.fresh
        if not outbox_lines:
            return SweepResult(status="no_change", reason="empty_outbox")

        worktree_raw = read_text_verbatim(worktree_triage)
        worktree_lines_norm, wt_eol = normalize_lines(worktree_raw)
        # The branch log uses the worktree file's EOL style (LF for a fresh
        # checkout); fall back to LF when the worktree log is absent/empty.
        eol = wt_eol if worktree_raw else "\n"

        # Materialize + classify, then give every un-deliverable line a PROPORTIONAL
        # disposition — quarantine / HOLD / deliver / block. Rules: sweep_quarantine.
        decision = quarantine_decide(
            worktree_lines_norm, outbox_lines, eol,
            known_append_ids=plan.known_append_ids,
        )
        if decision.action == "block":
            # Nothing has been mutated yet — not the outbox, not main's tracked log.
            return SweepResult(status="invalid", errors=decision.errors + decision.warnings)  # notes in errors: sweep_warnings prints both

        # The decision holds: NOW make the adoption real (durable outbox write, then the
        # git restore of main's tracked log).
        adopted, adopt_note = 0, ""
        if plan.status == "adoptable":
            done = commit_main_tracked_drift(plan, main_root, outbox_path)
            adopted, adopt_note = done.adopted, done.reason
            if done.status == "error":  # tracked log MISSING — no replay finishes that
                return SweepResult(status="error", reason=done.reason, adopted=adopted)

        # Driven off the LISTS, not ``action``: quarantine and hold can occur in one sweep
        # and ``action`` names only the stronger. Write order unchanged and load-bearing:
        # quarantine, then branch commit, then the outbox rewrite LAST.
        quarantined, held = len(decision.candidates), len(decision.held_lines)
        if decision.candidates:
            append_quarantine(
                quarantine_path(main_root), decision.candidates,
                reason="un-deliverable status: no append anywhere in the combined triage log, or no usable id",
            )
        # NOT ``outbox_lines``: putting branch content behind that name deletes HELD lines.
        branch_outbox_lines = decision.materialized_outbox
        deduped_text = decision.deduped_text

        # Count genuinely-new lines (not already in the worktree tracked log).
        # JSONL producer lines carry NO surrounding whitespace (``json.dumps(...) +
        # "\n"``), so the stripped membership set == the exact line set here —
        # strip is a CRLF/EOL absorber, not a content mutator.
        wt_set = {ln.strip() for ln in worktree_lines_norm if ln.strip()}
        swept = sum(1 for ln in branch_outbox_lines if ln.strip() and ln.strip() not in wt_set)

        committed_subject = ""
        if deduped_text != worktree_raw:
            worktree_triage.parent.mkdir(parents=True, exist_ok=True)
            # Encoded HERE, not by the primitive: this text came through
            # `read_text_verbatim`'s surrogateescape decode, so it may carry bytes a
            # strict encode would reject. The leniency belongs to this store, not to
            # a primitive thirty-five non-triage callers share.
            durable_atomic_write(
                worktree_triage, deduped_text.encode('utf-8', errors='surrogateescape'))
            add = run_git_soft(["add", "--", TRIAGE_LOG], cwd=worktree_path)
            if add.returncode != 0:
                return SweepResult(status="error", adopted=adopted, reason=_with(adopt_note, f"add_failed: {add.stderr.strip()[:300]}"))
            # FIX D (D2 review cascade): gate the commit on a REAL staged delta.
            # ``deduped_text != worktree_raw`` can be EOL-only (materialized LF vs
            # a CRLF-checked-out log) that git's index — governed by autocrlf —
            # treats as NO change; committing then fails "nothing to commit" → a
            # spurious ``error``. No staged delta → git no-op → ``no_change`` (the
            # GC still runs). ``--quiet`` exits 0 when there is NO staged diff.
            staged = run_git_soft(
                ["diff", "--cached", "--quiet", "--", TRIAGE_LOG], cwd=worktree_path,
            )
            # A timeout must NOT fall through to the ``!= 0`` branch below, which
            # means "there IS a staged delta" — that would read an unknown state as a
            # definite one and commit on the strength of it.
            if staged.returncode == TIMEOUT_RETURNCODE:
                return SweepResult(status="error", adopted=adopted, reason=_with(adopt_note, "git_timeout: diff --cached"))
            if staged.returncode != 0:
                subject = f"chore(triage): sweep {swept} outbox append(s) into branch"
                # The commit fires the bloat pre-commit hook, whose cold ``uv run``
                # on a brand-new worktree routinely exceeds run_git's 15s default —
                # give it a generous timeout and map a timeout to a structured
                # error rather than letting it crash setup (never raises into setup).
                commit = run_git_soft(
                    ["commit", "-m", subject, "--", TRIAGE_LOG],
                    cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT,
                )
                if commit.returncode == TIMEOUT_RETURNCODE:
                    return SweepResult(status="error", adopted=adopted, reason=_with(adopt_note, "commit_timeout"))
                if commit.returncode != 0:
                    return SweepResult(status="error", adopted=adopted, reason=_with(adopt_note, f"commit_failed: {commit.stderr.strip()[:300]}"))
                committed_subject = subject

        # --- GC (still under the lock): drop ONLY origin-delivered lines ----
        # Survivors keep the OUTBOX's OWN EOL (gitignored → no cross-platform
        # rewrite; OpenAI review). FIX B: membership is by CANONICAL FORM for every
        # JSON object (drift-immune, but content-sensitive) + stripped text for
        # anything with no canonical form. The former id-only rule for appends was
        # audit finding 14 — see ``lib/sweep_gc``.
        membership = delivered_membership(main_root, default_branch)

        # RE-READ the outbox HERE rather than reusing the read from the top of the
        # section. Everything between the two — the drift adoption's own durable write,
        # ``git add``, ``git diff --cached`` and a ``git commit`` budgeted 120 s — is a
        # window in which a writer that does NOT hold the canonical lock can append.
        # Such a writer is real and documented in this repo: ``triage_repair.py`` records
        # that the WebUI uses ``proper-lockfile``, which does not compose with the Python
        # byte lock, and the WebUI is the operator's primary dismiss surface.
        #
        # The sibling ``sweep_drift.commit_main_tracked_drift`` re-reads the outbox inside
        # this very section for exactly this reason ("A process lock cannot stop an
        # external `git commit` or an editor") and PRESERVES such an append — and writing
        # the survivors from the stale list then deleted it again a hundred lines later.
        # Two halves of one critical section disagreeing is the whole bug.
        current_lines, outbox_eol = normalize_lines(read_text_verbatim(outbox_path))
        # Quarantined candidates are still ON DISK — ``append_quarantine`` writes the
        # quarantine log, not the outbox — so this rewrite removes them, and a re-read
        # would otherwise resurrect them. CANDIDATES ONLY: a HELD line must survive here.
        quarantined_text = {ln.strip() for ln in decision.candidates} if quarantined else set()

        survivors, gc_dropped = partition_outbox(
            current_lines, membership, quarantined_text)
        # Rewrite the outbox when GC trimmed delivered lines OR quarantine removed orphans
        # this run.
        if gc_dropped or quarantined:
            survivor_text = (outbox_eol.join(survivors) + outbox_eol) if survivors else ""
            durable_atomic_write(
                outbox_path, survivor_text.encode('utf-8', errors='surrogateescape'))

        if not committed_subject:
            # Nothing folded into the branch (every outbox line already tracked);
            # report no_change unless the GC alone trimmed the outbox.
            status = "committed" if gc_dropped else "no_change"
            return SweepResult(
                status=status, reason=_with(adopt_note, "" if gc_dropped else "no_branch_change"),
                swept=0, gc_dropped=gc_dropped, quarantined=quarantined, adopted=adopted,
                held=held, dedup_notes=decision.warnings,
            )

        return SweepResult(
            status="committed", swept=swept, gc_dropped=gc_dropped, reason=adopt_note,
            quarantined=quarantined, adopted=adopted, commit_subject=committed_subject,
            held=held, dedup_notes=decision.warnings,
        )
