"""A per-round baseline, so "this round corrected a requirement" can be checked.

The iterate declaration this mechanism ports uses **the commit** as its evidence
boundary: everything in it happened during that change. A design feedback round
has no commit — the phase revises mockups and specs in the working tree and
commits, at most, once at the end.

An earlier draft therefore used ``git diff HEAD`` plus ``git ls-files --others``
for design rounds. Adversarial review broke it: in the standard pipeline nothing
commits before the build phase, so every ``.shipwright/planning/<split>/spec.md``
written by the project phase is *untracked*, ``ls-files --others`` lists it, and
**any** ``--impact modify`` was satisfied by a spec nobody had edited. The check
was decorative exactly where part (1) needed it to bite.

A baseline restores the boundary the commit provided. The round snapshots the
requirement specs before it revises anything; the declaration compares. A spec
counts as corrected only if its content actually differs from that snapshot —
which is true whether or not anything has ever been committed, and is the
faithful port of what the commit boundary means.

Baselines live beside the declarations (in a ``_baselines/`` subdirectory, so the
declaration reader's ``*.json`` glob does not see them) and are tracked, which
also gives the completion gate a round registry that does not depend on
gitignored review scratch.

Origin: trg-e9e5188e (FR-01.04).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lib.requirement_impact import PLANNING_ROOT, is_requirement_spec
from lib.requirement_impact_store import declaration_filename

#: Subdirectory of the declaration directory. Nested so ``read_declarations``
#: (a non-recursive ``*.json`` glob) can never mistake a baseline for a record.
BASELINE_SUBDIR = "_baselines"


def baseline_dir(declaration_directory) -> Path:
    return Path(declaration_directory) / BASELINE_SUBDIR


def baseline_path(declaration_directory, *, run_id, phase, scope) -> Path:
    """One baseline per ``(run_id, phase, scope)`` — same identity as the record."""
    return baseline_dir(declaration_directory) / declaration_filename(
        run_id, phase, scope)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_specs(project_root) -> dict[str, str]:
    """Digest every requirement spec currently on disk, keyed by repo-relative path.

    Reads bytes, not text: a spec re-saved in a different encoding is a real
    change, and decoding first would hide it (and could raise).
    """
    root = Path(project_root)
    planning = root / PLANNING_ROOT
    out: dict[str, str] = {}
    if not planning.is_dir():
        return out
    for path in sorted(planning.rglob("spec.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not is_requirement_spec(rel):
            continue
        try:
            out[rel] = _digest(path)
        except OSError:
            continue
    return out


def write_baseline(declaration_directory, *, run_id, phase, scope,
                   project_root) -> dict:
    """Capture and persist the baseline for one round. Returns the payload."""
    payload = {
        "run_id": run_id,
        "phase": phase,
        "scope": scope,
        "specs": snapshot_specs(project_root),
    }
    target = baseline_path(declaration_directory, run_id=run_id, phase=phase,
                           scope=scope)
    target.parent.mkdir(parents=True, exist_ok=True)
    from lib.atomic_write import durable_atomic_write
    durable_atomic_write(target, json.dumps(payload, indent=2) + "\n")
    return payload


def read_baseline(declaration_directory, *, run_id, phase, scope) -> dict | None:
    """The stored baseline, or ``None`` if this round never snapshotted one.

    A damaged baseline reads as absent **on purpose**: the declaration treats a
    missing baseline as a hard refusal for a behaviour-affecting impact, so
    damage fails closed rather than silently passing.
    """
    path = baseline_path(declaration_directory, run_id=run_id, phase=phase,
                         scope=scope)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def changed_specs_since(baseline: dict, project_root) -> list[str]:
    """Requirement specs whose content differs from the baseline.

    Covers all three ways a round can correct requirements: an edited spec, a
    newly created one, and a removed one.
    """
    recorded = (baseline or {}).get("specs")
    if not isinstance(recorded, dict):
        return []
    current = snapshot_specs(project_root)
    changed = {
        path for path, digest in current.items()
        if recorded.get(path) != digest
    }
    changed |= {path for path in recorded if path not in current}
    return sorted(changed)


def discover_baseline_scopes(declaration_directory, *, run_id,
                             phase) -> tuple[list[str], list[dict]]:
    """Every scope that snapshotted a baseline under this run and phase.

    This is the completion gate's round registry. It is written by the phase
    itself and tracked, unlike the gitignored ``design-feedback-round*.md``
    scratch an earlier draft globbed — where a round exported to a different
    directory, or named with a browser's duplicate-download suffix, simply
    vanished from the gate's view and the phase finalized clean.
    """
    directory = baseline_dir(declaration_directory)
    if not directory.is_dir():
        return [], []
    scopes: list[str] = []
    problems: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            # Loud, not skipped: a round whose baseline is damaged would
            # otherwise vanish from the registry and finalize clean — the very
            # "silent round" the gate exists to catch.
            problems.append({"path": str(path), "error": f"unreadable: {exc}"})
            continue
        if not isinstance(data, dict):
            problems.append({"path": str(path), "error": "not a JSON object"})
            continue
        if data.get("run_id") == run_id and data.get("phase") == phase:
            scope = data.get("scope")
            if isinstance(scope, str) and scope.strip():
                scopes.append(scope)
            else:
                problems.append({"path": str(path), "error": "no usable scope"})
    return sorted(set(scopes)), problems
