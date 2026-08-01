"""What the F11 spec-impact gate SEES — the iterate's work, not the commit at the tip.

`check_spec_impact_recorded` resolved its changed-path set from the SINGLE commit it
was handed. F11 runs `ensure_current` BEFORE the verifier and passes
`--commit $(git rev-parse HEAD)`, so on a branch that was behind, HEAD is an
integration MERGE whose own path set holds only the conflict-resolved files —
measured in `iterate-2026-07-31-it1-s2-expected-status` as 4 paths vs 36 in the
range, with the iterate's spec.md among the 32 that fell out. Same class as #493,
fixed for four sibling gates by #503 (`dcf85f87`); this one was not in that diff.
Own module: `test_verify_iterate_finalization.py` is bloat-baselined and does not
use the real-git `git_origin_repo` / `make_worktree` fixtures this shape needs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402

from tools.verifiers.common import Severity  # noqa: E402
from tools.verifiers.iterate_checks import check_spec_impact_recorded  # noqa: E402

_SPEC = ".shipwright/planning/01-x/spec.md"
_RUN_ID = "iterate-2026-08-01-spec-impact-range-resolver"


def _seed_run(root: Path, intent: str = "feature") -> None:
    """An iterate_history entry the gate will resolve, with a chosen intent."""
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [
            {"run_id": _RUN_ID, "complexity": "medium", "type": intent},
        ]}),
        encoding="utf-8",
    )


def _seed_event(root: Path, commit: str = "", **fields) -> None:
    """A work_completed event for this run.

    ``commit=""`` is the DEFAULT deliberately — that is what F5b writes in the
    worktree flow, and it is why `event_commit` falls back to the caller's HEAD,
    i.e. to the merge. A populated commit field makes the bug unreachable.
    """
    evt = {"type": "work_completed", "source": "iterate",
           "commit": commit, "adr_id": _RUN_ID}
    evt.update(fields)
    (root / "shipwright_events.jsonl").write_text(
        json.dumps(evt) + "\n", encoding="utf-8",
    )


def _assert_names_the_work_not_the_commit(detail: str, head: str) -> None:
    """AC5 — the report must name its real subject.

    The negative half pins the EXACT formulation that misled ("commit <sha> touched
    no …"), not the word "commit": banning the vocabulary item would forbid the
    honest phrasings too, i.e. forbid the correction rather than the defect.
    """
    assert "work up to" in detail.lower(), detail
    assert f"commit {head[:8]} touched no" not in detail, (
        f"the detail names the commit as the subject again: {detail}"
    )


def _build_merge_head(work: Path, make_worktree, *, branch_files: dict[str, str],
                      main_files: dict[str, str]) -> tuple[Path, str]:
    """The real F11 shape: branch commit, main moves, `merge --no-ff origin/main`.

    Returns the worktree and the merge sha, asserting the fixture really produced a
    merge — drift there would leave these tests green while testing nothing.
    """
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "spec-impact-range")
    for rel, text in branch_files.items():
        _write(wt, rel, text)
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: the iterate's own work")

    for rel, text in main_files.items():
        _write(work, rel, text)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves on")
    _git(work, "push", "origin", "main")
    _git(wt, "fetch", "origin")
    _git(wt, "merge", "--no-ff", "--no-edit", "origin/main")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    parents = _git(wt, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3, "the fixture must really put a MERGE commit on top"
    return wt, head


# --- AC1: the blindness itself ----------------------------------------------

def test_the_gate_sees_a_spec_md_carried_by_an_earlier_commit(
    git_origin_repo, make_worktree,
) -> None:
    """The citing run's shape: spec.md in the branch's own commit, an integrate
    merge on top, and the gate must still see it."""
    work, _origin = git_origin_repo
    wt, head = _build_merge_head(
        work, make_worktree,
        branch_files={_SPEC: "| FR-01.01 | x | Must |\n", "app.py": "changed\n"},
        main_files={"other.py": "main moved on\n"},
    )
    _seed_run(wt)
    _seed_event(wt, intent="feature", spec_impact="modify")

    result = check_spec_impact_recorded(wt, _RUN_ID, head)

    assert result.ok is True, (
        "the gate inspected only the merge commit and missed the spec.md below it: "
        f"{result.detail}"
    )
    assert "1 planning spec.md" in result.detail
    _assert_names_the_work_not_the_commit(result.detail, head)


# --- AC2: and the widening must not launder a missing spec -------------------

def test_the_gate_is_not_satisfied_by_a_spec_md_that_came_from_MAIN(
    git_origin_repo, make_worktree,
) -> None:
    """The other direction, so reading a RANGE cannot become a false green.

    MAIN edits the spec.md and the branch merges it in, having touched none itself.
    The range is measured from the merge-base, so mainline's work sits on the base
    side — the gate must still FAIL.
    """
    work, _origin = git_origin_repo
    wt, head = _build_merge_head(
        work, make_worktree,
        branch_files={"app.py": "only a source change\n"},
        main_files={_SPEC: "| FR-09.09 | mainline wrote this | Must |\n"},
    )
    _seed_run(wt)
    _seed_event(wt, intent="feature", spec_impact="modify")

    result = check_spec_impact_recorded(wt, _RUN_ID, head)

    assert result.ok is False, (
        f"inherited mainline's spec.md as if the branch had written it: {result.detail}"
    )
    assert result.severity == Severity.ERROR.value
    _assert_names_the_work_not_the_commit(result.detail, head)


# --- the resolver is genuinely the range one ---------------------------------

def test_the_gate_reads_the_branch_range_not_the_single_commit(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """Pins the call site against the shared resolver.

    AC1 also passes if someone re-derives a range inline; AC2 also passes if the gate
    never sees anything. This asserts WHICH helper answers, so a silent revert to
    `_commit_changed_paths` — identical from outside on a non-merge HEAD — cannot
    pass. Monkeypatched by MODULE OBJECT, never the "lib.X" string (ADR-045).
    """
    from tools.verifiers import iterate_checks as ic

    work, _origin = git_origin_repo
    wt, head = _build_merge_head(
        work, make_worktree,
        branch_files={_SPEC: "spec\n"},
        main_files={"other.py": "main moved on\n"},
    )
    _seed_run(wt)
    _seed_event(wt, intent="feature", spec_impact="modify")

    seen: list[str] = []
    real = ic._iterate_changed_paths

    def _spy(project_root, commit):
        seen.append(commit)
        return real(project_root, commit)

    monkeypatch.setattr(ic, "_iterate_changed_paths", _spy)
    result = check_spec_impact_recorded(wt, _RUN_ID, head)

    assert seen == [head], (
        "the gate did not route its changed-path lookup through "
        f"_iterate_changed_paths (calls seen: {seen})"
    )
    assert result.ok is True
