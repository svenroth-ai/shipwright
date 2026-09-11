"""Per-project resolution of ``check_binding_completeness``'s own rollout instant
(trg-aedcfe7b): the one-time transition/cutoff rule Stage-3 doubt-review on PR
#687 asked for, so an ``explicit`` binding that predates this gate's own
existence is not held to a standard it never knew about.

**Why a resolved commit, not a hardcoded SHA.** ``263c9197e6428134ad4e97c55384bf5dad89cbc1``
is a commit in THIS framework's own monorepo — it has no meaning inside a
target project's repository (measured population: ``shipwright-webui``, a
completely separate git history). What IS portable is the wall-clock INSTANT
that commit landed: the code implementing ``check_binding_completeness``
simply did not exist anywhere before it, in any repo. :data:`GATE_ROLLOUT_AT_EPOCH`
freezes that instant; :func:`resolve_rollout_commit` asks each CALLING
project's own git history "what was my own state at-or-before that instant",
which is the question that actually generalises.

**Why an epoch integer, not the ISO string, is passed to git.** Measured
directly against this repo: ``git rev-list --before=<garbage-or-empty>``
returns rc=0 and silently resolves to the tip of history (approxidate's
"unparseable input means now" fallback) — no error, no distinguishable
failure. A malformed cutoff would therefore grant BLANKET amnesty to every
gap, silently. An integer epoch is the one format approxidate cannot
misparse into "now", and :func:`resolve_rollout_commit` additionally
verifies the resolved commit's OWN committer time in Python (never trusting
git's parse alone) before treating it as usable — belt AND suspenders,
because the constant being correct today does not guarantee every future
caller (a different git version, a locale quirk, a copy-paste of the raw
string instead of the epoch) preserves that correctness.

**Why ``with_evidence=False``.** ``required_layers``/``required_layers_source``
are parsed straight from ``spec.md`` (``_requirement_parse.py``), never
evidence-derived — the same collector call ``_layer_coverage_regen`` already
uses for the base/head manifests, just pointed at a third, older commit.
Reuses that module's ``_load_collector``/``_archive_tree``/``_build`` rather
than re-implementing archive extraction, which would otherwise risk losing
the hardened tar-extraction defences (``_safe_extract``'s path-containment
and member-type guards, ``_archive_tree``'s subprocess timeout) to a
copy-paste drift.

**Why callers should only invoke this when a gap is already otherwise HARD.**
The archive+build here is a full ``git archive`` + collector test-root walk
of a third, potentially old, commit — the SAME cost class as the base/head
builds ``_layer_coverage_regen`` already pays twice. It buys nothing on a
clean run (the overwhelming common case), so ``layer_coverage_binding.py``
calls this ONLY after finding at least one candidate HARD gap, not
unconditionally on every F11 invocation.

**Disclosed, not fixed** (mirrors the original P3.3 ADR's own precedent of
naming a residual gap rather than eliminating it at disproportionate cost):

- A repo whose visible history was reshaped (a shallow clone, or a brownfield
  repo onboarded via ``/shipwright-adopt`` with regenerated/rewritten history)
  may have no commit reachable at-or-before the rollout instant even though
  the CODE it holds is conceptually much older. :func:`resolve_rollout_commit`
  treats this identically to "genuinely born after rollout" — no grace. This
  is the conservative direction for an OPTIONAL leniency: failing to grant an
  earned grace merely restores today's status quo severity, while granting an
  unverifiable one would silently weaken a HARD gate. A shallow clone is
  detected and short-circuited for exactly this reason — resolving a
  ``--before`` query against a truncated history would otherwise return a
  present-but-meaningless commit (a truncation artifact), not "no snapshot".
- :func:`resolve_rollout_commit`'s Python-side re-check (module docstring
  above) only catches the resolved commit being TOO NEW; ``git rev-list
  --before`` itself assumes commit dates increase monotonically while
  walking history and can stop early or pick a non-optimal ancestor on a
  history with out-of-order committer dates (a rebase that refreshes
  committer date while preserving author date, or clock skew across a
  merge) — internal plan review, opus, low-medium. The narrow failure mode
  this leaves open is picking an OLDER-than-necessary pre-rollout commit,
  which is the conservative direction (it can only WITHHOLD grace a
  slightly-newer, still-legitimate snapshot would have granted), so it is
  disclosed rather than fixed, consistent with every other gap in this list.
- :func:`rollout_manifest`'s blanket ``except Exception`` (internal plan review,
  opus, medium) conflates a genuine "no pre-rollout history" answer with an
  unrelated infra hiccup (a collector crash, a tar-extraction failure, a
  transient subprocess anomaly) — both degrade identically to ``None`` (no
  grace), with no diagnostic distinguishing them. This package has no
  existing logging convention to hook into (a new one for this single call
  site was judged not worth introducing), so the failure is silent by
  design, same trade-off as the shallow-clone and plugin-adoption-lag gaps
  above: fail-open here only ever WITHHOLDS an optional leniency, never
  grants a false one, so the worst outcome is an unexplained HARD block
  identical to today's pre-existing behaviour, not a new correctness risk.
- The rollout instant is fixed to when this framework FIRST shipped the gate,
  not to when any given target project's installed plugin version last
  updated. A project that adopts a much older plugin version and only later
  upgrades to one carrying this gate can author a binding in good faith,
  gate-unaware, well after 2026-09-07 in wall-clock terms, and still receive
  no grace — the same class of unfairness this rule exists to close, merely
  shifted to plugin-adoption time instead of framework-ship time. Fixing that
  precisely would need a NEW piece of infrastructure (per-project
  plugin-version-adoption tracking) this card does not build.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ._layer_coverage_regen import _archive_tree, _build, _load_collector
from .git_helpers import _run_git

#: Same bound `git_helpers._GIT_TIMEOUT_SECONDS` uses on the F11 hot path: a wedged
#: `index.lock` or a stalled filesystem must degrade this OPTIONAL leniency lookup to
#: "no grace", never hang the whole F11 run (internal plan review, opus, low).
_GIT_TIMEOUT_SECONDS = 30.0

#: ISO-8601 UTC form for humans: 2026-09-07T16:09:19Z. Derived from
#: ``git show -s --format=%cI 263c9197e6428134ad4e97c55384bf5dad89cbc1`` in
#: THIS monorepo (committer time 2026-09-07T18:09:19+02:00, CEST) — the
#: instant PR #687 (P3.3, ``check_binding_completeness``) merged and this
#: code first existed anywhere. Read as %cI (committer date), not %aI
#: (author date): the two can differ on a squash-merged PR, and the
#: committer time is when the code actually became reachable on ``main``.
GATE_ROLLOUT_AT_EPOCH = 1788797359

#: Same value in ISO form, kept only as a human-checkable comment target —
#: never parsed. Recompute via:
#:   python -c "from datetime import datetime,timezone;\
#:   print(int(datetime.fromisoformat('2026-09-07T16:09:19+00:00').timestamp()))"
GATE_ROLLOUT_AT_ISO = "2026-09-07T16:09:19Z"


def _is_shallow(project_root: Path) -> bool:
    """Best-effort: True unless git affirmatively says this is a full clone.

    Fails toward "shallow" (no grace) on any ambiguity — a shallow clone's
    ``rev-list --before`` result is untrustworthy (it can return a real,
    present commit that is simply the oldest one the clone happens to have,
    not "the state at that instant"), and granting grace on a false negative
    here is the wrong direction for an optional leniency (see module
    docstring)."""
    rc, out, _ = _run_git(project_root, "rev-parse", "--is-shallow-repository",
                          timeout=_GIT_TIMEOUT_SECONDS)
    return not (rc == 0 and out.strip() == "false")


def resolve_rollout_commit(project_root: Path, commit_hash: str) -> str | None:
    """The calling project's own commit at-or-before :data:`GATE_ROLLOUT_AT_EPOCH`,
    reachable from ``commit_hash``, or ``None`` when no such commit exists —
    a repo born entirely after the gate's rollout (the documented
    no-legacy-valve-for-greenfield case, now extended to this valve too), a
    shallow clone (see :func:`_is_shallow`), or any git failure. Verifies the
    resolved commit's OWN committer time in Python rather than trusting
    git's ``--before`` parse alone (module docstring: a malformed cutoff
    silently resolves to "now", which this catches)."""
    if not commit_hash or _is_shallow(project_root):
        return None
    rc, sha, _ = _run_git(
        project_root, "rev-list", "-1", f"--before={GATE_ROLLOUT_AT_EPOCH}", commit_hash,
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
    return sha


# Process-level cache, same shape/precedent as `_layer_coverage_regen._BASE_CACHE`:
# small dict keyed by (root, commit), caches a negative (``None``) result too so a
# repo with no pre-rollout history is not re-probed on every gap in the same run.
# Assumes history immutability for a given (root, commit) within one process lifetime
# (same assumption `_BASE_CACHE` already makes) — a repo whose history is rewritten or
# unshallowed between two calls for the SAME commit_hash within one long-lived process
# would see a stale cached answer. Fine for a single F11 verification run (external
# code review, P3.3 follow-up, glm, low); not documented as an issue for a service that
# would need to invalidate it, since no such caller exists today.
_ROLLOUT_CACHE: dict[tuple[str, str], dict | None] = {}


def clear_rollout_cache() -> None:
    _ROLLOUT_CACHE.clear()


def rollout_manifest(project_root: Path, commit_hash: str) -> dict | None:
    """The requirement manifest as it stood at-or-before this gate's own
    rollout instant, in the CALLING project's own history — used only to
    grant transition grace to a binding that predates the gate (trg-aedcfe7b).

    Never raises: any failure (git, archive, collector) degrades to ``None``
    (no grace), because this is a purely OPTIONAL leniency layered on top of
    the existing enforcement — a hiccup here must never turn a clean pass
    into a blocking infra error, the opposite of what
    ``regenerate_base_head``'s own fail-closed contract requires for the
    CORRECTNESS-critical base/head comparison."""
    key = (str(project_root), commit_hash)
    if key in _ROLLOUT_CACHE:
        return _ROLLOUT_CACHE[key]
    result: dict | None = None
    try:
        sha = resolve_rollout_commit(project_root, commit_hash)
        if sha:
            loaded = _load_collector()
            if loaded is not None:
                test_links, io, _evio = loaded
                with tempfile.TemporaryDirectory(prefix="sw-trace-rollout-") as rd:
                    root = Path(rd)
                    if _archive_tree(project_root, sha, root):
                        # `evidence={}` IS the `with_evidence=False` equivalent — the exact
                        # same idiom `_layer_coverage_regen.regenerate_base_head` uses
                        # internally (`evidence = ... if with_evidence else {}`). Confirmed
                        # by reading `build_manifest`: `required_layers`/`required_layers_source`
                        # are parsed from spec.md text alone, before `evidence` is ever
                        # consulted (which only feeds `coverage`/link status) — pinned by
                        # `test_rollout_build_is_evidence_independent_for_required_layers`
                        # (external code review, P3.3 follow-up, glm, medium).
                        result = _build(test_links, io, root, {}, sha)
    except Exception:  # noqa: BLE001 — best-effort optional grace, never a hard failure.
        # Raised three times across review (opus, glm, openai): this blanket catch
        # conflates a genuine "no pre-rollout history" answer with an unrelated infra
        # hiccup (collector crash, tar-extraction failure). NOT converted to an
        # `_infra_result` in the wrapper (openai's suggestion) because that would be a
        # regression, not a fix: this function only ever runs after a candidate HARD gap
        # already exists, so "no grace" here means the ALREADY-CORRECT HARD finding
        # stands — exactly what should happen when an infra hiccup makes the optional
        # leniency check unavailable. Reclassifying that as an infra ERROR would instead
        # HIDE a legitimate HARD violation behind an infrastructure-failure message,
        # the opposite of this gate family's fail-closed intent. See module docstring's
        # "Disclosed, not fixed" list.
        result = None
    _ROLLOUT_CACHE[key] = result
    return result


__all__ = [
    "GATE_ROLLOUT_AT_EPOCH",
    "GATE_ROLLOUT_AT_ISO",
    "resolve_rollout_commit",
    "rollout_manifest",
    "clear_rollout_cache",
]
