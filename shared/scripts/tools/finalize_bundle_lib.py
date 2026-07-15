#!/usr/bin/env python3
"""Pure schema + validation + argv layer for ``finalize_bundle.py``.

Split out (iterate-2026-07-15-finalize-bundle) so the orchestrator stays under
the 300-LOC source budget. This module has NO side effects and NO subprocess /
filesystem access — it defines the payload contract (``validate``) and builds
the argv for each finalize sub-tool. ``finalize_bundle.py`` owns the runtime
(subprocess execution, result assembly, CLI). Tested through the orchestrator's
public ``run()`` / ``main()`` (see test_finalize_bundle*.py).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_TOOLS_DIR = Path(__file__).resolve().parent          # shared/scripts/tools
_SCRIPTS_DIR = _TOOLS_DIR.parent                       # shared/scripts

# Absolute sub-tool paths — cwd-independent (external-review MED).
_ARTIFACT_SYNC = _SCRIPTS_DIR / "artifact_sync.py"
_WRITE_DECISION_DROP = _TOOLS_DIR / "write_decision_drop.py"
_WRITE_CHANGELOG_DROP = _TOOLS_DIR / "write_changelog_drop.py"
_APPEND_ITERATE_ENTRY = _TOOLS_DIR / "append_iterate_entry.py"
_FINALIZE_ITERATE = _TOOLS_DIR / "finalize_iterate.py"

_ALLOWED_TOP_KEYS = frozenset(
    {"run_id", "artifact_sync", "decision", "changelog", "iterate_entry", "finalize"}
)
_DECISION_REQUIRED = ("section", "title", "context", "decision", "consequences")
_DECISION_OPTIONAL = ("rationale", "rejected", "architecture_impact", "spec_ref")
_DECISION_ALLOWED = frozenset(_DECISION_REQUIRED + _DECISION_OPTIONAL)
_ARTIFACT_SYNC_ALLOWED = frozenset({"ref", "skip"})
# append_iterate_entry.py injects run_id + date itself and REJECTS them in the
# entry payload — pre-reject here so the typo fails fast, before F1/F3/F4 write.
_ITERATE_ENTRY_FORBIDDEN = frozenset({"run_id", "date"})
_ARCHITECTURE_IMPACTS = ("component", "data-flow", "convention", "none")
_CHANGELOG_CATEGORIES = frozenset(
    {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
)
_DEFAULT_REF = "HEAD~1..HEAD"

# Optional F3 fields → their CLI flag (emitted only when present/non-empty).
_F3_OPTIONAL = (
    ("rationale", "--rationale"), ("rejected", "--rejected"),
    ("architecture_impact", "--architecture-impact"), ("spec_ref", "--spec-ref"),
)


@dataclass
class RunResult:
    """The outcome of one sub-tool subprocess."""

    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list, Path], RunResult]


class BundleValidationError(ValueError):
    """Payload failed validation — raised BEFORE any subprocess runs."""


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def _require_str(obj: dict, key: str, where: str) -> None:
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise BundleValidationError(f"{where}.{key} is required and must be a non-empty string")


def _reject_unknown(obj: dict, allowed, where: str) -> None:
    unknown = set(obj) - set(allowed)
    if unknown:
        raise BundleValidationError(
            f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(allowed)}"
        )


def validate(payload: object) -> str:
    """Validate ``payload`` structurally; return the trimmed ``run_id``.

    Structural only — the sub-tools own their SEMANTIC validation (ADR field
    length budgets, the F5b FR-gate, iterate-entry shape), which surfaces at the
    owning step. A structural error here fails fast before ANY subprocess runs; a
    semantic error (e.g. an over-budget ADR field, or an FR-gate-incomplete
    ``event_extras``) still surfaces at its step (F3 / F5b) after the earlier
    writes — but those writes are idempotent per ``run_id``, so the fix-and-retry
    is safe. Raises :class:`BundleValidationError`.
    """
    if not isinstance(payload, dict):
        raise BundleValidationError("payload must be a JSON object")
    _reject_unknown(payload, _ALLOWED_TOP_KEYS, "payload")
    _require_str(payload, "run_id", "payload")

    decision = payload.get("decision")
    if not isinstance(decision, dict):
        raise BundleValidationError("'decision' (object) is required")
    _reject_unknown(decision, _DECISION_ALLOWED, "decision")  # catch a misspelled optional flag
    for key in _DECISION_REQUIRED:
        _require_str(decision, key, "decision")
    impact = decision.get("architecture_impact")
    if impact is not None and impact not in _ARCHITECTURE_IMPACTS:
        raise BundleValidationError(
            f"decision.architecture_impact must be one of {list(_ARCHITECTURE_IMPACTS)}"
        )

    changelog = payload.get("changelog")
    if not isinstance(changelog, list) or not changelog:
        raise BundleValidationError("'changelog' must be a non-empty list")
    for i, item in enumerate(changelog):
        if not isinstance(item, dict):
            raise BundleValidationError(f"changelog[{i}] must be an object")
        if item.get("category") not in _CHANGELOG_CATEGORIES:
            raise BundleValidationError(
                f"changelog[{i}].category must be one of {sorted(_CHANGELOG_CATEGORIES)}"
            )
        _require_str(item, "bullet", f"changelog[{i}]")

    entry = payload.get("iterate_entry")
    if not isinstance(entry, dict) or not entry:
        raise BundleValidationError("'iterate_entry' (non-empty object) is required")
    forbidden = _ITERATE_ENTRY_FORBIDDEN & set(entry)
    if forbidden:
        raise BundleValidationError(
            f"iterate_entry must not set {sorted(forbidden)} — append_iterate_entry adds them"
        )

    finalize = payload.get("finalize")
    if not isinstance(finalize, dict):
        raise BundleValidationError("'finalize' (object) is required")
    _require_str(finalize, "reason", "finalize")
    if not isinstance(finalize.get("event_extras"), dict):
        raise BundleValidationError("finalize.event_extras (object) is required")

    asy = payload.get("artifact_sync")
    if asy is not None:
        if not isinstance(asy, dict):
            raise BundleValidationError("'artifact_sync' must be an object")
        _reject_unknown(asy, _ARTIFACT_SYNC_ALLOWED, "artifact_sync")
        if "skip" in asy and not isinstance(asy["skip"], bool):
            raise BundleValidationError("artifact_sync.skip must be a boolean")
        if "ref" in asy and (not isinstance(asy["ref"], str) or not asy["ref"].strip()):
            raise BundleValidationError("artifact_sync.ref must be a non-empty string")

    return payload["run_id"].strip()


# --------------------------------------------------------------------------- #
# argv builders (pure)
# --------------------------------------------------------------------------- #

def _base(tool: Path, root: Path, run_id: str) -> list:
    return [sys.executable, str(tool), "--project-root", str(root), "--run-id", run_id]


def f1_argv(root: Path, ref: str | None = None) -> list:
    # The F1 argv builder owns the default ref (None/empty -> HEAD~1..HEAD).
    return [sys.executable, str(_ARTIFACT_SYNC),
            "--project-root", str(root), "--ref", ref or _DEFAULT_REF]


def f3_argv(root: Path, run_id: str, decision: dict) -> list:
    argv = _base(_WRITE_DECISION_DROP, root, run_id)
    for key in _DECISION_REQUIRED:
        argv += [f"--{key}", decision[key]]
    for key, flag in _F3_OPTIONAL:
        if decision.get(key):
            argv += [flag, decision[key]]
    return argv


def f4_argv(root: Path, run_id: str, item: dict) -> list:
    return _base(_WRITE_CHANGELOG_DROP, root, run_id) + [
        "--category", item["category"], "--bullet", item["bullet"],
    ]


def f5c_argv(root: Path, run_id: str, entry: dict) -> list:
    return _base(_APPEND_ITERATE_ENTRY, root, run_id) + [
        "--entry-json", json.dumps(entry, ensure_ascii=False),
    ]


def f5b_argv(root: Path, run_id: str, finalize: dict) -> list:
    return _base(_FINALIZE_ITERATE, root, run_id) + [
        "--reason", finalize["reason"],
        "--event-extras-json", json.dumps(finalize["event_extras"], ensure_ascii=False),
    ]
