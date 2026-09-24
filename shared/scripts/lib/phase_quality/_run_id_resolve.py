"""Composite-fallback ``resolve_run_id`` (plan § 5.3).

Split out of ``_run_id.py`` (300-LOC ceiling): the pointer-reading functions
(``pointer_run_id``, ``pointer_worktree_root``) answer "what does the run
pointer say"; this module answers "what run_id do we use when it doesn't" —
a distinct, layered fallback chain that happens to call back into the
pointer functions as its first, preferred source.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_events_path  # noqa: E402
from lib.jsonl_records import read_jsonl_records  # noqa: E402
from lib.campaign_wave import (  # noqa: E402
    per_unit_worktree_identity,
    resolve_wave_safe_unit_value,
)
from ._run_id import pointer_run_id  # noqa: E402


def resolve_run_id(project_root: Path, session_id: str) -> str:
    """Composite-fallback run_id resolution (plan § 5.3).

    Priority:
    0. the per-session iterate run pointer (:func:`pointer_run_id`)
    1. ``shipwright_run_config.json::run_id``
    2. ``events.jsonl`` latest ``run_started`` event
    3. ``SHIPWRIGHT_LOOP_ID`` + ``SHIPWRIGHT_LOOP_UNIT_ID``
    4. ``session_id`` itself (standalone)

    Step 0 is what makes the iterate spec checks (S2, S3, W2, S9, S10)
    evaluable at all. For an iterate, steps 1-3 are structurally inert — nothing
    writes a top-level ``run_id``, no producer emits a ``run_started`` event,
    and the loop vars are campaign-only — so the audit used to be handed the
    raw session UUID (or ``"unknown"``). Neither is an ``iterate_history`` key,
    so ``unresolvable_run_id_skip`` correctly refused to let an unrelated run's
    complexity or category decide those checks' verdicts, and the whole family
    SKIPped on every real invocation
    (iterate-2026-08-06-resolve-run-id-seam).

    **What step 0 does and does not buy.** It makes the audit's ``run_id`` the
    canonical one — verified in production: the Stop hook reports
    ``run=iterate-<date>-<slug>`` where it previously reported the session
    UUID, so findings and the triage cards ``audit_compliance_on_stop`` labels
    are attributable to the run, and a SKIP now names it. Whether the five
    guarded checks then *evaluate* is a separate condition this does not
    change: they need the audited tree to hold the run's own ledger entry, and
    F5c writes that into the run's WORKTREE. The hook resolves ``project_root``
    from the session's cwd, which is the MAIN repo even mid-iterate — that used
    to leave an in-flight run's audit rooted at main, unable to observe the
    ledger entry appearing (fail-safe, but a permanent SKIP). Closed by
    :func:`pointer_worktree_root`, which the hook now prefers: it redirects
    ``project_root`` to the run's own worktree via the same per-session pointer
    this function reads, so the re-audit this docstring's step 0 exists for can
    actually fire (trg-b36fd844, external review round 2).

    ``session_id`` is normalised ONCE here and that one value is reused for the
    sentinel test, the pointer lookup, the payload comparison and the tail —
    the sole production caller already passes a stripped value, so this only
    removes the possibility of the four disagreeing. One consequence beyond a
    pure move: a whitespace-only ``session_id`` now yields ``"unknown"`` rather
    than the whitespace itself. Unreachable from either production caller (both
    pass ``.strip() or "unknown"``), and it makes the tail agree with the
    sentinel test rather than contradict it.

    The ``isinstance(data, dict)`` check is load-bearing: valid JSON that is not
    an object (``[1, 2]``, ``null``) made ``data.get`` raise ``AttributeError``,
    which the ``except`` below does not catch. This runs FIRST in the Stop hook,
    outside its per-phase ``try`` and after the once-per-Stop claim is taken — so
    that raise killed the audit for EVERY phase and the sibling invocations then
    no-oped on the burned claim.
    """
    session_id = (session_id or "").strip()

    from_pointer = pointer_run_id(project_root, session_id)
    if from_pointer:
        return from_pointer

    run_config = project_root / "shipwright_run_config.json"
    if run_config.exists():
        try:
            data = json.loads(run_config.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                run_id = data.get("run_id")
                if isinstance(run_id, str) and run_id:
                    return run_id
        # ValueError (not just JSONDecodeError) because read_text raises
        # UnicodeDecodeError on a non-UTF-8 run config — the same post-claim
        # escape the pointer branch above guards against.
        except (ValueError, OSError, RecursionError):
            pass

    # Via the events_log SSoT rather than a raw join. The two are equivalent
    # (``resolve_events_path`` is a literal ``project_root / EVENT_FILE``), so
    # this is behaviour-identical — but it retires the pre-split
    # ``_MAIN_REPO_ONLY`` exemption instead of carrying it to a new file.
    events_path = resolve_events_path(project_root)
    if events_path.exists():
        try:
            latest_run_id: str | None = None
            # Record-boundary recovery via the shared SSoT: a merge=union merge can
            # leave two records on one physical line, and the pre-fix per-line
            # json.loads dropped BOTH — silently falling through to the session-id
            # fallback and mis-attributing every audit row keyed on the resolved run
            # (iterate-2026-07-20-events-record-boundary-remainder). read_jsonl_records
            # returns only JSON objects, in wire order, so latest-wins is preserved.
            for obj in read_jsonl_records(events_path).records:
                if obj.get("type") == "run_started":
                    rid = obj.get("run_id") or obj.get("id")
                    if isinstance(rid, str) and rid:
                        latest_run_id = rid
            if latest_run_id:
                return latest_run_id
        except OSError:
            pass

    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID", "").strip()
    # R5a: sentinel -> unset, then the per-unit worktree basename (concurrency-safe;
    # see `per_unit_worktree_identity`), before giving up to `loop_id` alone.
    raw_loop_unit = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID", "").strip()
    loop_unit = resolve_wave_safe_unit_value(raw_loop_unit)
    if raw_loop_unit and not loop_unit:
        loop_unit = per_unit_worktree_identity(project_root) or ""
    if loop_id and loop_unit:
        return f"{loop_id}-{loop_unit}"
    if loop_id:
        return loop_id

    return session_id or "unknown"
