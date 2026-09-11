#!/usr/bin/env python3
"""TEST-BODY SUSPECTS — the third, lower-priority item named (and explicitly
deferred) by P3.7's own sub-iterate spec (campaign
``req3-04c-ac-identity-wave2``; design:
``.shipwright/planning/iterate/2026-09-10-p3-7-feeder-checks.md``), delivered
here bundled with P3.8 (provenance: ``trg-33a474e2``, filed by P3.7's own
runner and amended by an operator to bundle in ``trg-c2329759``, p3.8's own
"don't lose this sub-iterate" tracker, which was then dismissed into it — see
the design doc's Section 12 for the full provenance trail, including
``trg-d03a239d``, filed before the real authorization card surfaced).

Design: ``.shipwright/planning/iterate/2026-09-10-p3-8-rewritability-advisory.md``,
addendum section (bundled build).

**Predicate.** An acceptance criterion whose own text is UNCHANGED between
base and head, that has a test bound to it (via a ``@covers`` tag), whose
BODY was edited in this diff. See ``verifiers._test_body_suspects``' module
docstring for the exact mechanism and its named exclusions.

**HARD CONSTRAINT, stated where a reader of this file's CI wiring meets it:
advisory means advisory.** This is the same class of check P3.6's own design
doc (§7) and P3.8's own sub-iterate spec both name — "mechanics raise a
flag, a human decides" — and it may never become a hard gate. Unlike this
campaign's two P3.7 gate siblings (``check_ac_coverage_ratchet.py``: exit
0/1/2, ratcheted; ``check_orphan_ac_binding.py``: exit 0/1/2, hard), this
script's own ``main()`` returns ``0`` UNCONDITIONALLY — including when an
infrastructure fault (an unresolvable merge-base, an unreadable manifest, a
git failure) prevents evaluation at all. A degraded infra state is reported
in the JSON payload as ``status: "not_evaluated"`` and never turned into a
failing exit code: an advisory check that could fail a CI *step* through its
own exit code is not meaningfully different from a gate the moment that job
is required, so the guarantee is enforced here, unconditionally, rather than
left to the CI YAML's own discipline (contrast
``ci_manifest_drift_check.py``, which DOES fail its step on a real infra
fault at exit 2 — a deliberate, narrower precedent this script does not
follow, because THIS check's own governing card is explicit that it must
never become a gate even by accident).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from verifiers._ac_binding_regression import ReadError  # noqa: E402
from verifiers._keystone_ac_digest import (  # noqa: E402
    MANIFEST_RELPATH,
    read_base_manifest,
    require_manifest_shape,
)
from verifiers._layer_coverage_regen import _merge_base  # noqa: E402
from verifiers._test_body_suspects import test_body_suspects  # noqa: E402
from verifiers.stdio import ensure_utf8_stdout  # noqa: E402

EXIT_OK = 0  # the ONLY exit code this script ever returns -- see module docstring.

_FETCH_REMEDY = (
    "no merge-base could be resolved by any route (origin/HEAD, the branch's upstream, "
    "origin/main, origin/master, local main/master). In CI, check that actions/checkout "
    "uses fetch-depth: 0; locally, run `git fetch --no-tags origin <your default branch>`."
)

_NOTE = (
    "The acceptance criterion's own text is UNCHANGED, but a test bound to it had its "
    "body edited in this diff. This is a SIGNAL, not a verdict -- a human should judge "
    "whether the edit merely refactors the assertion or quietly weakens it. Never "
    "auto-resolved, and never blocks a merge on its own."
)


def _read_head_manifest(project_root: Path) -> dict:
    path = project_root / MANIFEST_RELPATH
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReadError(
            f"the regenerated {MANIFEST_RELPATH} could not be read ({exc}). This check must "
            "run AFTER the manifest-regeneration step in the same job.",
        ) from exc
    except ValueError as exc:
        raise ReadError(f"{MANIFEST_RELPATH} in the worktree is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReadError(f"{MANIFEST_RELPATH} in the worktree is not a JSON object")
    return require_manifest_shape(manifest, "in the worktree")


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Test-body suspects (P3.7 deferred item, advisory-only, never blocks)",
    )
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
        payload = _run_check(project_root, args)
    except Exception as exc:  # last-resort fault boundary -- still never a non-zero exit.
        payload = {
            "check": "test_body_suspects", "status": "not_evaluated",
            "error": f"unexpected fault: {exc!r}", "head_sha": args.head_sha,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_OK


def _run_check(project_root: Path, args: argparse.Namespace) -> dict:
    base_sha = args.base_sha or _merge_base(project_root, args.head_sha)
    if not base_sha:
        return {
            "check": "test_body_suspects", "status": "not_evaluated",
            "error": _FETCH_REMEDY, "head_sha": args.head_sha,
        }

    try:
        head_manifest = _read_head_manifest(project_root)
        base_manifest, base_warning = read_base_manifest(project_root, base_sha)
        suspects, warnings = test_body_suspects(
            project_root, base_sha, args.head_sha, head_manifest, base_manifest,
        )
    except ReadError as exc:
        return {
            "check": "test_body_suspects", "status": "not_evaluated", "error": str(exc),
            "base_sha": base_sha, "head_sha": args.head_sha,
        }

    if base_warning:
        warnings = [*warnings, base_warning]

    payload: dict = {
        "check": "test_body_suspects",
        "base_sha": base_sha,
        "head_sha": args.head_sha,
        "suspects": [
            {"fr_id": s["fr_id"], "ac_id": s["ac_id"], "test_id": s["test_id"]}
            for s in suspects
        ],
        "warnings": warnings,
    }
    if suspects:
        payload["status"] = "advisory"
        payload["note"] = _NOTE
    else:
        payload["status"] = "clean"
    return payload


if __name__ == "__main__":  # pragma: no cover - exercised by the subprocess smoke test
    raise SystemExit(main())
