"""THE KEYSTONE GATE's post-merge DETECTIVE arm (ruling Q5,
``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md`` §4/§7/§8;
full design: ``.shipwright/planning/iterate/2026-09-10-keystone-detective-arm.md``).

The preventive gate (``check_keystone_ac_gate.py``) answers *"did test T run
green in THIS run?"* — same process tree, same job, no commit boundary to
forge across, so it trusts its own same-run local regeneration of the
traceability manifest. It also runs on ``pull_request`` only (design §5.7), so
a direct push to the default branch bypasses it entirely (design §7).

This module answers a different question: *"did a commit already on the
default branch's tip genuinely satisfy the gate, using evidence bound to a
real trunk CI run?"* — Q2 in ``ci_provenance.py``'s own docstring, the one the
preventive gate explicitly does NOT answer. It composes with the two existing
cross-commit unforgeability predicates (``resolve_ci_verification``,
``resolve_execution_evidence`` — built for a different consumer, P3.5's per-FR
layer promotion) rather than reusing the preventive gate's own same-run
producer, and it reuses ``evaluate_keystone``/``ac_change_set``/
``read_base_manifest`` UNEDITED: none of those three care where the manifest
dicts they are handed came from, only what is in them.

**This module holds the ORCHESTRATION half only** (``classify_commit``, the
seven outcome constants, ``DetectiveResult``). The PURE, no-I/O half
(``build_verified_manifest``) lives in ``_keystone_detective_manifest.py``
and is re-exported here unedited (code review, low — the combined module
crossed the 300-LOC guideline).

**Advisory only, deliberately not a CI gate** (external Architecture Review,
2026-09-10, both reviewers `reject`ed a standalone CLI/exit-code contract as
premature — see the design doc §3.5). ``classify_commit`` is a plain,
importable function; there is no script entry point, no argument parser, no
exit-code contract, and nothing in ``ci.yml`` references this module. A future
consumer (a compliance-audit producer, a scheduled job, a REPL) is a separate,
later decision.

**Precondition, measured 2026-09-10:** ``origin/main``'s own tip still carries
the pre-existing structural manifest drift the P3.6 design measured in its
own §2.3, so ``resolve_ci_verification`` reports ``not_verified`` for every
real commit in this repo today. This module's correctness therefore rests on
its unit tests against mocked resolver outputs — the same posture the
preventive gate's own pure core (``_keystone_core.py``) has always used for
its own zero-population findings — not on a live demonstration of
``gate_violated``/``gate_confirmed_clean``, which cannot exist yet.

The outcome is one of SEVEN named, mutually exclusive constants (design §4.2):

**Inherited cost, not a defect here (code review, low):** on the ``verified``
path, ``resolve_execution_evidence`` internally calls ``resolve_ci_verification``
a second time to get its own ``run_id`` — so a commit reaching
``GATE_VIOLATED``/``GATE_CONFIRMED_CLEAN`` costs two GitHub Actions API
round-trips for the same verification question, not one. This is
``ci_execution_evidence.py``'s own existing behavior, left unedited per this
module's scope (§3.5) — a future consumer batching many commits should budget
for it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from ci_execution_evidence import resolve_execution_evidence  # noqa: E402
from ci_provenance import resolve_ci_verification  # noqa: E402

from ._keystone_ac_digest import ac_change_set  # noqa: E402
from ._keystone_base_manifest import (  # noqa: E402  (re-exported: one import site for callers)
    ReadError,
    read_base_manifest,
)
from ._keystone_core import (  # noqa: E402  (re-exported: one import site for callers)
    EmptyLinkWalk,
    KeystoneVerdict,
    evaluate_keystone,
)
from ._keystone_detective_manifest import build_verified_manifest  # noqa: E402,F401  (re-exported)
from .git_helpers import _GIT_TIMEOUT_SECONDS, _run_git  # noqa: E402

#: `resolve_ci_verification` found no qualifying push-event CI run for `commit`
#: at all -- no evidence exists to judge it by. Never a violation and never a
#: pass. **Not the expected outcome for an ordinary PR-merged commit on THIS
#: repo** (external plan review, both reviewers, corrected 2026-09-10): this
#: repo's `ci.yml` triggers on `push: branches: [main]`, so the merge commit
#: GitHub creates for an ordinary PR merge DOES get its own push-event run on
#: `main`, distinct from the `pull_request`-event run CI already ran on it
#: before merge. `NO_QUALIFYING_RUN` is therefore the genuine edge case here --
#: an Actions outage, a workflow disabled at merge time, GitHub API lag before
#: the run is queryable, or a commit predating this `ci.yml`'s push trigger --
#: not the steady state. The dominant real-world outcome today (design §2's
#: precondition) is `RUN_NOT_VERIFIED`: the push run exists and its overall
#: conclusion is `success`, but its structural drift-check step did not
#: confirm a clean manifest.
NO_QUALIFYING_RUN = "no_qualifying_run"
#: A qualifying trunk run for `commit` exists, but that run's OWN structural
#: drift check did not confirm a clean manifest -- the run genuinely did not
#: pass what this control needs. Distinct from `NO_QUALIFYING_RUN`: a run DID
#: happen, it just didn't confirm. Today's steady state for every real commit
#: in this repo (see the module docstring's Precondition paragraph).
RUN_NOT_VERIFIED = "run_not_verified"
#: The query to GitHub itself could not complete (timeout, `gh` missing,
#: malformed response). Never evidence of anything about `commit` -- must
#: never be treated as clean or as a violation, and this module never
#: proceeds to ask the execution-evidence question from this state.
VERIFICATION_QUERY_FAILED = "verification_query_failed"
#: Structure was confirmed, but no per-test execution-evidence artifact
#: exists for the verified run (aged out of retention, or predates this
#: mechanism) -- greenness cannot be recomputed. Neither a violation
#: (structure was fine) nor a pass (greenness is genuinely unknown).
EXECUTION_EVIDENCE_UNAVAILABLE = "execution_evidence_unavailable"
#: The artifact query/download/content-binding pipeline itself failed. Same
#: "could not determine" discipline as `VERIFICATION_QUERY_FAILED`.
EXECUTION_EVIDENCE_QUERY_FAILED = "execution_evidence_query_failed"
#: Execution evidence was confirmed AND the recomputed verdict carries at
#: least one HARD finding: `commit` reached the default branch without a
#: changed AC's bound test(s) being green, per CI-VERIFIED evidence -- the
#: shape a direct push (or any other preventive-gate bypass) would produce.
GATE_VIOLATED = "gate_violated"
#: Execution evidence was confirmed AND no hard finding -- `commit` genuinely
#: satisfied the gate, per real trunk CI evidence, not merely per its own
#: committed self-report.
GATE_CONFIRMED_CLEAN = "gate_confirmed_clean"


@dataclass(frozen=True)
class DetectiveResult:
    outcome: str          # one of the seven constants above
    detail: str
    commit: str
    parent: str | None = None
    run_id: int | None = None
    #: Populated only for GATE_VIOLATED / GATE_CONFIRMED_CLEAN -- the
    #: recomputed verdict, unedited from `evaluate_keystone`.
    verdict: KeystoneVerdict | None = None


def classify_commit(commit: str, *, project_root: Path | str) -> DetectiveResult:
    """The whole decision for ``commit``: resolve its first parent, ask the
    two cross-commit resolvers, and — only when both confirm — recompute the
    keystone verdict from CI-VERIFIED evidence via the existing pure evaluator.

    Takes NO ``parent`` argument (external plan review, both reviewers,
    medium — a caller-supplied parent permits an accidental or malicious
    mismatched commit pair). The first parent is resolved internally via
    ``git rev-parse --verify "<commit>^1"``; a root commit (no parent) or any
    other unresolvable ref raises :class:`ReadError` naming the reason. A
    merge commit is judged against its FIRST parent only — the ordinary "what
    would have been reviewed" lineage; the merge's other parent's own changes
    are that parent commit's own concern, not this one's.

    Raises :class:`ReadError` (an unreadable/malformed manifest at either
    commit, the duplicate-id/root-commit cases above, or either resolver
    returning a status outside its own documented contract — fail-closed,
    external plan review openai medium) or :class:`EmptyLinkWalk` (the
    evaluator's own empty-link tripwire — a defect in the evaluator, not a
    finding about the repo) — the same two exceptions
    ``_keystone_ac_digest``/``_keystone_core`` already define. No new
    exception type, no exit-code contract.
    """
    root = Path(project_root)
    # Canonicalize to a full COMMIT SHA FIRST, before any resolver call —
    # `commit` may be a mutable ref (a branch name, "HEAD"); resolving it
    # once and using that resolved value throughout closes the window where
    # the ref could move between the parent-resolution call and the
    # resolver/manifest reads that follow (external plan review, openai,
    # medium). The `^{commit}` peel suffix — not a bare `--verify <ref>` —
    # because an annotated TAG resolves to the tag OBJECT's own SHA, not the
    # commit it points at; without peeling, that tag SHA would be handed to
    # both resolvers and both manifest reads, none of which accept anything
    # but a commit (external code review round 2, glm, low).
    rc, out, err = _run_git(root, "rev-parse", "--verify", f"{commit}^{{commit}}", timeout=_GIT_TIMEOUT_SECONDS)
    if rc != 0:
        raise ReadError(
            f"could not resolve {commit!r} to a commit ({(err or out).strip() or 'git rev-parse failed'})."
        )
    commit = out.strip()
    rc, out, err = _run_git(root, "rev-parse", "--verify", f"{commit}^1", timeout=_GIT_TIMEOUT_SECONDS)
    if rc != 0:
        raise ReadError(
            f"could not resolve the first parent of {commit!r} "
            f"({(err or out).strip() or 'git rev-parse failed'}) -- a root commit has no "
            "parent to diff against, and this control cannot judge one."
        )
    parent = out.strip()

    verification = resolve_ci_verification(commit, project_root=root)
    if verification.status == "no_record":
        return DetectiveResult(NO_QUALIFYING_RUN, verification.detail, commit, parent)
    if verification.status == "not_verified":
        return DetectiveResult(
            RUN_NOT_VERIFIED, verification.detail, commit, parent, verification.run_id,
        )
    if verification.status == "error":
        return DetectiveResult(VERIFICATION_QUERY_FAILED, verification.detail, commit, parent)
    if verification.status != "verified":
        raise ReadError(
            f"resolve_ci_verification returned unrecognized status {verification.status!r} for "
            f"{commit!r} -- outside its own documented contract (verified/not_verified/no_record/"
            "error); refusing to guess whether this counts as verified."
        )

    committed_manifest, _ = read_base_manifest(root, commit)
    base_manifest, _ = read_base_manifest(root, parent)
    evidence = resolve_execution_evidence(commit, committed_manifest=committed_manifest, project_root=root)
    if evidence.status == "unavailable":
        return DetectiveResult(
            EXECUTION_EVIDENCE_UNAVAILABLE, evidence.detail, commit, parent, evidence.run_id,
        )
    if evidence.status == "error":
        return DetectiveResult(
            EXECUTION_EVIDENCE_QUERY_FAILED, evidence.detail, commit, parent, evidence.run_id,
        )
    if evidence.status != "confirmed":
        raise ReadError(
            f"resolve_execution_evidence returned unrecognized status {evidence.status!r} for "
            f"{commit!r} -- outside its own documented contract (confirmed/unavailable/error); "
            "refusing to guess whether this counts as confirmed."
        )

    change_set = ac_change_set(root, parent, commit, committed_manifest, base_manifest)
    verified_manifest = build_verified_manifest(committed_manifest, evidence)
    verdict = evaluate_keystone(change_set, verified_manifest, base_manifest)
    outcome = GATE_VIOLATED if verdict.any_hard else GATE_CONFIRMED_CLEAN
    return DetectiveResult(
        outcome, "recomputed from CI-verified execution evidence", commit, parent, evidence.run_id, verdict,
    )


__all__ = [
    "NO_QUALIFYING_RUN", "RUN_NOT_VERIFIED", "VERIFICATION_QUERY_FAILED",
    "EXECUTION_EVIDENCE_UNAVAILABLE", "EXECUTION_EVIDENCE_QUERY_FAILED",
    "GATE_VIOLATED", "GATE_CONFIRMED_CLEAN",
    "DetectiveResult", "build_verified_manifest", "classify_commit",
    "ReadError", "EmptyLinkWalk",
]
