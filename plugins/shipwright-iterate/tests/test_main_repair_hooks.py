"""The two places the repair procedure is wired into the iterate lifecycle.

@FR-01.19

AC-4 is prose, which means it is exactly the kind of thing that silently
disappears in a later edit. These tests are the drift protection: the hooks are
worthless if a reorganisation drops them, and nothing else would notice — the
skill would simply stop checking, and every iterate would go on building on
whatever base it was handed.

Both hooks exist for the same reason at different moments. At §B1b the worktree
has just been cut off the shared branch, so this run *inherits* its state. At
F11 the run is about to merge onto it, and a green branch armed onto a red base
puts the blame for the next red run on the wrong change.
"""

from __future__ import annotations

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "iterate"
SKILL = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
PROCEDURE = REFERENCES / "main-repair.md"
TOOL = "main_health.py"


def _skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def _f11() -> str:
    return (REFERENCES / "F11.md").read_text(encoding="utf-8")


def _procedure() -> str:
    return PROCEDURE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# AC-4 — the two hooks
# --------------------------------------------------------------------------

def test_the_start_hook_runs_right_after_the_worktree_is_cut():
    text = _skill()
    assert "### B1b." in text, "the start-of-iterate health hook is gone"
    assert text.index("### B1a.") < text.index("### B1b.") < text.index("### B2."), (
        "the health check belongs between cutting the worktree and loading "
        "context — it is about the base this run inherits"
    )
    assert TOOL in text.split("### B1b.")[1].split("### B2.")[0]


def test_the_f11_hook_runs_before_the_merge_is_armed():
    text = _f11()
    assert TOOL in text, "the pre-arm health hook is gone"
    assert text.index(TOOL) < text.index("gh pr merge"), (
        "checking after the arm buys nothing — an armed PR merges the moment "
        "its own checks pass"
    )


def test_both_hooks_point_at_the_procedure():
    assert "references/main-repair.md" in _skill()
    assert "main-repair" in _f11()


def test_the_procedure_is_linked_from_the_phase_index():
    """Kern only loads what it points at; an unlinked reference is dead."""
    assert "references/main-repair.md" in _skill().split("## CRITICAL")[0]


def test_unknown_is_never_treated_as_green_at_either_hook():
    """The one rule the whole check rests on. Both call sites must say it,
    because the exit code alone invites `if rc == 0 ... else fine`."""
    for text in (_skill(), _f11()):
        assert "unknown" in text.lower()
        assert "not green" in text.lower() or "never green" in text.lower()


# --------------------------------------------------------------------------
# AC-5 / AC-6 / AC-7 — the procedure says the things it must say
# --------------------------------------------------------------------------

def test_the_procedure_exists_and_is_within_the_runtime_prompt_budget():
    assert PROCEDURE.is_file()
    loc = len(_procedure().splitlines())
    assert loc <= 400, f"{loc} LOC — over the runtime-prompt budget"


def test_the_procedure_carries_every_step_of_the_repair():
    text = _procedure().lower()
    for phrase in ("read the failure", "candidate_partners", "full suite",
                   "fix(main)", "check_repair_safety.py"):
        assert phrase.lower() in text, f"the procedure never mentions {phrase!r}"


def test_the_claim_creates_a_ref_and_is_explicitly_not_a_push():
    """Two things, and the second is the one that was wrong.

    A query-only claim is no lock — two agents can both look before either has
    written anything. But neither is a `git push`: the procedure claims BEFORE
    doing the work, so both racers hold the same `HEAD` and push the same
    object, and git answers the second "Everything up-to-date" with exit 0.
    Only an operation that rejects an existing ref regardless of its target
    decides the race (external code review, round 1, high).
    """
    text = _procedure()
    assert "git/refs" in text, "the claim must be a create-ref call"
    assert "before doing the work" in text.lower()
    assert "already exists" in text.lower(), (
        "the procedure must say WHY create-ref is the lock, or the next editor "
        "will 'simplify' it back into a push"
    )
    assert "Not `git push`" in text


def test_the_repair_is_based_on_the_shared_branch_not_on_this_iterate():
    """At the F11 hook `HEAD` is this iterate's own finished branch. Claiming
    from it would put all of the current, unrelated work into what is supposed
    to be a small repair PR — and merge it as part of the repair (external code
    review, round 2, high)."""
    text = _procedure()
    assert 'rev-parse "origin/{default_branch}"' in text
    assert "never `HEAD`" in text


def test_the_procedure_requires_releasing_a_failed_claim():
    # Whitespace-normalised: the prose wraps, and a line break between "close"
    # and "the repair PR" is not a change of meaning.
    text = " ".join(_procedure().lower().split())
    assert "close the repair pr" in text
    assert "wedges the mechanism" in text


def test_releasing_a_claim_deletes_the_ref_and_not_only_the_pull_request():
    """A bare ref carries no timestamp, so a leftover branch is indistinguishable
    from a live claim and wedges that commit for every later repairer."""
    text = _procedure()
    assert "--delete-branch" in text
    assert "push origin --delete" in text


def test_the_procedure_forbids_weakening_a_test_in_words_as_well_as_in_code():
    text = _procedure().lower()
    assert "never \"adjust the test until it is green\"" in text or (
        "adjust the test until it is green" in text
    )
    assert "check_repair_safety.py" in text


def test_the_procedure_names_every_escalation_case():
    text = _procedure().lower()
    for case in ("weaken an assertion", "codeql", "bloat check",
                 "too_many_commits", "repeat_attempts"):
        assert case.lower() in text, f"escalation case missing: {case}"


def test_escalation_cards_are_idempotent_so_a_red_commit_is_filed_once():
    text = _procedure()
    assert "escalate.keys" in text
    assert "idempotency key" in text.lower()


def test_the_untrusted_excerpt_is_labelled_as_such_in_the_procedure():
    """A failing test can print anything, including something shaped like an
    instruction. The reader has to be told before they read it."""
    text = _procedure().lower()
    assert "untrusted" in text
    assert "never as instructions" in text or "not as instructions" in text


def test_the_deliberate_gaps_are_written_down_rather_than_left_implicit():
    text = _procedure().lower()
    assert "no scheduled run" in text
    assert "no auto-revert" in text
