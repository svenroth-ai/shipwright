#!/usr/bin/env python3
"""Which frozen compliance documents a refresh may rewrite, and how it judges itself.

Sibling to :mod:`lib.derived_snapshots`, which owns the other half of the same
subject: that module says what an iterate branch must NOT carry (so a conflict
cannot arise); this one says what a **release-time or on-demand refresh** may put
back (so the paths do not stay frozen). Pure decisions only — every git,
subprocess and filesystem effect lives in ``tools/compliance_refresh_produce.py``
(recompute and verify) and ``tools/refresh_compliance_docs.py`` (deliver),
mirroring the ``lib/churn_merge`` ⟷ ``tools/resolve_churn_conflicts`` split the
rest of the churn tooling uses.

Background: #480 stopped iterate branches from committing eleven regenerated
snapshots, because a branch-local derivation reads the *branch's* git history and
an event log missing every concurrently-merging branch — measured, ``main``'s
``change-history.md`` over-counted commits by 11 and cited a SHA that was never on
``main``. That left ``main``'s copies frozen. Weg B unfreezes them at the two
moments a human is already looking: the release PR, and an on-demand documents-only
PR. Decision and rejected alternative:
``.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md``.

**Eligibility is declared, never inferred.** An earlier draft derived the set as
"the churn registry minus the session-scoped paths". External review rejected that
and was right: whether a path is a function of the tree alone cannot be read off
its file extension, so a future run-scoped artifact would slide in silently — the
incorrect-default failure this whole change exists to remove. Every
:data:`~lib.derived_snapshots.DERIVED_SNAPSHOTS` path therefore carries an explicit
:data:`CLASSIFICATION` entry, and a new member with no entry fails a test rather
than defaulting either way.
"""

from __future__ import annotations

from lib.churn_merge import (
    CI_SECURITY_SUMMARY,
    COMPLIANCE_MDS,
    TEST_RESULTS,
    TEST_TRACEABILITY,
    THROUGHPUT_REPORT,
)
from lib.derived_snapshots import DERIVED_SNAPSHOTS

__all__ = [
    "CLASSIFICATION",
    "CONTENT_FLOOR_RATIO",
    "DERIVES_FROM_CI_HISTORY",
    "DERIVES_FROM_TREE",
    "EXCLUDED",
    "PRODUCER_TARGETS",
    "REFRESH_SET",
    "RUN_WRITTEN",
    "SESSION_SCOPED",
    "SUCCESS_OUTCOMES",
    "TREE_DERIVED",
    "branch_name",
    "content_floor_violation",
    "converged",
    "docs_commit_message",
    "failed_paths",
    "pr_body",
    "release_commit_note",
    "unclassified",
]

# --- classification ---------------------------------------------------------

#: A pure function of the tree — ``shipwright_events.jsonl`` +
#: ``.shipwright/triage.jsonl`` + git history + specs + tests. Byte-equality with a
#: fixpoint regeneration is claimable for these, and :func:`converged` claims it.
DERIVES_FROM_TREE = "derives_from_tree"

#: Derived, but **not from the tree**: ``refresh_ci_security`` reads the LATEST
#: COMPLETED ``security.yml`` run, which may belong to a different commit than the
#: one being refreshed. At release time that is fine in practice — a scan has just
#: run on the release PR — but the dependency is STATED rather than assumed away,
#: and a refresh never claims a fixpoint over this path. It is the parked Weg-A
#: iterate's H4 finding, kept deliberately: assuming all seven behave alike is the
#: mistake this constant exists to prevent.
DERIVES_FROM_CI_HISTORY = "derives_from_ci_history"

#: Embeds a ``run_id`` describing one specific run or session. The default branch
#: has no run, so a refresh could only invent one — and a plausible-looking default
#: is the recurring defect class in this codebase. Left frozen, which is honest.
SESSION_SCOPED = "session_scoped"

#: Not a derivation at all: a run WRITES it and nothing can recompute it
#: (``trg-ad29a709``, shipped as PR #502 — resetting it destroyed the F5 ledger).
#: Named explicitly so no acceptance criterion can appear to cover it by omission.
RUN_WRITTEN = "run_written"

#: Every :data:`~lib.derived_snapshots.DERIVED_SNAPSHOTS` path → its class.
CLASSIFICATION: dict[str, str] = {
    **{rel: DERIVES_FROM_TREE for rel in sorted(COMPLIANCE_MDS)},
    TEST_TRACEABILITY: DERIVES_FROM_TREE,
    ".shipwright/agent_docs/triage_inbox.md": DERIVES_FROM_TREE,
    CI_SECURITY_SUMMARY: DERIVES_FROM_CI_HISTORY,
    ".shipwright/agent_docs/build_dashboard.md": SESSION_SCOPED,
    ".shipwright/agent_docs/session_handoff.md": SESSION_SCOPED,
    TEST_RESULTS: RUN_WRITTEN,
    THROUGHPUT_REPORT: DERIVES_FROM_TREE,
}

#: **The set, pinned as a literal.** The compliance directory: five markdown
#: documents plus the two ``.json`` snapshots that live beside them.
#:
#: Written out rather than computed from a ``.shipwright/compliance/`` prefix so
#: widening it is an edit somebody has to make on purpose. The operator's decision
#: pinned this explicitly — "B's seven files is the compliance directory; pin it so
#: a later hand does not widen it to all eleven derived snapshots". A prefix test
#: would have let a new file dropped into that directory join the commit silently.
#: ``test_refresh_set_is_exactly_the_compliance_directory`` asserts the two
#: definitions agree, so the literal cannot fall behind either.
REFRESH_SET: frozenset[str] = frozenset(COMPLIANCE_MDS) | {
    TEST_TRACEABILITY,
    CI_SECURITY_SUMMARY,
}

#: The subset a fixpoint claim covers. ``ci-security.json`` is outside it by
#: construction: two passes can legitimately differ if a CI run completes between
#: them, so demanding byte-equality there would turn an honest refresh into a
#: flake — and claiming it converged would be the same overclaim under the
#: opposite sign.
TREE_DERIVED: frozenset[str] = frozenset(
    rel for rel in REFRESH_SET if CLASSIFICATION.get(rel) == DERIVES_FROM_TREE
)

#: Every derived path NOT in :data:`REFRESH_SET`, each with the reason it is out —
#: a reason per path, not a class-level rule, since an exclusion nobody wrote down
#: reads as an oversight the next time somebody audits the set.
EXCLUDED: dict[str, str] = {
    ".shipwright/agent_docs/build_dashboard.md":
        "session_scoped — embeds one session's run id; the default branch has no run, "
        "so a refresh could only invent one",
    ".shipwright/agent_docs/session_handoff.md":
        "session_scoped — same as build_dashboard.md: per-session, meaningless on the "
        "default branch",
    ".shipwright/agent_docs/triage_inbox.md":
        "tree-derived and refreshable, but OUTSIDE the compliance directory and not "
        "recomputed by the release phase (PHASE_REPORTS['changelog'] does not name it). "
        "Excluded by the operator's scope pin, NOT by a classification claim — widening "
        "the set to include it is a decision, not a fix",
    TEST_RESULTS:
        "run_written — a run writes it and nothing can recompute it (trg-ad29a709, "
        "PR #502). Regenerating it would destroy the F5 ledger, not refresh a view",
    THROUGHPUT_REPORT: "tree-derived, but by its OWN producer — same scope pin as triage_inbox.md",
}

#: What the producer is asked to regenerate. ``regenerate_tracked_snapshots``
#: expands any :data:`~lib.churn_merge.COMPLIANCE_MDS` member into one
#: ``_update_compliance`` call that rewrites all five MDs **and** both ``.json``
#: snapshots, so naming the MDs asks for exactly :data:`REFRESH_SET` and nothing
#: else. Asking for the ``.json`` paths as well would be a no-op that reads as if
#: they were separately producible.
PRODUCER_TARGETS: frozenset[str] = frozenset(COMPLIANCE_MDS)


def unclassified() -> frozenset[str]:
    """Derived snapshots with no class — a test failure, never a silent default."""
    return frozenset(DERIVED_SNAPSHOTS) - frozenset(CLASSIFICATION)


# --- judging a pass ---------------------------------------------------------

#: What a producer leg says when it SUCCEEDED. Everything else is a failure.
#:
#: Inverted deliberately — matching the literal ``"error"`` is what makes this
#: class of bug invisible. ``_update_compliance`` swallows a non-zero exit, its own
#: 30-second timeout and every exception, returning ``[]``;
#: ``regenerate_tracked_snapshots`` then marks paths as errored WITHOUT writing
#: anything. An all-error pass therefore leaves the digest untouched, converges
#: immediately, and reads as a clean fixpoint: green, frozen forever, no card.
#: A closed SUCCESS set fails closed instead — a new or reworded producer status is
#: a failure until somebody adds it here on purpose.
SUCCESS_OUTCOMES: frozenset[str] = frozenset({"regenerated", "copied", "seeded"})


def failed_paths(outcomes: dict[str, str] | None) -> list[str]:
    """Paths whose generator leg did not report success. Sorted."""
    return sorted(
        rel for rel, outcome in (outcomes or {}).items()
        if outcome not in SUCCESS_OUTCOMES
    )


def converged(previous: dict[str, str], current: dict[str, str]) -> bool:
    """Two consecutive passes produced identical content for every tree-derived path.

    Compared over :data:`TREE_DERIVED` only. A path that STOPPED being emitted is
    absent from the digest, and absent ≠ unchanged — so the dicts are compared
    whole rather than key-by-key over the intersection.
    """
    return {k: v for k, v in previous.items() if k in TREE_DERIVED} == {
        k: v for k, v in current.items() if k in TREE_DERIVED
    }


#: A regenerated document may not fall below this fraction of its committed size.
#: ``collect_git_history`` returns ``[]`` on its 30-second timeout, which renders a
#: change-history document with its headers and no rows — a plausible-looking file
#: that converges perfectly well and would replace #480's "wrong by 11 commits"
#: with "zero commits". Failing closed leaves the documents frozen, which is the
#: safe direction: a refused refresh is visible, a silently emptied evidence
#: document is not.
CONTENT_FLOOR_RATIO = 0.5


def content_floor_violation(
    before: bytes | None, after: bytes | None, *, allow_shrink: bool = False,
) -> str | None:
    """Why ``after`` fails the floor against the committed ``before``, or ``None``.

    Two floors. A path must stay non-empty when the committed copy had content —
    that catches a generator that produced nothing at all. It must additionally keep
    at least :data:`CONTENT_FLOOR_RATIO` of its committed size, which catches the
    subtler and likelier case: a collector that timed out, returned ``[]`` and
    rendered a well-formed document with no rows in it.

    Judged against the COMMITTED copy, never against the previous pass: the failure
    this guards converges happily, so consecutive passes agreeing says nothing
    about it.

    ``before`` absent or blank means there is nothing to fall below — a path the
    committed tree does not carry cannot have lost content.

    ``allow_shrink`` waives the RATIO floor only. A large deletion — a dropped
    dependency, a retired feature, a shrinking backlog — can legitimately halve a
    document, and a floor with no override would make that a permanently blocked
    release (external review, gemini/medium). The empty floor is NOT waivable: no
    legitimate change turns a document with content into a blank one, and that is
    the shape the timeout produces. The caller records that the override was used
    and which paths it covered, so a waived floor is visible rather than assumed.
    """
    if not before or not before.strip():
        return None
    if not after or not after.strip():
        return "regenerated empty while the committed copy has content"
    if not allow_shrink and len(after) < len(before) * CONTENT_FLOOR_RATIO:
        return (
            f"regenerated to {len(after)} bytes, under "
            f"{CONTENT_FLOOR_RATIO:.0%} of the committed {len(before)} "
            "(--allow-shrink overrides this deliberately)"
        )
    return None


# --- wording ----------------------------------------------------------------

#: Keeps a branch name unique per base without a clock — two refreshes at the same
#: base produce the same branch, which is the honest outcome (there is nothing new
#: to say).
def branch_name(base_sha: str) -> str:
    """The on-demand refresh branch. ``chore/`` so it reads as maintenance."""
    return f"chore/compliance-docs-{base_sha[:12]}"


def docs_commit_message(base_sha: str, run_id: str) -> str:
    """The on-demand refresh commit. ``chore`` is inside B7's default non-functional
    exclusion, so this is expected maintenance rather than drift.

    **The ``Run-ID:`` trailer is load-bearing, not decoration.**
    ``audit_staleness.find_snapshot_commit`` recognises a compliance snapshot by
    EITHER a ``Run-ID:`` trailer or a ``chore(release)`` subject, and its docstring
    says verbatim that a manual ``chore(compliance)`` regen is *deliberately NOT
    recognised* — that is the hand-edit case Group E exists to catch. So this
    subject, alone, is the one string the audit refuses. Without the trailer the
    docs-only PR merges, the next audit skips this commit, falls back to the
    previous release, and reports the **freshest possible evidence as stale**
    (Stage-2 code review, high). The trailer is the honest fix rather than widening
    that grep, which would re-open the hand-edit case.
    """
    return (
        f"chore(compliance): refresh evidence documents as of {base_sha[:12]}\n\n"
        "Recomputed from the tree at the named commit and checked in through a "
        "documents-only pull request. These documents are derived: every line is "
        "recomputable from shipwright_events.jsonl, .shipwright/triage.jsonl and "
        f"git history, all of which already ship.\n\nRun-ID: {run_id}\n"
    )


def release_commit_note(version: str) -> str:
    """The line the release step prints once the seven paths are staged."""
    return (
        f"compliance evidence staged for {version} — the seven documents ride the "
        "release commit and are reviewed in the release PR"
    )


def pr_body(base_sha: str, staged: list[str], ci_security_note: str) -> str:
    """Body for the documents-only pull request."""
    files = "\n".join(f"- `{rel}`" for rel in sorted(staged)) or "- _(none differed)_"
    return (
        "## Compliance evidence refresh\n\n"
        f"Recomputed from `{base_sha[:12]}` and nothing else. These documents are "
        "derived — every line is recomputable from the event log, the triage backlog "
        "and git history, all of which already ship in this repository.\n\n"
        "They are refreshed at each release and on demand, **not continuously**. "
        "This is the on-demand path.\n\n"
        f"### Changed\n\n{files}\n\n"
        f"### `ci-security.json`\n\n{ci_security_note}\n"
    )
