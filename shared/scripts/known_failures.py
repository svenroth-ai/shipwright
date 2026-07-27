"""The one reader for ``shipwright_known_failures.json``.

The file is a hand-maintained declaration: *these failures predate onboarding
and are accepted, do not count them as new regressions.*

It used to be read by exactly one component — the compliance audit — so an
onboarded project got its inherited failures excused by the audit and reported
as fresh failures by the test phase. Two components, two truths about one run,
and a permanently red test phase that teaches the operator to ignore red.

This module is that single reader. Both the audit collector
(``collectors/test_evidence.collect_known_failures``) and the test phase read
through it, so the two cannot drift.

Lives at ``shared/scripts/`` top level, stdlib-only, per ADR-045 — see
``project_facts`` for the same reasoning.

Two distinct questions, deliberately kept apart:

* **Which of these named failures are accepted?** — :func:`split_accepted`,
  matching by identity. This is the one that can honestly say "this failure is
  known".
* **Is this run's failure count within the declared allowance?** —
  :func:`within_baseline`, pure arithmetic mirroring the audit's rule. It is an
  *aggregate allowance* and says nothing about which failures those were.

A caller that only has counts must report the second as an allowance, never
dress it up as the first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

KNOWN_FAILURES_NAME = "shipwright_known_failures.json"

# A declared id shorter than this is not used for substring matching — a
# one- or two-character entry would swallow unrelated failures. Such an entry
# still counts toward the aggregate baseline; it just cannot claim an identity.
_MIN_SUBSTRING_MATCH = 4


@dataclass(frozen=True)
class AcceptedFailure:
    """One declared entry of ``known_failures``."""

    test: str
    description: str = ""
    ticket: str = ""
    added: str = ""
    count: int = 1


@dataclass(frozen=True)
class AcceptedBaseline:
    """The declared list, plus how it was read.

    ``present`` / ``malformed`` exist so a caller can say *"the accepted list
    could not be read"* instead of silently reporting "nothing is accepted" —
    the same failure mode this module exists to remove.
    """

    entries: tuple[AcceptedFailure, ...] = ()
    baseline_failure_count: int = 0
    present: bool = False
    malformed: bool = False


def _coerce_entry(raw: object) -> AcceptedFailure | None:
    if not isinstance(raw, dict):
        return None
    test = raw.get("test")
    if not isinstance(test, str) or not test.strip():
        return None
    count = raw.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        count = 1
    return AcceptedFailure(
        test=test,
        description=raw.get("description", "") if isinstance(raw.get("description"), str) else "",
        ticket=raw.get("ticket", "") if isinstance(raw.get("ticket"), str) else "",
        added=raw.get("added", "") if isinstance(raw.get("added"), str) else "",
        count=count,
    )


def load_accepted_baseline(project_root: Path | str) -> AcceptedBaseline:
    """Read the declared accepted-failure list.

    Absent file → an empty baseline (``present=False``). Present but
    unreadable → ``malformed=True`` with the same zero-baseline result, so a
    corrupt file can never *widen* what is excused.
    """
    path = Path(project_root) / KNOWN_FAILURES_NAME
    if not path.exists():
        return AcceptedBaseline()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return AcceptedBaseline(present=True, malformed=True)

    if not isinstance(data, dict):
        return AcceptedBaseline(present=True, malformed=True)

    raw_entries = data.get("known_failures", [])
    if not isinstance(raw_entries, list):
        return AcceptedBaseline(present=True, malformed=True)

    entries = tuple(e for e in (_coerce_entry(r) for r in raw_entries) if e is not None)

    declared = data.get("baseline_failure_count")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared >= 0:
        count = declared
    else:
        count = sum(e.count for e in entries)

    return AcceptedBaseline(
        entries=entries, baseline_failure_count=count, present=True, malformed=False,
    )


def split_accepted(
    failure_names: list[str] | tuple[str, ...],
    baseline: AcceptedBaseline,
) -> tuple[list[str], list[str]]:
    """Split reported failures into ``(known_and_accepted, genuine)`` by identity.

    A reported failure is accepted when a declared entry's ``test`` is equal to
    it, or is contained in it (reported names usually carry a suite/file prefix
    the declaration omits). Short declared ids do not substring-match — see
    ``_MIN_SUBSTRING_MATCH``.

    A declared failure that did **not** fire this run excuses nothing: matching
    runs from the reported side, so an unrelated new failure stays genuine even
    when the declared count would have covered it.
    """
    declared = [e.test for e in baseline.entries]
    accepted: list[str] = []
    genuine: list[str] = []

    for name in failure_names:
        if not isinstance(name, str) or not name.strip():
            continue
        if any(
            d == name or (len(d) >= _MIN_SUBSTRING_MATCH and d in name)
            for d in declared
        ):
            accepted.append(name)
        else:
            genuine.append(name)

    return accepted, genuine


def within_baseline(passed: int, total: int, baseline_count: int) -> bool:
    """True when the passed/total gap is covered by the declared allowance.

    Verbatim mirror of the audit's rule (``rtm_generator``: ``gap <= 0`` →
    covered; ``baseline > 0 and gap <= baseline`` → ``COVERED (baseline)``). A
    different rule here would re-open the divergence this module closes.

    This is an **aggregate allowance**. It does not identify which failures
    were accepted — use :func:`split_accepted` when identities are available.
    """
    gap = total - passed
    if gap <= 0:
        return True
    return baseline_count > 0 and gap <= baseline_count


def has_exact_failure_count(failed: object = None, skipped: object = None) -> bool:
    """True when the layer reported enough to know the failure count exactly.

    Either an explicit ``failed``, or an explicit ``skipped`` (which makes the
    residual ``total - passed - skipped`` exact). Without either, all we have is
    a gap that may be failures or skips.

    This is the switch on the aggregate baseline allowance, and it mirrors the
    audit's deliberate rule (``tests_block.progression_result`` + its pinning
    test ``test_explicit_residual_ignores_baseline_charity``): *an explicit
    residual is exact, so the baseline exemption must NOT apply to it.* The
    exemption is charity for an unbroken-down gap, not a licence to wave away
    failures somebody actually counted. Where the count is exact, acceptance is
    decided per failure by :func:`split_accepted`, not by arithmetic.
    """
    exact_failed = isinstance(failed, int) and not isinstance(failed, bool) and failed >= 0
    exact_skipped = isinstance(skipped, int) and not isinstance(skipped, bool) and skipped >= 0
    return exact_failed or exact_skipped


def genuine_failure_count(
    *,
    passed: int,
    total: int,
    failed: int | None = None,
    skipped: int | None = None,
) -> int:
    """How many tests genuinely failed, using the best signal available.

    Prefers an explicit ``failed`` count; falls back to ``total - passed -
    skipped``; falls back again to the bare gap. The fallbacks matter because
    ``total - passed`` counts *skipped* tests as failures — which would make a
    fully green run with host-gated skips consume accepted-failure allowance.
    Never negative.

    **Deliberately the same arithmetic as the audit's**
    ``tests_block.progression_result`` (the skip-vs-fail SSoT introduced when
    skipped tests became a first-class field): explicit skip count → genuine
    failures are ``total - passed - skipped``; no explicit count → the gap is
    read charitably. That module renders a *cell*, this one returns a *number*,
    so neither can call the other — the agreement is pinned by
    ``shared/tests/test_known_failures_audit_parity.py`` instead. Changing one
    without the other re-opens exactly the divergence this module exists to
    close.
    """
    if isinstance(failed, int) and not isinstance(failed, bool) and failed >= 0:
        return failed
    gap = total - passed
    if isinstance(skipped, int) and not isinstance(skipped, bool) and skipped >= 0:
        gap -= skipped
    return max(0, gap)


__all__ = [
    "KNOWN_FAILURES_NAME",
    "AcceptedBaseline",
    "AcceptedFailure",
    "genuine_failure_count",
    "has_exact_failure_count",
    "load_accepted_baseline",
    "split_accepted",
    "within_baseline",
]
