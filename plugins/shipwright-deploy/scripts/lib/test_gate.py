"""The shared pre-release test-gate oracle.

FR-01.08 criterion 1: a release is refused on failing tests until a person
confirms. Extracted out of ``validate-deploy.py`` (its original home) so a
second coded caller — ``release.py``'s structural refusal — reads the exact
same verdict rather than re-deriving it: one oracle, read by every caller
that needs it, never a second parallel implementation that could drift from
the first.

A person's confirmation reaches this function ONLY via the ``confirmed``
argument — never inferred from an environment variable or a config default,
so the refusal cannot be silenced by anything but a caller that was itself
told a person confirmed (validate-deploy.py's ``--confirm-failing-tests``,
release.py's ``--confirm-failing-tests``).
"""

from __future__ import annotations

import json
from pathlib import Path

# The routine, non-blocking E2E outcomes for a change with no startable web
# surface of its own. Anything else — "failed", "partial", "error", or an
# unrecognised value — is treated as a real E2E failure and blocks, matching
# criterion 1's actual intent (Tier-3 PR review round 5).
_E2E_NONBLOCKING_STATUSES = frozenset({"passed", "skipped", "not_run"})


def evaluate_test_gate(project_root: Path, confirmed: bool) -> tuple[str, str | None]:
    """Return ``(state, error_or_none)``.

    ``state`` is one of ``passed`` / ``failing-unconfirmed`` /
    ``failing-confirmed`` / ``no-results``. A genuinely ABSENT results file
    is treated the same as a failing one. ``no-results`` is still reported as
    its own distinct ``state`` (rather than folded into
    ``failing-unconfirmed``) so a caller can still tell "no test phase ran at
    all" apart from "tests ran and failed", but it BLOCKS exactly like
    ``failing-unconfirmed`` unless ``confirmed`` is ``True``.

    A results file that EXISTS but fails to parse is treated as
    ``failing-*``, not ``no-results`` — a present-but-corrupt file is not the
    same as an absent one.
    """
    results_path = project_root / "shipwright_test_results.json"
    if not results_path.exists():
        if confirmed:
            return "no-results", None
        return "no-results", (
            "shipwright_test_results.json not found — re-run with "
            "--confirm-failing-tests only after a person has explicitly "
            "confirmed the deploy should proceed anyway"
        )

    unreadable_reason: str | None = None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        unreadable_reason = str(exc)
        data = {}
    else:
        # A syntactically valid JSON value that isn't an object (`[]`, `"x"`,
        # `5`) would otherwise crash `.get()` below with AttributeError.
        if not isinstance(data, dict):
            unreadable_reason = f"root value is {type(data).__name__}, expected an object"
            data = {}

    if unreadable_reason is not None:
        if confirmed:
            return "failing-confirmed", None
        return "failing-unconfirmed", (
            f"shipwright_test_results.json exists but could not be read ({unreadable_reason}) "
            "— re-run with --confirm-failing-tests only after a person has "
            "explicitly confirmed the deploy should proceed anyway"
        )

    # shipwright_test_results.json is written in two shapes depending on
    # which flow last produced it: the full-pipeline /shipwright-test phase
    # writes unit/e2e/... at the TOP level; /shipwright-iterate's F5 step
    # nests the identical sub-keys under iterate_latest. A deploy can follow
    # either flow, so this gate must recognise both, or it silently never
    # fires in an iterate-run repo (unit is always None there).
    view = data
    if not isinstance(data.get("unit"), dict):
        nested = data.get("iterate_latest")
        if isinstance(nested, dict):
            view = nested

    unit_raw = view.get("unit")
    e2e_raw = view.get("e2e")
    unit = unit_raw if isinstance(unit_raw, dict) else {}
    e2e = e2e_raw if isinstance(e2e_raw, dict) else {}
    unit_ok = unit.get("status") == "passed"
    # E2E is non-blocking, matching the pipeline's own _validate_test
    # convention. An ALLOWLIST of the routine non-blocking statuses, not a
    # blocklist of one bad value, is what actually implements "only a
    # reported partial failure does [block]".
    e2e_status = e2e.get("status")
    e2e_ok = e2e_status is None or e2e_status in _E2E_NONBLOCKING_STATUSES
    if unit_ok and e2e_ok:
        return "passed", None

    if confirmed:
        return "failing-confirmed", None

    return "failing-unconfirmed", (
        f"tests have not passed (unit={unit.get('status')!r}, "
        f"e2e={e2e.get('status')!r}) — re-run with --confirm-failing-tests "
        "only after a person has explicitly confirmed the deploy should "
        "proceed anyway"
    )


__all__ = ["evaluate_test_gate"]
