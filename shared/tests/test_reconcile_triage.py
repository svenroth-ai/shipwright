"""Library behaviour for ``lib/reconcile_triage.reconcile_main_triage`` — the
guarded commit-path that folds uncommitted main-tree ``.shipwright/triage.jsonl``
background appends into one ``chore(triage)`` commit.

Covers AC-1 (detect/validate/dedup/commit), AC-2 (B7-exempt + idempotent),
AC-7 (validate fail-closed + dedup + encoding round-trip). Safety-guard no-ops
(AC-3), worktree resolution + the AC-4 pull-unblock live in
``test_reconcile_triage_guards.py``; the integrate/setup wiring (AC-5/AC-6) in
``test_reconcile_triage_wiring.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# shared/scripts must precede shared/tests so ``from lib import ...`` resolves to
# shared/scripts/lib (shared/tests stays on path only for the _reconcile helper).
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

import _reconcile_helpers as h  # noqa: E402
from lib import reconcile_triage  # noqa: E402

TRIAGE = h.TRIAGE


# --------------------------------------------------------------------------- #
# AC-1 / AC-2 — detect, commit, idempotent
# --------------------------------------------------------------------------- #


def test_commits_drift_as_chore(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    before = h.head_count(work)
    h.append(work, h.item("trg-bbbb"), h.item("trg-cccc"))

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "committed", res
    assert res.folded == 2, res
    subject = h.git(work, "log", "-1", "--format=%s").stdout.strip()
    assert subject.startswith("chore(triage):"), subject
    assert h.head_count(work) == before + 1
    assert h.git(work, "status", "--porcelain", "--", TRIAGE).stdout.strip() == ""
    committed = h.git(work, "show", f"HEAD:{TRIAGE}").stdout
    assert "trg-bbbb" in committed and "trg-cccc" in committed


def test_no_drift_is_noop(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    before = h.head_count(work)

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "no_drift", res
    assert h.head_count(work) == before


def test_idempotent_second_run_is_noop(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))

    first = reconcile_triage.reconcile_main_triage(work, allow_ci=True)
    second = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert first.status == "committed"
    assert second.status == "no_drift", second


def test_commit_is_b7_exempt_no_fr_linkage(git_origin_repo) -> None:
    """AC-2: chore type (Rule E) + no Run-ID/FR trailer."""
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    h.append(work, h.item("trg-bbbb"))

    reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    body = h.git(work, "log", "-1", "--format=%B").stdout
    assert body.split(":", 1)[0].strip().lower() == "chore(triage)"
    assert "Run-ID:" not in body
    assert "FR-" not in body


# --------------------------------------------------------------------------- #
# AC-7 — validate fail-closed + dedup + encoding round-trip
# --------------------------------------------------------------------------- #


def test_invalid_log_is_not_committed(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    h.seed_tracked_triage(work, h.item("trg-aaaa"))
    before = h.head_count(work)
    h.append(work, "this is NOT json")

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "invalid", res
    assert res.errors
    assert h.head_count(work) == before
    # The dirty working tree is left untouched for the operator to inspect.
    assert "NOT json" in (work / TRIAGE).read_text(encoding="utf-8")


def test_dedup_folds_exact_duplicate_lines(git_origin_repo) -> None:
    work, _ = git_origin_repo
    h.set_identity(work)
    dup = h.item("trg-aaaa")
    h.seed_tracked_triage(work, dup)
    # Re-append the EXACT same line (a double-write) + one genuinely new line.
    h.append(work, dup, h.item("trg-bbbb"))

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "committed", res
    assert res.folded == 1, res  # only trg-bbbb is genuinely new
    committed = h.git(work, "show", f"HEAD:{TRIAGE}").stdout
    assert committed.count(dup) == 1  # duplicate collapsed to a single line


def test_non_ascii_preserved_and_mixed_eol_handled(git_origin_repo) -> None:
    """AC-7: a dedup over a genuinely MIXED-EOL working file must collapse the
    duplicate (the realistic autocrlf=true case) AND byte-preserve non-ASCII.
    The CRLF duplicate is written with explicit bytes so the mixed-EOL path is
    exercised on every platform, not just a Windows runner."""
    work, _ = git_origin_repo
    h.set_identity(work)
    dup = h.item("trg-aaaa")
    h.seed_tracked_triage(work, dup)  # committed log ends the dup line with LF (in repo)
    unicode_line = '{"event":"append","id":"trg-uni","title":"München — café","status":"triage"}'
    # Append a CRLF duplicate of `dup` + the unicode line → mixed endings.
    with (work / TRIAGE).open("ab") as fh:
        fh.write((dup + "\r\n").encode("utf-8"))
        fh.write((unicode_line + "\n").encode("utf-8"))

    res = reconcile_triage.reconcile_main_triage(work, allow_ci=True)

    assert res.status == "committed", res
    committed = h.git(work, "show", f"HEAD:{TRIAGE}").stdout
    assert committed.count(dup) == 1  # CRLF dup collapsed against the LF original
    assert "München — café" in committed
