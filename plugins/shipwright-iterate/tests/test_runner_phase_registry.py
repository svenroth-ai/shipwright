"""The runner's finalization phase list vs SKILL.md's — drift protection.

Split from ``test_sub_iterate_runner_finalization.py`` (bloat: 313 lines
against a 300-line limit).

The runner RE-ENUMERATES the finalization phases instead of deriving them, and
that duplicate list silently fell FOUR phases behind: F0.5, F2
(``architecture.md``), F3a and F5 were absent, while the label ``F2`` was reused
for Browser Verify — a collision that hid the omission. Per SKILL.md Step 6's
registry-driven SSoT meta-test rule, BOTH directions are pinned:

  forward  — every phase the runner must carry is actually in the contract;
  reverse  — every phase SKILL.md defines is CLASSIFIED here as either required
             or deliberately excluded, so a phase cannot be added upstream
             without this contract making a decision.

Each guard is mutation-probed: delete the bullet (or its subject) and it fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DOC = PLUGIN_ROOT / "agents" / "sub-iterate-runner.md"
SKILL_DOC = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"


def _load_runner_text() -> str:
    return RUNNER_DOC.read_text(encoding="utf-8")


#: Phases a campaign sub-iterate runs exactly as a standalone iterate does.
RUNNER_REQUIRED = {
    "F0", "F0.5", "F1", "F2", "F3", "F3a", "F4", "F5", "F5b", "F5c", "F6",
}

#: Phases deliberately NOT run by the runner. A reason each — an unexplained
#: exclusion is how the missing phases survived for as long as they did, and a
#: WRONG reason is no better: F5 was first excluded here as "a derived snapshot
#: F11 rewinds to HEAD", which trg-ad29a709 had already closed
#: (`RESTORABLE_SNAPSHOTS = DERIVED_SNAPSHOTS - {TEST_RESULTS}`). F5 is in fact
#: REQUIRED — `check_test_completeness_ledger` reads the ledger from
#: `iterate_latest`, which F5 is the producer of.
RUNNER_EXCLUDED = {
    "F6.5": "attaches a commit to an out-of-band event; the runner commits in "
            "the same tree, so F6 already ships the event",
    "F7": "legacy / replay event recording, not the normal flow",
    "F7b": "seals an out-of-band F7 append; idempotent noop here",
    "F11": "SPLIT, not excluded: the runner does F11's branch-current + push "
           "(its Step 5) and self-runs the F11 verifier at F6-verify, while "
           "the orchestrator owns review + merge (campaign-mode 3f-bis + 3g). "
           "No actor is assigned `gh pr create`, though 3g reads the PR — a "
           "pre-existing hole recorded here rather than hidden behind a tidy "
           "'excluded'",
    "F12": "release prompt — the campaign loop does it once, at the end",
    "F5a": "UNIMPLEMENTABLE AS WRITTEN: SKILL.md's MANDATORY prose names F5a, "
           "but it has no index row, no heading and no references/F5a.md, so "
           "there is nothing for the runner to run. Classified rather than "
           "left invisible; correcting SKILL.md is a separate change "
           "(iterate spec, residual 6)",
}


def _skill_phases() -> set[str]:
    """Every F-phase SKILL.md names: index table, F0/F0.5 headings, AND the
    MANDATORY prose.

    Reading only tables and headings made the registry-reader look somewhere
    other than where the mandatory CLAIM lives: SKILL.md declares
    "F0-F11 (incl. F3a, F5a, F5b, F5c) are MANDATORY" in prose, and `F5a` has no
    row, no heading and no `references/F5a.md`. It was therefore mandatory and
    invisible at the same time, and every test here passed (external review).
    """
    text = SKILL_DOC.read_text(encoding="utf-8")
    rows = re.findall(r"(?m)^\|\s*(F[0-9][0-9a-z.]*)\s*\|", text)
    heads = re.findall(r"(?m)^###\s+(F[0-9][0-9a-z.]*)\s*[:\s]", text)
    prose = re.findall(r"\(incl\.\s*([^)]*)\)", text)
    inline = {tok for chunk in prose
              for tok in re.findall(r"F[0-9][0-9a-z.]*", chunk)}
    return set(rows) | set(heads) | inline


def _runner_phases() -> set[str]:
    """The phases Step 4 actually LISTS — its bullet heads, nothing else.

    A token scan over the whole prompt does not work, and the way it fails is
    the failure being guarded against. `references/F0.5.md`, `references/F2.md`
    and `references/F3.md` each contain their own phase name, and the section
    heading contains "F0–F6" — so five of the ten required phases stayed
    "covered" with their bullet deleted (Stage-2 review). Only the bullet head
    proves the runner is told to RUN the phase rather than merely to read about
    it.
    """
    text = _load_runner_text()
    start = re.search(r"(?m)^###\s+Step 4:.*$", text)
    assert start, "the runner contract must carry a `### Step 4:` section"
    body = text[start.end():]
    end = re.search(r"(?m)^###\s", body)
    body = body[:end.start()] if end else body
    return set(re.findall(r"(?m)^\s*-\s*\*\*(F[0-9][0-9a-z.]*)", body))


@pytest.mark.covers("FR-01.11")
def test_runner_carries_every_required_finalization_phase():
    """Forward: a phase omitted here is omitted by every sub-iterate of every
    campaign, and no later phase fills it."""
    missing = sorted(RUNNER_REQUIRED - _runner_phases())
    assert not missing, (
        f"sub-iterate-runner.md no longer names {missing}. A campaign "
        "sub-iterate would then skip it while a standalone iterate runs it — "
        "the exact divergence iterate-2026-07-31-it7b-campaign-cascade closed."
    )


@pytest.mark.covers("FR-01.11")
def test_every_skill_phase_is_classified_required_or_excluded():
    """Reverse: SKILL.md is the registry. A phase added there must be either
    adopted by the runner or excluded WITH a reason — never silently ignored,
    which is how F0.5 / F2 / F3a went missing."""
    unclassified = sorted(
        _skill_phases() - RUNNER_REQUIRED - set(RUNNER_EXCLUDED)
    )
    assert not unclassified, (
        f"SKILL.md defines {unclassified}, which this contract has not "
        "classified. Add it to RUNNER_REQUIRED (and to the runner's Step 4) "
        "or to RUNNER_EXCLUDED with the reason it does not apply."
    )


@pytest.mark.covers("FR-01.11")
def test_required_and_excluded_sets_do_not_overlap_or_invent_phases():
    """The classification must describe SKILL.md, not a phase list of its own —
    otherwise a renamed phase would leave a stale entry looking healthy."""
    overlap = sorted(RUNNER_REQUIRED & set(RUNNER_EXCLUDED))
    assert not overlap, f"{overlap} is both required and excluded"

    invented = sorted((RUNNER_REQUIRED | set(RUNNER_EXCLUDED)) - _skill_phases())
    assert not invented, (
        f"{invented} is classified here but SKILL.md no longer defines it — "
        "the phase was renamed or removed upstream and this list is stale."
    )


@pytest.mark.covers("FR-01.11")
def test_f2_is_bound_to_architecture_not_to_browser_verify():
    """A phase must be pinned to its SUBJECT, not merely to its number.

    Until 2026-07-31 this contract labelled Browser Verify `F2`. The label was
    therefore present, and a set-membership test over F-tokens reported F2 as
    covered while `architecture.md` was never written by any sub-iterate.
    Measured against the pre-change file, the forward test above reports F0.5,
    F3a and F5 — it does NOT catch F2. This test is that gap's guard.
    """
    text = _load_runner_text()
    assert "architecture.md" in text, (
        "F2 must name architecture.md — a bare `F2` label is satisfied by "
        "anything, including the Browser Verify step that used to occupy it"
    )
    browser_lines = [ln for ln in text.splitlines() if "Browser Verify" in ln]
    assert browser_lines, "the Browser Verify step must still exist"
    assert not any(re.search(r"\bF2\b", ln) for ln in browser_lines), (
        "Browser Verify must not carry an F-number: it is not an F-phase, and "
        "reusing `F2` is what hid architecture.md's absence"
    )


#: Phases SKILL.md declares mandatory in PROSE (its "CRITICAL: F0-F11 (incl.
#: F3a, F5a, F5b, F5c) are MANDATORY" line). These may never be moved into
#: RUNNER_EXCLUDED — without this, the drift protection is circular: deleting a
#: bullet and re-classifying the phase with any plausible-sounding reason leaves
#: every other test in this module green (Stage-3 doubt).
NON_EXCLUDABLE = {"F0", "F0.5", "F3", "F3a", "F4", "F5", "F5b", "F5c", "F6"}

#: Each required phase must name its SUBJECT, not merely its number. `F2` was
#: "present" for years while pointing at Browser Verify, and `F4` told every
#: sub-iterate to append to CHANGELOG.md — which `references/F4.md` forbids in
#: as many words. A bullet head is not coverage.
PHASE_SUBJECT = {
    "F0.5": "F0.5.md",
    "F2": "architecture.md",
    "F3": "write_decision_drop.py",
    "F3a": "reflection.md",
    "F4": "write_changelog_drop.py",
    "F5": "F5.md",
    "F5b": "finalize_iterate.py",
    "F5c": "append_iterate_entry.py",
}


@pytest.mark.covers("FR-01.11")
def test_a_mandatory_phase_cannot_be_reclassified_as_excluded():
    """Closes the circularity: RUNNER_REQUIRED is hand-written, so without this
    a phase can be deleted from the contract and 'excluded' in the same edit."""
    smuggled = sorted(NON_EXCLUDABLE & set(RUNNER_EXCLUDED))
    assert not smuggled, (
        f"{smuggled} is declared MANDATORY by SKILL.md but excluded here. A "
        "mandatory phase is not excludable by editing this list."
    )
    dropped = sorted(NON_EXCLUDABLE - RUNNER_REQUIRED)
    assert not dropped, (
        f"{dropped} was removed from RUNNER_REQUIRED. SKILL.md declares it "
        "mandatory, so the runner must carry it."
    )


@pytest.mark.covers("FR-01.11")
def test_every_excluded_phase_states_a_reason():
    """`"F0.5": ""` would otherwise pass the classification test — an empty
    reason is the same silent omission with extra steps."""
    for phase, reason in RUNNER_EXCLUDED.items():
        assert len(reason.strip()) >= 20, (
            f"{phase} is excluded without a checkable reason: {reason!r}"
        )


@pytest.mark.covers("FR-01.11")
def test_each_required_phase_names_its_subject_not_just_its_number():
    """Generalises the F2 guard to every phase with a known subject.

    F2 was satisfied by a Browser Verify bullet for years, and F4's bullet
    instructed the opposite of `references/F4.md`. The label being present is
    what made both invisible.
    """
    text = _load_runner_text()
    start = re.search(r"(?m)^###\s+Step 4:.*$", text)
    body = text[start.end():]
    end = re.search(r"(?m)^###\s", body)
    body = body[:end.start()] if end else body

    bullets = re.split(r"(?m)^\s*-\s+(?=\*\*)", body)
    for phase, subject in PHASE_SUBJECT.items():
        owned = [b for b in bullets if b.startswith(f"**{phase}:")
                 or b.startswith(f"**{phase} ")]
        assert owned, f"Step 4 has no bullet for {phase}"
        assert any(subject in b for b in owned), (
            f"the {phase} bullet never names {subject!r}. A phase number "
            "without its subject is how F2 pointed at Browser Verify and F4 "
            "told every sub-iterate to do what references/F4.md forbids."
        )


@pytest.mark.covers("FR-01.11")
def test_the_runner_names_no_phase_skill_md_does_not_define():
    """Reverse direction over the DOCUMENT, which was missing.

    `test_required_and_excluded_sets_do_not_overlap_or_invent_phases` compares
    the two hand-maintained Python sets against SKILL.md, so an invented bullet
    in the runner's Step 4 — `**F9:**` — failed nothing (external review). The
    contract itself has to be the subject.
    """
    invented = sorted(_runner_phases() - _skill_phases())
    assert not invented, (
        f"the runner's Step 4 names {invented}, which SKILL.md does not "
        "define. Either add it upstream or drop the bullet — a phase that "
        "exists only in the runner is drift in the other direction."
    )


@pytest.mark.covers("FR-01.11")
def test_the_runner_bullets_match_the_required_classification():
    """The forward test asks whether each REQUIRED phase is present; this asks
    the converse of the same document — that every phase the runner actually
    lists is one it is supposed to run, so a bullet cannot be added for a phase
    this contract classified as excluded."""
    listed = _runner_phases()
    excluded_but_listed = sorted(listed & set(RUNNER_EXCLUDED))
    assert not excluded_but_listed, (
        f"Step 4 lists {excluded_but_listed}, which this contract classifies "
        "as NOT run by the runner. Move it to RUNNER_REQUIRED or drop the "
        "bullet — the list and the classification must agree."
    )
