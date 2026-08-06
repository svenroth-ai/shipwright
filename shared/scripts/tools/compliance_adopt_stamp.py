#!/usr/bin/env python3
"""Onboarding's delivery of the evidence documents — the third fixed point.

Sibling to :mod:`tools.compliance_refresh_produce` (recompute and verify) and
:mod:`tools.compliance_delivery` (the on-demand PR protocol), under the same
split those two follow: :mod:`tools.refresh_compliance_docs` stays the thin
deliverer and CLI, and each delivery path's substance lives beside it.

**What makes this path different from the other two.** ``--stage`` and ``--pr``
describe *now*, so they may resolve ``HEAD`` themselves. This one describes *the
commit onboarding read* — a fact only the caller holds — and everything here is a
consequence of that single difference: the base is supplied rather than observed,
every way of not knowing it collapses to the same answer, and ``HEAD`` is never
consulted.

Decision and rejected alternative:
``.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# UNCONDITIONAL, exactly as every sibling `compliance_*` module does it. A
# `if not in sys.path` guard skips the insert whenever the path is already
# present but sitting BEHIND a directory carrying its own lib/tools package —
# the collision that reads green locally and red in CI (ADR-045). Without this
# the module resolves only because its importer happened to insert first, which
# makes the protection importer-dependent.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # shared/scripts

from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from source_state import safe_commit  # noqa: E402
from tools.compliance_git import write_back  # noqa: E402
from tools.compliance_provenance import stamp_fixed_point  # noqa: E402
from tools.compliance_refresh_produce import git  # noqa: E402

#: A full object id. Anything shorter is refused rather than resolved — see
#: :func:`resolve_adopted_base`.
_FULL_OID_LEN = 40

__all__ = ["deliver_stamp_adopted", "resolve_adopted_base", "stampable_paths"]


def stampable_paths() -> frozenset[str]:
    """The refresh set's members that carry a banner at all — the ``.md`` half.

    Derived from :data:`~lib.compliance_refresh.REFRESH_SET` rather than from
    ``COMPLIANCE_MDS``, which is the same five today: correctness here is defined
    over the refresh set, and consuming a second list would let production code
    stamp a divergent one until the drift test next ran (external review R2).

    The two ``.json`` members are out **by design, not by omission** —
    ``ci-security`` states its provenance in its own ``source``/``scan_date``
    fields, and ``test-traceability`` has a schema with contract tests that is not
    this change's to extend. So "seven documents, five stamped" is the whole set.
    """
    return frozenset(rel for rel in REFRESH_SET if rel.endswith(".md"))


def resolve_adopted_base(root: Path, raw: str | None) -> str | None:
    """The commit onboarding read, or ``None``. **Never this process's ``HEAD``.**

    Every way of not knowing the answer returns ``None``: absent, malformed, the
    literal ``"HEAD"`` that ``event_seeder`` writes as its own fallback, or a
    well-formed sha naming no object in this repository.

    An earlier draft split those: absent fell back to ``HEAD``, malformed did not.
    The asymmetry had no justification and reintroduced the timing failure the
    recorded value exists to remove — at Step H, ``HEAD`` equals the recorded
    commit only if nothing has committed since, which resume, retry and operator
    intervention all break (external review R3, high).

    Lexical validation alone is not enough: :func:`~source_state.safe_commit`
    accepts any 7-40 hex string, including one naming no object here. So the value
    must also *resolve*, and what comes back is what git resolved.

    **Abbreviations are refused, not resolved.** For a 7-39 hex string git tries
    ``dwim_ref`` FIRST and only falls back to short-oid lookup if no ref matched —
    so in a repository carrying a branch or tag literally named ``deadbeef``,
    ``--base deadbeef`` would stamp that branch's tip: a real, plausible, wrong
    commit, which is the one outcome this whole path exists to prevent (Stage-2
    code review). Only a full 40-hex id is taken as an object regardless of refs.
    The caller always has one — ``event_seeder`` records ``commit_at_adoption``
    full-length — so nothing legitimate is lost, and a short value degrades to
    ``no_base``, which is unstamped-and-honest rather than stamped-and-wrong.
    """
    base = safe_commit(raw)
    # `safe_commit` validates the TRIMMED value, so interpolating `raw` would send
    # git a padded argument that fails to resolve — silently degrading a perfectly
    # establishable commit to `no_base` (Stage-2 code review).
    if base is None or len(base) != _FULL_OID_LEN:
        return None
    resolved = git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    if resolved.returncode != 0:
        return None
    return safe_commit((resolved.stdout or "").strip())


def deliver_stamp_adopted(root: Path, raw_base: str | None) -> dict:
    """Stamp the seeded evidence with the commit onboarding read.

    Runs at Step H immediately before the adoption commit, because anything that
    regenerates in between — a phase-completion hook, a second session — would
    substitute unstamped bytes while this still reported success.

    **Validates before it writes.** A partial stamp that had already touched the
    tree would abort adoption with the repository mutated: no bad commit, but a
    dirty worktree that then fouls retry, the clean-tree preconditions elsewhere
    in this same change, and the operator's recovery (external review R3). So the
    payload is stamped in memory, the set is checked, and only a complete result
    reaches disk.
    """
    # PRESENCE-FILTERED, like both sibling deliveries, and computed FIRST — before
    # the base is even resolved. An absent document and a bannerless one are
    # different facts and must not share a status: absence is Step F's business
    # (its seeder is documented non-blocking), while a document that is present
    # and unstampable is this tool's (Stage-1 spec review).
    # COMPLETENESS FIRST, and before the base is even resolved. Both refusals
    # below are fatal, and they precede everything because an incomplete set is
    # wrong whatever the base turns out to be. Ordered any other way, `no_base`
    # (which is legitimately non-fatal) returns exit 0 while documents are
    # missing, Step H continues, `--verify-commit` is skipped on `no_base` by
    # design, and an incomplete evidence set ships green — the same shape as the
    # all-absent case, one notch subtler (external code review, medium).
    #
    # Absence gets its OWN status rather than being folded into `partial`: they
    # are different diagnoses (Step F produced nothing here vs produced something
    # unstampable), and `partial`'s wording is simply untrue of a file that is not
    # there (Stage-1 spec review).
    expected = stampable_paths()
    present = frozenset(rel for rel in expected if (root / rel).is_file())
    absent = sorted(expected - present)
    if not present:
        return {"status": "no_documents", "base": None, "stamped": [],
                "absent": absent, "detail": (
                    "none of the evidence documents exist — re-run Step F "
                    "before committing")}
    if absent:
        return {"status": "incomplete_set", "base": None, "stamped": [],
                "absent": absent, "detail": (
                    "these evidence documents were never produced, so the set is "
                    "incomplete — re-run Step F before committing; "
                    "`--verify-commit` presence-filters and would call what "
                    "remains `verified`")}
    base = resolve_adopted_base(root, raw_base)
    if base is None:
        # Not an error, and reachable only with the set already COMPLETE. A
        # repository with no commits is a legitimate thing to onboard; the banner
        # simply says nothing rather than something plausible.
        return {"status": "no_base", "base": None, "stamped": [],
                "absent": absent, "detail": (
                    "no usable commit was supplied, so the evidence names none — "
                    "onboarding continues and the documents carry their run id "
                    "only")}
    payload = {rel: (root / rel).read_bytes() for rel in sorted(present)}
    stamped_payload, stamped = stamp_fixed_point(payload, base, None)
    unstampable = sorted(present - set(stamped))
    if unstampable:
        # `stamp_fixed_point` skips a document carrying no `Source-State:` line
        # and omits it from its return value without comment. Reporting `ok` here
        # would ship a half-stamped evidence set under a green status — the same
        # shape as the release-path defect `verify_commit` exists to catch.
        return {"status": "partial", "base": base, "stamped": sorted(stamped),
                "missing": unstampable, "absent": absent, "detail": (
                    "these are present but carry no Source-State banner to "
                    "rewrite, so the set cannot be stamped completely; "
                    "nothing was written")}
    try:
        write_back(root, stamped_payload)
    except OSError as exc:
        # `write_back` writes the set in a loop with no rollback, so a raise on
        # the fourth file leaves three stamped and two not — a half-stamped tree
        # under a claim of "only a complete result reaches disk". Not exotic on
        # Windows: the sibling `restore_to_head` documents a file held open by an
        # editor, and an index.lock race with a hook, as ordinary there. The
        # originals are still in `payload`, so put them back (Stage-2 code review).
        restored, unrestored = [], []
        for rel, original in sorted(payload.items()):
            try:
                (root / rel).write_bytes(original)
                restored.append(rel)
            except OSError:
                unrestored.append(rel)
        return {"status": "write_failed", "base": base, "stamped": [],
                "restored": restored, "unrestored": unrestored,
                "detail": f"{type(exc).__name__}: {exc}"[:300]}
    # `absent` is necessarily empty here — the completeness gate above is fatal —
    # so `ok` means exactly "the whole set, stamped", with no qualifier a caller
    # has to remember to check.
    return {"status": "ok", "base": base, "stamped": sorted(stamped),
            # The number of documents that SHOULD exist, not the number that did.
            # In this branch `present == set(stamped)` by construction, so
            # `len(present)` was a guarantee that could not fail (Stage-2 review).
            "absent": absent, "expected": len(expected)}
