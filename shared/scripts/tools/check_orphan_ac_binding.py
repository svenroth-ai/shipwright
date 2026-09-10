#!/usr/bin/env python3
"""ORPHAN AC BINDING — feeder (b) of P3.7's two feeder checks (campaign
``req3-04c-ac-identity-wave2``, SPEC §8 E2): "a test whose AC vanished".

Design: ``.shipwright/planning/iterate/2026-09-10-p3-7-feeder-checks.md``.

**HARD from day one, no baseline — the asymmetry, stated where a reader of
THIS file meets it.** Its sibling, ``check_ac_coverage_ratchet.py`` ("AC
without a test"), is anti-ratcheted because a real legacy backlog exists
(259 of 268 minted ACs, P3.6 design §2.1). This check has no such backlog to
grandfather: nothing has ever validated that a ``@covers`` tag's AC id still
exists, so *every* orphan this check would find is a genuine, addressable
defect, not inherited history — *"a gate needs a baseline only when it has a
legacy backlog to forgive"* (P3.6 design doc §7).

**Three named shapes, one shared mission, TWO arms — not one code path, and
not three.** The orphan-test detector's own triage card
(``trg-f68795d2``) and P3.6's design doc (§7, §10 item 8b) name three ways
a test's bound AC can effectively vanish without ever editing the
criterion's own text:

  (i)   **two-PR unbind sequence** — PR1 drops a ``@covers`` tag's ``/ACnn``
        suffix (no AC text changes); PR2, later, edits that AC's text
        against an already-unbound base.
  (ii)  **outright deletion** of a minted criterion that still had a
        binding.
  (iii) **id rotation** on the same criterion (``[AC01] foo`` -> ``[AC55]
        foo``, wording unchanged) — reads as removal-plus-addition, never
        enters P3.6's ``changed`` set.

All three collapse to ONE remediable condition — *a binding tag whose AC no
longer exists in the spec* — and that is exactly arm 1
(``_ac_binding_state.BindingState.orphaned``): it directly catches (ii) and
(iii), unconditionally, from current state alone.

**It does NOT, on its own, catch (i)** — tracing PR1's exact shape through
arm 1 shows the tag becomes a bare, VALID FR-level tag, not one naming a
vanished id, so arm 1 is silent on it (see
``_ac_binding_regression``'s module docstring for the full trace). Rather
than let the brief's "one shared condition" framing stand unverified, this
is disclosed and addressed by a SECOND arm reusing P3.6's own diagnosis of
its blind spot (design doc §7): a binding regression on an AC whose
criterion text this PR never touched (a narrower claim than "closes" —
arm 2 depends on the base manifest's own record being trustworthy, itself
disclosed rather than assumed; see ``_ac_binding_regression``'s docstring).
Both arms are HARD, no baseline, and both are reported under their own JSON
key so a consumer never has to guess which shape fired.

Exit codes (matching the family's dialect):

* ``0`` — clean.
* ``1`` — a HARD finding from either arm.
* ``2`` — infrastructure fault (unresolvable base, unreadable spec or
  manifest).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from verifiers._ac_binding_regression import (  # noqa: E402
    ReadError,
    binding_regressions,
    head_and_base_minted,
)
from verifiers._ac_binding_state import read_binding_state, spec_path_by_fr  # noqa: E402
from verifiers._keystone_ac_digest import (  # noqa: E402
    MANIFEST_RELPATH,
    read_base_manifest,
    require_manifest_shape,
)
from verifiers._layer_coverage_ac import spec_text_at  # noqa: E402
from verifiers._layer_coverage_regen import _merge_base  # noqa: E402
from verifiers.stdio import ensure_utf8_stdout  # noqa: E402

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INFRA = 2

_FETCH_REMEDY = (
    "no merge-base could be resolved by any route (origin/HEAD, the branch's upstream, "
    "origin/main, origin/master, local main/master). In CI, check that actions/checkout "
    "uses fetch-depth: 0; locally, run `git fetch --no-tags origin <your default branch>`."
)


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


def _infra(reason: str, **extra) -> dict:
    return {"gate": "orphan_ac_binding", "status": "infra_fault", "error": reason, **extra}


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
    return require_manifest_shape(manifest, "in the worktree")


def _ac_str(key: tuple[str, str]) -> str:
    return f"{key[0]}/{key[1]}"


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Orphan AC binding gate (P3.7 feeder b)")
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--head-sha", required=True,
        help="the commit under test; on a pull_request event this is github.sha.",
    )
    parser.add_argument(
        "--base-sha", default="",
        help="override the resolved merge-base. For tests and local reproduction only.",
    )
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    try:
        return _run_gate(project_root, args)
    except Exception as exc:  # last-resort fault boundary, same pattern the family uses
        return _emit(
            _infra(f"unexpected gate fault: {exc!r}", head_sha=args.head_sha), EXIT_INFRA,
        )


def _run_gate(project_root: Path, args: argparse.Namespace) -> int:
    base_sha = args.base_sha or _merge_base(project_root, args.head_sha)
    if not base_sha:
        return _emit(_infra(_FETCH_REMEDY, head_sha=args.head_sha), EXIT_INFRA)

    try:
        head_manifest = _read_head_manifest(project_root)
        base_manifest, base_warning = read_base_manifest(project_root, base_sha)
    except ReadError as exc:
        return _emit(_infra(str(exc), base_sha=base_sha, head_sha=args.head_sha), EXIT_INFRA)

    # Arm 1 — orphaned bindings, pure current-state read (no base needed).
    # Head-side spec text via `spec_text_at(head_sha)`, never a worktree disk
    # read: unlike feeder (a) (deliberately "what is bound right now"), this
    # gate ALSO runs arm 2 against the same head_sha, and reading the two
    # arms' HEAD spec text through two different mechanisms (disk vs git-show)
    # could disagree on an uncommitted or gitignored file — one reader, one
    # answer, matching every sibling gate in this family.
    try:
        spec_texts = {
            path: spec_text_at(project_root, args.head_sha, path)
            for path in set(spec_path_by_fr(head_manifest).values())
        }
        state = read_binding_state(spec_texts, head_manifest)
    except ReadError as exc:
        return _emit(_infra(str(exc), base_sha=base_sha, head_sha=args.head_sha), EXIT_INFRA)

    # Arm 2 — a binding regression on an AC whose text this PR never touched.
    try:
        head_minted, base_minted, arm2_warnings = head_and_base_minted(
            project_root, base_sha, args.head_sha, head_manifest, base_manifest,
        )
    except ReadError as exc:
        # Doubt review, low: arm 1's `state` (possibly a real, actionable
        # `orphaned` finding) is already computed above -- carry it into the
        # infra payload rather than discarding it, so an author facing BOTH a
        # genuine orphan and this fault sees both, not just the latter.
        return _emit(
            _infra(
                str(exc), base_sha=base_sha, head_sha=args.head_sha,
                orphaned_bindings=sorted(_ac_str(k) for k in state.orphaned),
            ),
            EXIT_INFRA,
        )
    regressions = binding_regressions(head_minted, base_minted, head_manifest, base_manifest)

    warnings = list(state.warnings) + arm2_warnings
    if base_warning:
        warnings.append(base_warning)

    orphaned = sorted(_ac_str(k) for k in state.orphaned)
    regressed = sorted(_ac_str(k) for k in regressions)
    payload = {
        "gate": "orphan_ac_binding",
        "base_sha": base_sha,
        "head_sha": args.head_sha,
        "orphaned_bindings": orphaned,
        "binding_regressions": regressed,
        "warnings": warnings,
    }
    if base_warning:
        payload["base_manifest_absent"] = base_warning

    if orphaned or regressed:
        payload["status"] = "blocked"
        payload["remedy"] = (
            "`orphaned_bindings`: the `@covers` tag(s) named there point at an AC id that no "
            "longer exists in the spec — remove the tag, or retarget it to the AC that replaced "
            "it (a rotated id). `binding_regressions`: the AC(s) named there had at least one "
            "`@covers` binding at the base commit and have none now, even though the criterion's own text "
            "is unchanged — restore the `@covers` tag (or the test it named), or, if retiring "
            "the binding is deliberate, edit the criterion's own text in the same PR so it is "
            "reviewed as the intentional change it is."
        )
        return _emit(payload, EXIT_BLOCKED)
    payload["status"] = "clean"
    return _emit(payload, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised by the subprocess smoke test
    raise SystemExit(main())
