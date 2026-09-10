#!/usr/bin/env python3
"""THE KEYSTONE GATE — a behaviour-changing PR names its changed ACs and their
bound tests ran green in THIS CI run.

Campaign ``req3-04c-ac-identity-wave2`` sub-iterate P3.6. Design + rulings:
``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md``.

SPEC §1.4, one sentence: *a behaviour-changing PR must not merge without (a)
naming the changed ACs and (b) re-running the tests bound to those ACs in CI —
green.*

**Read that sentence with its scope attached, and never without it (ruling Q2):**
*a PR that changes behaviour in code and changes no acceptance criterion passes
this gate untouched; it enforces spec-to-test consistency, not code-to-spec
consistency.* Detecting the latter from paths is Track R, struck from scope.
This gate does not claim to enforce "behaviour-changing PRs" in general, and any
summary of it that drops this paragraph is overclaiming.

**Two deviations from the sub-iterate spec, both ratified at the plan-review
gate and repeated here because a deviation recorded only in a PR body is lost
the moment the PR is merged:**

* **Q1 — no ``ac_id -> tests -> last_verified_commit`` baseline (D9 dropped).**
  ``ci.yml`` re-runs every suite on every PR, so there is nothing selective for a
  ledger to compensate for, and a stored baseline is a *self-reported trust
  artifact* — the class that cost PR #690 twelve review rounds.
* **Q1b — "named ACs" is spec-DERIVED, not author-DECLARED.** The sub-iterate
  spec's AC-1 reads as a declaration; a declaration is forgeable and a derived
  signal is not. Same reasoning that makes every gate in this family recompute
  rather than read a self-report (``evaluate_cross_layer``: *"never the
  self-reported event ``fr_impact``"*).

A **third** deviation exists, from the ratified DESIGN rather than from the sub-iterate
spec, and is **ratified (2026-09-10, coordinator)**: an ``added`` AC that already carries a
binding takes AC-2's greenness walk instead of being report-only. It was taken at build time,
no reviewer asked for it, and the reasoning + scope live in design §7 and in
``_keystone_core``'s added-arm comment. Named here so a reader of this file does not infer
from the two above that the shipped behaviour matches the design everywhere else.

**Why this gate does NOT call ``resolve_execution_evidence``** — the single most
important thing to know before "improving" it. That resolver answers *"can I
trust evidence I did not produce, for a commit that is not mine?"* (P3.5's
question, a post-merge one). This gate asks *"did test T run green in THIS
run?"* — same process tree, so it reads the producer directly. Worse than
unnecessary, wiring the resolver in here would make the gate **permanently
inert**: ``ci_provenance._qualifying_runs`` accepts only ``event == "push"`` runs
on the default branch, so on a ``pull_request`` event it resolves ``unavailable``
on 100 % of PRs. The gate is therefore *exactly as strong as ``ci.yml``* — a
disclosed limit (design §4/§7), not a hidden one.

**Head manifest = the REGENERATED file on disk, never the committed bytes.** The
preceding ``Check traceability manifest against a fresh regeneration`` step
rewrites ``.shipwright/compliance/test-traceability.json`` in place from this
run's own JUnit *before* it compares, so hand-edited committed claims are already
overwritten by the time this reads them (probe A pins that). Regeneration happens
before that step's comparison, so this holds even while ``main`` carries the
advisory (drift-code 1) structural drift; drift-code 2 fails that step and this
one never runs — fail-closed.

Exit codes, matching ``ci_manifest_drift_check``'s dialect in the same job so the
job does not carry two:

* ``0`` — clean, including advisory-only findings and report-only ``unbound`` ACs
* ``1`` — a HARD finding, or the reader-divergence authoring finding
* ``2`` — a genuine infrastructure fault ONLY (unresolvable base, unreadable spec
  or manifest, untrustworthy AC markers at head)

A JSON verdict goes to stdout on every path, including both failures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from verifiers._keystone_ac_digest import (  # noqa: E402
    MANIFEST_RELPATH,
    ReadError,
    ac_change_set,
    read_base_manifest,
    require_manifest_shape,
)
from verifiers._keystone_core import EmptyLinkWalk, evaluate_keystone  # noqa: E402
from verifiers._layer_coverage_regen import _merge_base  # noqa: E402
from verifiers.stdio import ensure_utf8_stdout  # noqa: E402

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INFRA = 2

#: Named so the failure message can be pasted verbatim. `_merge_base` tries
#: `origin/HEAD` -> `@{u}` -> `origin/main` -> `origin/master` -> local
#: `main`/`master`, so the remedy must NOT name `origin/main`: a repo whose
#: default is `master`, or one resolving through its tracking upstream, would be
#: sent to fetch a ref that does not exist.
_FETCH_REMEDY = (
    "no merge-base could be resolved by any route (origin/HEAD, the branch's "
    "upstream, origin/main, origin/master, local main/master). In CI, check that "
    "actions/checkout uses fetch-depth: 0; locally, run "
    "`git fetch --no-tags origin <your default branch>`."
)


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


def _infra(reason: str, **extra) -> dict:
    return {"gate": "keystone_ac", "status": "infra_fault", "error": reason, **extra}


def _read_head_manifest(project_root: Path) -> dict:
    path = project_root / MANIFEST_RELPATH
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReadError(
            f"the regenerated {MANIFEST_RELPATH} could not be read ({exc}). This gate must run "
            "AFTER the manifest-regeneration step in the same job."
        ) from exc
    except ValueError as exc:
        raise ReadError(f"{MANIFEST_RELPATH} in the worktree is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReadError(f"{MANIFEST_RELPATH} in the worktree is not a JSON object")
    # Valid JSON is not the same as a valid manifest: `{"requirements": []}` parses
    # fine and then raises AttributeError inside three different readers, which is
    # a bare exit 1 with no JSON -- see `require_manifest_shape` (openai, medium).
    return require_manifest_shape(manifest, "in the worktree")


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Keystone AC gate (P3.6)")
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--head-sha", required=True,
        help="the commit under test; on a pull_request event this is github.sha, "
             "the merge commit the workspace has checked out.",
    )
    parser.add_argument(
        "--base-sha", default="",
        help="override the resolved merge-base. For tests and local reproduction "
             "only -- CI must let _merge_base resolve it.",
    )
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    # The precondition is _merge_base's own VERDICT, never `git rev-parse --verify
    # origin/main`: that would exit 2 as a false "infra fault" on a master-default
    # or upstream-tracking repo whose base _merge_base resolves fine.
    base_sha = args.base_sha or _merge_base(project_root, args.head_sha)
    if not base_sha:
        return _emit(_infra(_FETCH_REMEDY, head_sha=args.head_sha), EXIT_INFRA)

    try:
        head_manifest = _read_head_manifest(project_root)
        base_manifest, base_warning = read_base_manifest(project_root, base_sha)
        change_set = ac_change_set(
            project_root, base_sha, args.head_sha, head_manifest, base_manifest,
        )
    except ReadError as exc:
        return _emit(
            _infra(str(exc), base_sha=base_sha, head_sha=args.head_sha), EXIT_INFRA,
        )

    try:
        verdict = evaluate_keystone(change_set, head_manifest, base_manifest)
    except EmptyLinkWalk as exc:
        # The ∀-over-empty tripwire. Reaching it is a bug in THIS gate, not a
        # finding about the repo -- so it must not be reported as exit 1
        # ("blocked"), which is what an uncaught exception's Python exit code 1
        # would have looked like, indistinguishable from a real hard finding.
        # A gate that cannot decide is an infrastructure fault (self-review).
        return _emit(_infra(
            f"the keystone evaluator hit its own empty-link tripwire: {exc} "
            "This is a defect in the gate; report it rather than editing the spec.",
            base_sha=base_sha, head_sha=args.head_sha,
        ), EXIT_INFRA)

    warnings = list(verdict.warnings)
    if base_warning:
        warnings.append(base_warning)
    payload = {
        "gate": "keystone_ac",
        "base_sha": base_sha,
        "head_sha": args.head_sha,
        "changed_acs": sorted(f"{fr}/{ac}" for fr, ac in change_set.changed),
        "added_acs": sorted(f"{fr}/{ac}" for fr, ac in change_set.added),
        # Report-only, for p3.7(b)'s orphan detector to consume.
        "removed_acs": sorted(f"{fr}/{ac}" for fr, ac in change_set.removed),
        # The subset that HAD a test binding at base — the single-PR
        # delete-or-rotate-the-id shape both external plan reviewers found. Its
        # own key so p3.7(b) consumes a list, not a diff of two other lists.
        "removed_with_bindings": sorted(
            f"{fr}/{ac}" for fr, ac in verdict.removed_with_bindings),
        "unbound": sorted(f"{fr}/{ac}" for fr, ac in verdict.unbound),
        "findings": [f.as_dict() for f in verdict.hard],
        "advisory": [f.as_dict() for f in verdict.advisory],
        "warnings": warnings,
    }
    if base_warning:
        # Its OWN key, not merely a line in `warnings`: case (i) of the base read
        # silently disarms `binding_removed` for this PR, which is exactly the
        # state an attacker would want, so a consumer must be able to detect the
        # degradation by key rather than by matching prose (design AC-K9(e)).
        payload["base_manifest_absent"] = base_warning

    if verdict.removed_with_bindings:
        # Stage-3 doubt review, low. Report-only by design (see the module-level comment on
        # `removed_with_bindings`'s home arm), which means a bare exit 0 with
        # this list buried in JSON is otherwise invisible in a green CI log --
        # an operator has to already know to look for it.
        # stderr, never stdout: `_emit` below prints the JSON payload as the
        # WHOLE of stdout and every caller (`run_gate` here, CI's own step)
        # does `json.loads` on it -- a stdout line ahead of the JSON would
        # break every one of them. GitHub Actions recognises `::warning::`
        # workflow commands on either stream.
        print(
            f"::warning::THE KEYSTONE GATE: {len(verdict.removed_with_bindings)} AC(s) with a "
            "test binding at base were removed in this PR: "
            f"{', '.join(f'{fr}/{ac}' for fr, ac in sorted(verdict.removed_with_bindings))}. "
            "This does not block (see design §7); p3.7(b) is the hard gate for an orphaned "
            "@covers tag.",
            file=sys.stderr,
        )
    if verdict.any_hard:
        payload["status"] = "blocked"
        return _emit(payload, EXIT_BLOCKED)
    payload["status"] = "clean"
    return _emit(payload, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised by the subprocess smoke test
    raise SystemExit(main())
