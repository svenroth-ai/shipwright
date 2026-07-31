"""Git-timeout fail-safes for the MAIN-tree writers: reconcile_triage + sweep_drift.

Split from ``test_store_git_timeout_paths.py`` (which keeps the ``run_git_soft``
primitive and the sweep_outbox/sweep_gc sites) when that module crossed the
300-line guideline.

These two matter most: unlike the sweep, their git calls run in the operator's MAIN
tree, so ``run_git``'s kill-on-timeout strands ``.git/index.lock`` in the repo the
operator is actually using.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import pytest  # noqa: E402

import _sweep_helpers as h  # noqa: E402
from lib import reconcile_triage as rt  # noqa: E402
from lib import sweep_drift as sd  # noqa: E402
from lib import sweep_outbox as so  # noqa: E402
from lib.git_base import TIMEOUT_RETURNCODE  # noqa: E402


@pytest.fixture
def repo(git_origin_repo):
    work, _origin = git_origin_repo
    h.set_identity(work)
    return work

# ---------------------------------------------------------------------------
# reconcile_triage — AC-5, and the one whose stranded lock hits the MAIN tree
# ---------------------------------------------------------------------------

def test_reconcile_commit_timeout_returns_a_structured_error(repo, monkeypatch) -> None:
    """AC-5's whole deliverable. Previously this raised out of the caller."""
    h.seed_tracked(repo, h.item("trg-seed"))
    h.write_outbox(repo)  # ensure .shipwright exists
    (repo / ".shipwright" / "triage.jsonl").write_text(
        "\n".join([h.HEADER, h.item("trg-seed"), h.item("trg-drift")]) + "\n",
        encoding="utf-8", newline="\n")

    real = rt.run_git_soft

    def wrapper(args, **kwargs):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess(
                ["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(rt, "run_git_soft", wrapper)
    result = rt.reconcile_main_triage(repo)
    assert result.status == "error", result.to_dict()
    assert result.reason == "commit_timeout", result.to_dict()


def test_reconcile_read_failure_is_structured_not_raised(repo, monkeypatch) -> None:
    """AC-1's other half: ``UnicodeDecodeError`` is a ``ValueError``, NOT an ``OSError``,
    so it used to escape the handler that promises a structured ``read_failed``.

    Real DRIFT is created first — the function short-circuits on ``no_drift`` well
    before the read, so without it this test would pass while exercising nothing.
    """
    h.seed_tracked(repo, h.item("trg-seed"))
    triage_path = repo / ".shipwright" / "triage.jsonl"
    triage_path.write_bytes(
        triage_path.read_bytes() + (h.item("trg-drift") + "\n").encode("utf-8")
    )

    real_open = Path.open

    def boom(self, *a, **k):
        # Scoped to the triage log only: a blanket Path.open patch also breaks the
        # lock file and the guards, so the read would never be reached.
        if self.name == "triage.jsonl":
            raise ValueError("simulated decode failure")
        return real_open(self, *a, **k)

    monkeypatch.setattr(Path, "open", boom)
    result = rt.reconcile_main_triage(repo)
    assert result.status == "error", result.to_dict()
    assert result.reason.startswith("read_failed"), result.to_dict()


# ---------------------------------------------------------------------------
# sweep_drift — in the sweep's locked section, and it writes MAIN's tree
# ---------------------------------------------------------------------------

def test_unreadable_head_refuses_instead_of_claiming_no_blob(repo, monkeypatch) -> None:
    """A timeout must not be reported as ``main_tracked_no_head_blob``.

    That is a confident diagnosis ("HEAD genuinely has no such blob") drawn from a
    question git never answered — and it routes to ``unrepairable`` rather than to a
    retryable refusal.
    """
    h.seed_tracked(repo, h.item("trg-seed"))
    monkeypatch.setattr(sd, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    plan = sd.plan_main_tracked_drift(repo, repo / ".shipwright" / "triage.outbox.jsonl")
    assert plan.status == "refused", plan
    assert "head_unreadable" in plan.reason, plan.reason


def test_index_probe_timeout_refuses(repo, monkeypatch) -> None:
    """``_index_diverged`` is already fail-closed; pin it so it stays that way."""
    monkeypatch.setattr(sd, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    assert sd._index_diverged(repo) is True


def test_two_failed_head_reads_do_not_read_as_unchanged(repo, monkeypatch) -> None:
    """Two failed HEAD reads must not compare equal and license the restore.

    ``_head_oid`` returns ``""`` when git could not answer. The pre-fix condition was
    ``_head_oid(main_root) != plan._head_oid or <raw changed>`` — with BOTH reads
    failing, ``"" != ""`` is False and the raw is unchanged, so the whole guard
    evaluated False and the code ran ``git checkout -- <triage>`` in the MAIN tree on
    the strength of two failures. That command succeeds, so the operator's
    uncommitted drift is destroyed.

    The assertion is therefore on the FILE, not on a status word: the drift line must
    still be on disk. An earlier version of this test set only ``_head_oid=""`` while
    leaving the live read real — which made ``current != plan`` fire, the condition
    the OLD code already had, so it passed green against the unfixed guard
    (Stage-1 review caught it).
    """
    h.seed_tracked(repo, h.item("trg-seed"))
    triage_path = repo / ".shipwright" / "triage.jsonl"
    triage_path.write_bytes(
        triage_path.read_bytes() + (h.item("trg-drift") + "\n").encode("utf-8"))
    raw_now = triage_path.read_text(encoding="utf-8")

    # `_raw` matches disk, so the second clause CANNOT fire; `_head_oid=""` on both
    # sides, so the first clause cannot fire either under the old condition. Only the
    # new "cannot prove it did not move" clause can catch this.
    plan = sd.DriftPlan("adoptable", drift=[h.item("trg-drift")], fresh=[],
                        _raw=raw_now, _head_oid="")

    # ONLY `rev-parse` fails, so the re-read also yields "". `checkout` is left REAL
    # — the danger is that it succeeds and wipes the drift, so stubbing it out would
    # hide exactly what this test exists to catch.
    real = sd.run_git_soft

    def only_rev_parse_times_out(args, **kwargs):
        if args and args[0] == "rev-parse":
            return subprocess.CompletedProcess(
                ["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(sd, "run_git_soft", only_rev_parse_times_out)

    out = sd.commit_main_tracked_drift(
        plan, repo, repo / ".shipwright" / "triage.outbox.jsonl")

    assert out.status == "buffered", out
    assert "changed_during_adopt" in out.reason, out.reason
    assert h.item("trg-drift") in triage_path.read_text(encoding="utf-8"), (
        "the operator's uncommitted drift was destroyed by a restore licensed by two "
        "FAILED HEAD reads"
    )


def test_op_in_progress_says_yes_when_only_the_gitpath_probe_times_out(repo, monkeypatch) -> None:
    """The SECOND loop must fail closed too — a rebase sets none of the pseudo-refs.

    Doubt review found this: the first loop got the TIMEOUT check, the second kept a
    bare ``if returncode != 0: continue``, which reads a timeout as "this marker is
    absent". Since ``rebase-merge`` / ``rebase-apply`` / ``BISECT_LOG`` are the ONLY
    things that detect a rebase, that let the sweep commit into a half-finished one.

    The existing test could not see it: it patched EVERY call to 124, so the first
    loop returned on iteration one and the second never ran. This one times out only
    the ``--git-path`` probes and lets the pseudo-ref probes answer honestly.
    """
    real = so.run_git_soft

    def only_gitpath_times_out(args, **kwargs):
        if args[:2] == ["rev-parse", "--git-path"]:
            return subprocess.CompletedProcess(
                ["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(so, "run_git_soft", only_gitpath_times_out)
    assert so._op_in_progress(repo) is True


def test_reconcile_op_in_progress_gitpath_timeout_also_fails_closed(repo, monkeypatch) -> None:
    """Same gap, same fix, in the module whose commit lands in the MAIN tree."""
    real = rt.run_git_soft

    def only_gitpath_times_out(args, **kwargs):
        if args[:2] == ["rev-parse", "--git-path"]:
            return subprocess.CompletedProcess(
                ["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(rt, "run_git_soft", only_gitpath_times_out)
    assert rt._op_in_progress(repo) is True


def test_has_drift_timeout_is_an_error_not_no_drift(repo, monkeypatch) -> None:
    """Row 44's real pin. ``_has_drift`` returning a confident False on a timeout
    would report ``no_drift`` over a log that has some — and `git status --porcelain`
    refreshes the index, so it is also where a stranded lock lands in the main tree."""
    h.seed_tracked(repo, h.item("trg-seed"))
    real = rt.run_git_soft

    def status_times_out(args, **kwargs):
        if args[:2] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(
                ["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(rt, "run_git_soft", status_times_out)
    assert rt._has_drift(repo) is None
    result = rt.reconcile_main_triage(repo)
    assert result.status == "error", result.to_dict()
    assert result.reason == "git_timeout: status --porcelain", result.to_dict()


def test_head_line_set_timeout_is_an_error_not_an_empty_head(repo, monkeypatch) -> None:
    """Row 44's other half: an empty set would count every existing line as newly
    folded and misreport the total."""
    monkeypatch.setattr(rt, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    assert rt._head_line_set(repo) is None


def test_an_all_crlf_store_survives_an_lf_append_and_folds(repo) -> None:
    """MIGRATION: this repo's own tracked store is 100% CRLF, and `_append_line` now
    writes LF. Nothing exercised that transition.

    Doubt review measured it — 1145/1145 CRLF lines in the live store — and traced
    that every reader tolerates the mixed state, so this is a coverage gap on the
    system's most load-bearing write rather than a known defect. It is pinned here
    because "traced and could not break it" is not the same as "tested".
    """
    import triage

    triage_path = repo / ".shipwright" / "triage.jsonl"
    triage_path.parent.mkdir(parents=True, exist_ok=True)
    # An all-CRLF store, exactly like the one on disk today.
    triage_path.write_bytes(
        (h.HEADER + "\r\n" + h.item("trg-crlf01") + "\r\n"
         + h.item("trg-crlf02") + "\r\n").encode("utf-8"))
    h.git(repo, "add", "--", ".shipwright/triage.jsonl")
    h.git(repo, "commit", "-m", "seed CRLF store")

    # The REAL appender, which now writes LF.
    triage.append_triage_item(
        repo, source="plugin-sync", severity="low", kind="maintenance",
        title="lf-into-crlf", detail="d", to_outbox=False,
    )

    raw = triage_path.read_bytes()
    assert b"\r\n" in raw and raw.endswith(b"}\n"), f"expected a mixed store: {raw!r}"

    # Every reader must still see three appends + the header, and the fold must
    # validate rather than refusing `main_tracked_diverged` on the EOL difference.
    items = triage.read_all_items(repo)
    assert len([i for i in items if i.get("id", "").startswith("trg-crlf")]) == 2

    result = rt.reconcile_main_triage(repo)
    assert result.status in ("committed", "no_drift"), result.to_dict()
    assert triage.read_all_items(repo), "the fold emptied the store"


def test_has_drift_is_indeterminate_on_ANY_git_failure(repo, monkeypatch) -> None:
    """Not just a timeout: `git status` has no legitimate non-zero outcome here.

    External review (GPT) caught that the first cut special-cased only
    `TIMEOUT_RETURNCODE`, so an ordinary failure left stdout empty and `bool("")`
    reported a confident "no drift" from an unanswered probe — the same fail-open the
    rest of this change exists to close.
    """
    h.seed_tracked(repo, h.item("trg-seed"))
    monkeypatch.setattr(rt, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], 128, "", "fatal: not a git repository"))
    assert rt._has_drift(repo) is None
