"""Where Step 3.4's diff-risk-recheck result is persisted, and how it is written.

Split from ``diff_risk_recheck.py`` (which keeps detection + the `recheck()`
decision) so neither file crosses the 300-line rule — the same reason
``ci_supplychain_ack_store.py`` is its own module, split from
``ci_supplychain.py``.

Without this artifact, the runner contract's "F5c MUST record this value"
(Step 3.4) was prose nobody checked: the F11 verifier
`shared/scripts/tools/verifiers/risk_recheck_recording.py` needs a durable,
committed home for what this step computed to compare against the F5c-recorded
complexity. It is written here (pre-Finalization) rather than folded into
`result.json` (Step 6) because the runner's own F6-verify call to that F11
verifier runs *before* `result.json` exists (Step 4 precedes Step 6), and
`result.json` itself is never committed (local orchestrator state under
`.shipwright/runs/`). This file mirrors `ci_supplychain_ack.json`: a durable,
per-run, tracked file beside `reviews.json`, staged by F6's existing
directory-level add.

This proves TRANSCRIPTION integrity (F5c honors what Step 3.4 computed), not
independent re-verification — a runner could still edit this file itself
before F6. Closing that residual would need an independently reproducible
fingerprint or a re-run of the detectors at F11, out of scope here (external
plan review, 2026-08-05): every other runner-contract step is
contract-enforced rather than independently gated, and this is not a new
category of that gap.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: Self-contained copy of ``shared/scripts/lib/review_record_schema.is_safe_run_id``.
#: This plugin-lib module deliberately never imports ``shared/`` at runtime — the
#: installed plugin cache does not guarantee ``shared/`` is reachable at a known
#: relative path (precedent: ``session_plan.RUN_ID_STRICT``) — so the rule is
#: copied, not imported. ``test_is_safe_run_id_sync_with_shared_precedent`` pins
#: this against the shared original; only tests may cross-import both sides.
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_RUN_ID_CHARS = 128

#: Bumped only on an incompatible shape change; the F11 reader
#: (`shared/scripts/tools/verifiers/risk_recheck_recording.py`) rejects any
#: other value rather than guessing at an unknown shape.
RECHECK_SCHEMA_VERSION = 1


def is_safe_run_id(run_id) -> bool:
    if not isinstance(run_id, str):
        return False
    if not (0 < len(run_id) <= _MAX_RUN_ID_CHARS):
        return False
    if run_id in (".", ".."):
        return False
    return bool(_SAFE_RUN_ID_RE.match(run_id))


def _planning_iterate_root(project_root: Path) -> Path:
    return (Path(project_root) / ".shipwright" / "planning" / "iterate").resolve()


def recheck_record_path(project_root: Path, run_id: str) -> Path:
    """Where this run's Step 3.4 result is persisted — beside `ci_supplychain_ack.json`
    and `reviews.json`, so F6's existing directory-level add ships it in the PR."""
    return (Path(project_root) / ".shipwright" / "planning" / "iterate"
            / run_id / "risk_recheck.json")


def write_recheck_record(project_root: Path, run_id: str, result: dict) -> Path:
    """Persist this run's `recheck()` result. See module docstring for why.

    Raises ``ValueError`` for an unsafe `run_id` and ``OSError`` for a write
    failure (incl. a `<run_id>` directory that resolves OUTSIDE the planning
    tree — a symlink planted there before this call — and a target that
    exists but is not a regular file). Both are caught by
    `diff_risk_recheck.main()`; whether that changes the CLI's exit code
    depends on which path was in progress (see that module — external code
    review, 2026-08-05: a write failure must not silently degrade the
    continue path into an undetectable no-op, but must also not overwrite an
    already-decided CI-escalation's exit code).
    """
    if not is_safe_run_id(run_id):
        raise ValueError(
            f"run id {run_id!r} is not a single safe path component — it "
            "becomes a directory name under .shipwright/planning/iterate/"
        )
    path = recheck_record_path(project_root, run_id)
    root = _planning_iterate_root(project_root)
    try:
        path.parent.resolve().relative_to(root)
    except ValueError:
        raise OSError(
            f"{path.parent} resolves outside {root} — refusing to write "
            "through what a symlinked run directory would make an escape"
        ) from None
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OSError(f"{path} exists but is not a regular file")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(
        {"schema_version": RECHECK_SCHEMA_VERSION, "run_id": run_id, "risk_recheck": result},
        indent=2, ensure_ascii=False,
    ) + "\n"
    # with_name, not with_suffix: with_suffix REPLACES the final suffix, which
    # only happens to be correct while the filename has exactly one dot.
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path
