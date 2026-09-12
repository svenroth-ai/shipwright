"""Commit resolution half of the one-time rollout/grandfather transition
grace for two `/shipwright-project` Step-8 gates:
``check_criteria_free_of_implementation_detail`` (FR-01.02 #5) and
``check_no_empty_split`` (FR-01.02 #10) — Stage-2 code review on PR #729
(round 3), tracked as ``trg-9583d3a8``.

**The problem this closes.** Unlike their siblings ``check_basis_forbids_assumed``
(#4/#15) and ``check_starting_guidance_present`` (#11), which both carry a
``scope == "extension"`` carve-out for reasons specific to their own subject
matter, #5 (the implementation-detail ban) and #10 (the zero-row floor) are
stated as universal rules — a permanent extension-scope skip would excuse
every FUTURE violation too, not just the pre-existing content this module
exists to grandfather. The actual defect is narrower: an
``/shipwright-adopt``-onboarded project's ``spec.md`` may carry content
written before these two gates existed, and the very next Step 8 run now
hard-fails on it. Mirrors the shape of the ``check_binding_completeness``
rollout-transition precedent (``_layer_coverage_rollout.py`` — closing
``trg-aedcfe7b``): resolve a commit at-or-before the gate's own rollout
instant, in the CALLING project's own history, and grant grace only to
content that already existed there, essentially unchanged.

**Split from ``_project_gate_rollout_snapshot.py`` at the 300-LOC guideline**
(same precedent as ``_project_gate_wiring.py``/``_project_gate_manifest.py``
splitting apart for the identical reason) — THIS module owns resolving
"which historical commit", the sibling owns "what did that commit's spec.md/
manifest actually say".

**Deliberately a STANDALONE module family, not an extension of
``_layer_coverage_rollout.py``.** The P3.3 ADR's own "Out of Scope" section
already establishes the precedent that each gate family gets its own rollout
instant and its own resolver, since each gate ships on its own date; the two
FR-01.02 gates here happen to share ONE instant only because they landed in
the same PR (#729), otherwise unrelated to the layer-coverage family. ~20
lines of git shallow-check + ``rev-list --before`` + committer-epoch-verify
logic are duplicated here rather than factored into a shared primitive —
external plan review (glm) noted this makes a THIRD near-identical copy of
the same idea and that a future gate family will face a stronger temptation
to finally share it; accepted as a real, disclosed cost, not a decision
reversed here (a cross-cutting refactor of an already-shipped, heavily
reviewed sibling module is a larger, separately-scoped change).

**Always resolved against ``"HEAD"``.** Both gates run against the live
working tree (Step 8, F11's project-phase checks), not a specific base/head
diff pair, so there is no separate commit hash to plumb through. ``HEAD`` is
resolved to its immutable SHA once per call (external plan review, openai,
medium: caching under the *symbolic* name ``"HEAD"`` would go stale the
moment the process evaluates more than one repository state, e.g. across
`tmp_path` fixtures in one test run) — the cache key is always a concrete
commit hash.

**Fail-open direction (unchanged from the precedent): every failure
WITHHOLDS grace, never grants a false one.** A shallow clone, an absent
rollout commit (greenfield, or a repo entirely younger than the rollout
instant), or any git failure all degrade to "no grace" — the worst outcome
is an unexplained HARD block identical to today's pre-existing behaviour,
never a silently weakened gate.

**Trust anchor, `trg-4380c61a`.** A committer-date claim alone is a claim
whoever controls ``resolved_commit_sha`` can forge: ``resolved_commit_sha``
is typically an open PR's own HEAD, so a contributor can create a NEW commit
on their own branch with ``GIT_COMMITTER_DATE`` backdated before
``GATE_ROLLOUT_AT_EPOCH`` — it satisfies every check that only reads
``resolved_commit_sha``'s own reachable history, having never actually
existed at that instant. :func:`resolve_rollout_commit` additionally
requires the candidate to be an ancestor of (or equal to) the corroborated
boundary where the branch actually left the project's own already-merged
trunk (``origin/main``/``origin/master``/local fallbacks — reuses
``git_helpers._branch_base_commit``, the same hardened trunk-corroboration
pattern already trusted elsewhere in this gate family). Only content that
was genuinely already on that trunk before the branch's own commits could
be introduced passes; a self-authored commit sitting ON the branch, however
dated, never can. No corroborated trunk boundary (no ``origin`` remote, an
ambiguous/renamed trunk name) withholds grace entirely — the same
fail-closed direction as every other branch in this function, not a
special case.
"""

from __future__ import annotations

from pathlib import Path

from .git_helpers import _branch_base_commit, _run_git

# Same bound `git_helpers`'s own callers use on a git-subprocess hot path: a
# wedged `index.lock` or a stalled filesystem must degrade this OPTIONAL
# leniency lookup to "no grace", never hang the calling check.
_GIT_TIMEOUT_SECONDS = 30.0

#: ISO-8601 UTC form for humans: 2026-09-12T06:23:06Z. Derived from
#: `git show -s --format=%cI c411c36ad7af7d446047c552e032579d45b588fe` in
#: THIS monorepo — the committer time of PR #729's merge commit, the instant
#: `check_criteria_free_of_implementation_detail` and `check_no_empty_split`
#: first existed anywhere. Read as %cI (committer date), not %aI (author
#: date): the two can differ on a squash-merged PR, and committer time is
#: when the code actually became reachable on `main`.
GATE_ROLLOUT_AT_ISO = "2026-09-12T06:23:06Z"

#: Same instant as an epoch integer — passed to `git rev-list --before`,
#: never the ISO string. `git rev-list --before=<garbage-or-empty>` returns
#: rc=0 and silently resolves to the tip of history (approxidate's
#: "unparseable input means now" fallback) — no error, no distinguishable
#: failure. An integer epoch is the one format approxidate cannot misparse
#: into "now"; `resolve_rollout_commit` additionally re-verifies the
#: resolved commit's own committer time in Python before trusting it.
GATE_ROLLOUT_AT_EPOCH = 1789194186

#: The commit itself, kept only as a human-checkable comment target — never
#: parsed or compared against. Recompute via:
#:   git show -s --format='%H %cI %ct' c411c36ad7af7d446047c552e032579d45b588fe
GATE_ROLLOUT_COMMIT = "c411c36ad7af7d446047c552e032579d45b588fe"


def _is_shallow(project_root: Path) -> bool:
    """Best-effort: True unless git affirmatively says this is a full clone.
    Fails toward "shallow" (no grace) on any ambiguity — see module docstring."""
    rc, out, _ = _run_git(project_root, "rev-parse", "--is-shallow-repository",
                          timeout=_GIT_TIMEOUT_SECONDS)
    return not (rc == 0 and out.strip() == "false")


def resolve_head_sha(project_root: Path, commit_hash: str) -> str | None:
    """``commit_hash`` reaches every public function in this module family as
    a caller-supplied ref (usually the literal string ``"HEAD"``); resolved
    to a concrete SHA immediately so every cache is keyed by an immutable
    value, never a symbolic name that can silently point somewhere else on
    the next call within the same process."""
    rc, out, _ = _run_git(project_root, "rev-parse", commit_hash, timeout=_GIT_TIMEOUT_SECONDS)
    if rc != 0 or not out.strip():
        return None
    return out.strip()


def resolve_rollout_commit(project_root: Path, resolved_commit_sha: str) -> str | None:
    """The calling project's own commit at-or-before :data:`GATE_ROLLOUT_AT_EPOCH`,
    reachable from ``resolved_commit_sha`` (already a concrete SHA — see
    :func:`resolve_head_sha`) AND an ancestor of the project's own
    corroborated trunk boundary, or ``None`` when no such commit exists: a
    repo born entirely after the gate's rollout, a shallow clone, an
    uncorroborated/absent trunk anchor, or any git failure. Verifies the
    resolved commit's OWN committer time in Python rather than trusting
    git's ``--before`` parse alone, and — see the module docstring's "Trust
    anchor" note, `trg-4380c61a` — that the commit is not merely a
    self-authored, unmerged commit on ``resolved_commit_sha``'s own branch
    carrying a forged early committer date."""
    if not resolved_commit_sha or _is_shallow(project_root):
        return None
    rc, sha, _ = _run_git(
        project_root, "rev-list", "-1", f"--before={GATE_ROLLOUT_AT_EPOCH}", resolved_commit_sha,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if rc != 0 or not sha.strip():
        return None
    sha = sha.strip()
    rc2, ts, _ = _run_git(project_root, "show", "-s", "--format=%ct", sha,
                          timeout=_GIT_TIMEOUT_SECONDS)
    if rc2 != 0 or not ts.strip():
        return None
    try:
        committer_epoch = int(ts.strip())
    except ValueError:
        return None
    if committer_epoch > GATE_ROLLOUT_AT_EPOCH:
        return None  # git's answer postdates our cutoff — refuse rather than trust it

    base = _branch_base_commit(project_root, resolved_commit_sha)
    if base is None:
        return None  # no corroborated trunk boundary — an unverifiable ancestry claim is not grace
    rc3, count_out, _ = _run_git(
        project_root, "rev-list", "--count", f"{base}..{sha}", timeout=_GIT_TIMEOUT_SECONDS,
    )
    if not (rc3 == 0 and count_out.strip() == "0"):
        return None  # sha is not reachable from the trusted trunk boundary — refuse
    return sha


# Process-level cache, keyed by a CONCRETE (root, sha) pair — never the
# symbolic "HEAD" — so evaluating a second repo or a second commit within
# one long-lived process cannot read back a stale answer for the first.
_ROLLOUT_SHA_CACHE: dict[tuple[str, str], str | None] = {}


def clear_rollout_sha_cache() -> None:
    _ROLLOUT_SHA_CACHE.clear()


def cached_rollout_sha(project_root: Path, resolved_commit_sha: str) -> str | None:
    key = (str(project_root), resolved_commit_sha)
    if key not in _ROLLOUT_SHA_CACHE:
        _ROLLOUT_SHA_CACHE[key] = resolve_rollout_commit(project_root, resolved_commit_sha)
    return _ROLLOUT_SHA_CACHE[key]


__all__ = [
    "GATE_ROLLOUT_AT_EPOCH",
    "GATE_ROLLOUT_AT_ISO",
    "GATE_ROLLOUT_COMMIT",
    "resolve_head_sha",
    "resolve_rollout_commit",
    "cached_rollout_sha",
    "clear_rollout_sha_cache",
]
