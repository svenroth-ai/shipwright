"""D3 — a requirement promised via ``new_frs`` but never delivered.

Extracted from :mod:`group_d` (iterate-2026-07-21) so that module keeps room
under its anti-ratchet ceiling, the same reason :mod:`_group_d_link_proof` was
split out of :mod:`_group_d_traceability`. Pure move: the body is unchanged
apart from the delivery rule this iterate introduced.

Why it is its own concern: D1 asks "is this requirement covered *now*", reading
the spec and the manifest. D3 asks a purely historical question of the event log
alone — "was every promise kept" — and needs neither.

**What D3 actually detects, stated without overclaim.** ``tests`` on a
``work_completed`` event is that run's WHOLE-SUITE total; it is not evidence
about the minted FR specifically. So "a tested mint delivers" means, in
practice, "a mint recorded by a run that reported a suite result delivers", and
the surviving failure condition is narrow: *an FR was minted by an event that
recorded no test totals, and no event has named it under ``affected_frs``
since*. That is a **recording-integrity** check, not proof the requirement
works — and it is worth keeping precisely because such a recording omission is
what produced the FR-01.15 false-positive this module exists to correct.
Per-FR test evidence is D1's job, via the manifest link proof.

Two known asymmetries, deliberate and pinned by tests:

- the ``affected_frs`` path carries **no** test gate (pre-existing D3 behaviour,
  left unchanged — the new path is stricter, never looser);
- the guard is evaluated per EVENT, not per FR, so an event that mints an
  untested FR while also affecting a tested one delivers both.
"""

from __future__ import annotations


def check_d3(
    events: list[dict] | None,
) -> tuple[str, str, str, list[str]]:
    """Returns (status, severity, detail, evidence)."""
    if events is None:
        return "skip", "MEDIUM", "shipwright_events.jsonl not present", []

    promised: dict[str, str] = {}  # fr_id -> earliest ts where it appeared in new_frs
    delivered_after: dict[str, list[str]] = {}  # fr_id -> ts list of delivery hits

    for ev in events:
        if ev.get("type") != "work_completed":
            continue
        ts = ev.get("ts")
        if not isinstance(ts, str):
            continue
        # ``tests`` may be any JSON type in a hand-edited or union-merged log;
        # D4 already guards this way. Without the isinstance check a string
        # ``tests`` raises AttributeError and run()'s blanket except turns the
        # whole check into a synthetic HIGH finding.
        tests = ev.get("tests")
        total = tests.get("total") if isinstance(tests, dict) else None
        tested = isinstance(total, int) and total > 0
        for fr in ev.get("new_frs", []) or []:
            if not isinstance(fr, str):
                continue
            if fr not in promised or ts < promised[fr]:
                promised[fr] = ts
            # A TESTED mint delivers: ``work_completed`` means the work is done,
            # so ``new_frs`` reads "introduced AND delivered". Demanding a
            # separate later affirmation flagged forever any FR right the first
            # time, and audited a duplicate-``affected_frs`` convention the
            # writer never required (fr_gates.py accepts ``new_frs`` alone).
            # ``tested`` narrows what survives to a recording omission — see the
            # module docstring for what this does and does NOT prove.
            if tested:
                delivered_after.setdefault(fr, []).append(ts)
        for fr in ev.get("affected_frs", []) or []:
            if not isinstance(fr, str):
                continue
            delivered_after.setdefault(fr, []).append(ts)

    if not promised:
        return "skip", "MEDIUM", "no events introduced FRs via new_frs", []

    pending: list[str] = []
    for fr_id, promised_ts in promised.items():
        delivered_ts_list = delivered_after.get(fr_id, [])
        # ``>=`` (not ``>``): an FR present in both ``new_frs`` and
        # ``affected_frs`` of the SAME event (ts == promised_ts) — the normal
        # single-iterate "introduce + deliver" case — counts as delivered.
        # Strictly-later was the FR-01.33 webui false-positive: a same-event
        # delivery stayed "pending" forever until some unrelated later event
        # happened to touch the FR (iterate-2026-06-05-fr-linkage-lifecycle).
        if any(ts >= promised_ts for ts in delivered_ts_list):
            continue
        pending.append(fr_id)

    if not pending:
        return "pass", "MEDIUM", "every promised FR was delivered (tested mint or affected_frs event)", []

    pending.sort()
    head = ", ".join(pending[:5])
    if len(pending) > 5:
        head += f", … (+{len(pending) - 5})"
    # Name the ACTUAL condition. "never delivered" sent a reader hunting for
    # missing work when the real cause is missing evidence — the exact wrong
    # investigation that FR-01.15 cost this project.
    detail = (
        "FRs minted with no test totals recorded and never named in "
        f"affected_frs since — {head}"
    )
    evidence = [
        f"{fr_id}: minted {promised[fr_id]} with no tests recorded; "
        "never named in affected_frs since"
        for fr_id in pending
    ]
    return "fail", "MEDIUM", detail, evidence


__all__ = ["check_d3"]
