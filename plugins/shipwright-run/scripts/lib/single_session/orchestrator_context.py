"""Single-session orchestrator CONTEXT reload + persistence guard (SS4).

After each phase completes, the ``single_session`` master reconstructs "where
the pipeline is" from ``shipwright_run_config.json`` + the COMPACT per-phase
summaries stored in ``phase_tasks[].result`` — NEVER from full phase
transcripts. This module is the reader for that reload (resumability +
context-budget foundation) and the on-disk PERSISTENCE GUARD that enforces the
phase-runner's artifact contract: a result may not CLAIM an artifact it did not
write to disk (the section-writer silent-loss class, closed at the loop level).

Pure data-package discipline (the SS1 lifecycle-reuse contract): this module
NEVER mutates ``shipwright_run_config.json`` and NEVER imports
``orchestrator_pkg`` (that would form an import cycle — ``orchestrator_pkg``
imports ``single_session``). It reads the config file directly, read-only,
exactly the way ``loop_state`` reads its own state file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .result_contract import MAX_SUMMARY_CHARS

# Public config name (stable per the Shipwright ``shipwright_`` config prefix).
RUN_CONFIG_REL_PATH = "shipwright_run_config.json"

# Keys copied verbatim from a phase_tasks[] entry into a compact summary record.
# Deliberately small — the reload never pulls anything transcript-sized.
_TASK_KEYS = ("phaseTaskId", "phase", "splitId", "status")


def run_config_path(project_root: Path) -> Path:
    """Canonical run-config path for a project."""
    return Path(project_root) / RUN_CONFIG_REL_PATH


# The run_config schema this reader understands. Kept as a literal (no
# orchestrator_pkg import — that would form a cycle), mirroring how
# ``result_contract`` keeps ``VALID_PHASES`` a literal.
_SUPPORTED_SCHEMA_VERSION = 2


def _load_config(project_root: Path) -> Optional[dict[str, Any]]:
    """Read the run config read-only.

    Returns None when it is absent, unreadable, not valid JSON, or not the v2
    schema this reader understands — a resuming master then treats the run as
    not-a-single-session-run rather than crashing on a half-written or legacy
    config (mirrors ``resolve_next_dispatch``'s ``no_config`` guard).
    """
    path = run_config_path(project_root)
    if not path.exists():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(config, dict) or config.get("schemaVersion") != _SUPPORTED_SCHEMA_VERSION:
        return None
    return config


def phase_summaries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact per-phase records rebuilt from ``phase_tasks[].result``.

    One record per phase task, carrying ONLY the task identity plus the compact
    result fields (``summary``, ``artifacts``, ``ok``, and ``reason`` when set).
    Tasks with no result yet (pending / in_progress) carry ``summary=None`` and
    ``artifacts=[]``. A transcript is NEVER copied through — only the
    contract-bounded ``summary`` string is.
    """
    out: list[dict[str, Any]] = []
    for task in config.get("phase_tasks", []):
        result = task.get("result") or {}
        rec: dict[str, Any] = {k: task.get(k) for k in _TASK_KEYS}
        rec["summary"] = result.get("summary")
        rec["artifacts"] = list(result.get("artifacts") or [])
        rec["ok"] = result.get("ok")
        if result.get("reason"):
            rec["reason"] = result["reason"]
        out.append(rec)
    return out


def context_budget_chars(summaries: list[dict[str, Any]]) -> int:
    """Total summary chars across all phase records — the context-budget metric.

    Bounded by ``len(summaries) * MAX_SUMMARY_CHARS`` because each stored summary
    was ceiling-checked by the result contract at write time. This is the number
    the master watches to prove the reload is O(N · summary) and not O(transcript).
    """
    return sum(len(s.get("summary") or "") for s in summaries)


def reload_orchestrator_context(project_root: Path) -> Optional[dict[str, Any]]:
    """Rebuild the orchestrator's pipeline context from disk (read-only).

    Returns ``None`` when no run config exists. The returned dict is intentionally
    small: run identity / status / mode / frozen splits + the compact phase
    summaries + the context-budget total. It NEVER reads a phase transcript, so
    resuming the master conversation costs bounded context regardless of how many
    phases (or how large a transcript) preceded it.
    """
    config = _load_config(project_root)
    if config is None:
        return None
    summaries = phase_summaries(config)
    return {
        "runId": config.get("runId"),
        "status": config.get("status"),
        "mode": config.get("mode"),
        "splitsFrozen": list(config.get("splits_frozen") or []),
        "phaseSummaries": summaries,
        "summaryCharBudget": context_budget_chars(summaries),
        "summaryCharCeiling": MAX_SUMMARY_CHARS,
    }


def verify_artifacts_exist(project_root: Path, artifacts: list[str]) -> list[str]:
    """Return the subset of ``artifacts`` that do NOT exist on disk.

    The on-disk PERSISTENCE GUARD. Artifacts are repo-relative (already
    contract-validated for shape), so each is resolved against ``project_root``.
    A phase-runner result that claims an artifact it never wrote is caught here
    — BEFORE the phase is completed — instead of being lost silently. An empty
    list means every claimed artifact is present.
    """
    missing: list[str] = []
    root = Path(project_root)
    for a in artifacts:
        if not isinstance(a, str) or not a.strip():
            missing.append(str(a))
            continue
        if not (root / a).exists():
            missing.append(a)
    return missing
