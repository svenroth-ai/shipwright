"""Frozen vocab + fail-closed reduction primitives for the execution-evidence reader.

Extracted from ``execution_evidence.py`` (ADR-099 300-LOC cap) as the lowest layer:
the closed ``status`` / ``executed`` vocabularies, their fail-closed coercion, the
per-entry constructor, and the reduction precedence (a failure outranks a pass; a
real run outranks a skip). Both the parsers (``_evidence_readers``) and the core
(``execution_evidence``) import from here — one-directional, no cycle.
"""

from __future__ import annotations

EVIDENCE_INDEX_VERSION = 2
# Frozen closed vocabularies — the single source of truth mirrored by both the
# evidence-index schema and traceability_schema.json's testLink enums.
STATUS_VOCAB = frozenset({"enabled", "skipped", "quarantined", "only"})
EXECUTED_VOCAB = frozenset({"pass", "fail", "not_run"})
LAYER_VOCAB = frozenset({"unit", "integration", "e2e"})

# Fail-closed reduction precedence when ONE test id appears more than once (retries,
# shards, multiple browser projects, parametrized cases, duplicate names): a failure
# is never hidden by a later pass, and a real (enabled) run is never masked by a skip.
_EXECUTED_RANK = {"fail": 3, "pass": 2, "not_run": 1}
_STATUS_RANK = {"enabled": 4, "quarantined": 3, "only": 2, "skipped": 1}


def normalize_status(value: object) -> str:
    """Coerce to the frozen status vocab; an out-of-vocab value → ``quarantined``
    (held-out, can never combine with a pass to claim coverage ok — fail-closed)."""
    return value if value in STATUS_VOCAB else "quarantined"


def normalize_executed(value: object) -> str:
    """Coerce to the frozen executed vocab; an out-of-vocab value → ``not_run``
    (an unrecognized runner outcome is never trusted as a pass — fail-closed)."""
    return value if value in EXECUTED_VOCAB else "not_run"


def entry(status: object, executed: object, runner: str) -> dict:
    return {
        "status": normalize_status(status),
        "executed": normalize_executed(executed),
        "runner": runner,
    }


def stronger(cur: tuple[str, str], new: tuple[str, str]) -> tuple[str, str]:
    """Combine two ``(status, executed)`` verdicts fail-closed under the rank
    precedence — used to fold multi-project / multi-record test outcomes."""
    s = new[0] if _STATUS_RANK[new[0]] >= _STATUS_RANK[cur[0]] else cur[0]
    e = new[1] if _EXECUTED_RANK[new[1]] >= _EXECUTED_RANK[cur[1]] else cur[1]
    return s, e


def merge_into(results: dict, tid: str, ent: dict) -> None:
    """Fold ``ent`` into ``results[tid]`` under the fail-closed reduction so a
    duplicate test id across retries/shards/projects can never let a pass mask a fail."""
    prev = results.get(tid)
    if prev is None:
        results[tid] = ent
        return
    s, e = stronger((prev["status"], prev["executed"]), (ent["status"], ent["executed"]))
    results[tid] = {"status": s, "executed": e, "runner": prev.get("runner") or ent.get("runner", "")}
