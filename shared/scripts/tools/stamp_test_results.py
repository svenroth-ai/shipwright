#!/usr/bin/env python3
"""Stamp ``shipwright_test_results.json`` with the state it describes.

Call site 1 of the artifact-state stamp (card ``trg-4d5b6a56``, FR-01.10). The
test-results record was not bound to the code version it describes: the phase gate
checks the record exists and was not produced outside the pipeline, but not that it
*describes the code being checked* — so a record left over from an earlier commit
satisfied it.

Run this immediately after the record is written::

    stamp_test_results.py --project-root . --run-id "<run id>"

Deliberately a post-write tool, and the reason is worth stating: the record is
produced by a **prompt** (a heredoc in ``plugins/shipwright-test/agents/test-runner.md``,
a ``Write`` at iterate F5), so there is no Python writer to inject into. External
review flagged post-processing as the weaker option — correct in general, and
unavailable here.

Reach, stated exactly. ``commit`` and ``dirty`` are resolved from git by this tool
and cannot be dictated by the caller — they are what bind the record to a code
version. ``run_id`` is **declared** via ``--run-id`` (falling back to
``shipwright_run_config.json::run_id``): the run knows its own id, and the tool
cannot independently verify it, so a caller that declares the wrong one is not
caught — only a *disagreement between the two sources* is warned about. Detecting a
wrong-but-plausible id needs a gate, which belongs to sibling card ``trg-12b4cf3f``.
Said plainly because the campaign's verdict on the neighbouring ``mode: standalone``
field was that "stamping that field is instruction, not code. A run that omits it
passes as pipeline results" — repeating that overclaim here would be the same bug.

Nothing here enforces the stamp. A gate that refuses an unstamped or mismatched
record belongs to sibling card ``trg-12b4cf3f``, which owns the test-phase
validator branch. A run that skips this tool leaves a record with **no**
``source_state`` — honestly absent rather than falsely stamped.

Shares its whole shape with the compliance renderers via ``shared/scripts/source_state.py``;
this file adds only the file I/O and the run-id fallback. Mirrors
``record_coverage_total.py`` — the other isolated writer of this same file —
including its canonical ``indent=2`` + trailing-newline form, so the two cannot
fight over formatting on every run.

Exit codes: ``0`` stamped · ``1`` the record is missing, unreadable, or not a JSON
object (nothing is written — an unreadable record must survive rather than be
replaced by a near-empty one carrying only a stamp).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_TOOLS_ROOT = Path(__file__).resolve().parent
_SCRIPTS_ROOT = _TOOLS_ROOT.parent
for _p in (str(_SCRIPTS_ROOT.parent), str(_SCRIPTS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.atomic_write import durable_atomic_write  # noqa: E402
from source_state import (  # noqa: E402
    BLOCK_KEY, SHORT_SHA_LEN, UNKNOWN_RUN, resolve_git_state, safe_run_id, to_block,
)

RESULTS_REL = "shipwright_test_results.json"
RUN_CONFIG_REL = "shipwright_run_config.json"


def _run_id_from_config(project_root: Path) -> str | None:
    """Fallback run id from ``shipwright_run_config.json``. Absent/corrupt → ``None``.

    A corrupt run config must not stop the record from being stamped with what IS
    resolvable — the alternative is an unstamped record, which is strictly worse.
    """
    config = project_root / RUN_CONFIG_REL
    if not config.exists():
        return None
    try:
        data = json.loads(config.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return safe_run_id(data.get("run_id")) if isinstance(data, dict) else None


def _record_run_id(record: dict[str, Any]) -> str | None:
    """Run id the record itself already claims, from ``iterate_latest.run_id``."""
    latest = record.get("iterate_latest")
    return safe_run_id(latest.get("run_id")) if isinstance(latest, dict) else None


def _resolve_run_id(
    supplied: str | None, project_root: Path, record: dict[str, Any]
) -> str | None:
    """Resolve the run id to stamp, distinguishing *absent* from *rejected*.

    Precedence: a usable ``--run-id`` wins; otherwise the run config is consulted —
    but **only when no ``--run-id`` was supplied at all**. A supplied-but-unusable
    value (the realistic case being an unsubstituted ``{run_id}`` from a prompt) must
    NOT fall through to the run config: in an iterate that field legitimately holds a
    different, older pipeline run id, so falling back would replace an obviously
    broken value with a plausible wrong one — the opposite of what AC7 asks for.

    Two disagreements are warned about, because both mean a wrong id is about to be
    stamped and neither is detectable later:

    * against the record's own ``iterate_latest.run_id`` — this catches the wrong-tree
      case (``--project-root`` pointing at the main repo from a worktree);
    * against the run config — informational only, since an iterate run id differing
      from the pipeline's is normal, so this is not raised when the record already
      agrees with the declared value.
    """
    raw_supplied = supplied is not None and supplied.strip() != ""
    declared = safe_run_id(supplied)

    if raw_supplied and declared is None:
        sys.stderr.write(
            f"stamp_test_results: WARNING --run-id {supplied!r} is not a usable run id "
            f"(whitespace, control character, or an unsubstituted placeholder); "
            f"stamping run_id=null rather than a fallback that would look plausible.\n"
        )
        return None

    if declared is None:
        return _run_id_from_config(project_root)

    in_record = _record_run_id(record)
    if in_record and in_record != declared:
        sys.stderr.write(
            f"stamp_test_results: WARNING --run-id {declared!r} disagrees with the "
            f"record's own iterate_latest.run_id {in_record!r} — is --project-root the "
            f"tree this record was written to?\n"
        )
    elif in_record is None:
        from_config = _run_id_from_config(project_root)
        if from_config and from_config != declared:
            sys.stderr.write(
                f"stamp_test_results: note --run-id {declared!r} differs from "
                f"{RUN_CONFIG_REL}::run_id {from_config!r} (normal for an iterate).\n"
            )
    return declared


def load_record(path: Path) -> dict[str, Any]:
    """Read the record, or raise ``ValueError`` describing why it is unusable."""
    if not path.exists():
        raise ValueError(f"{path} does not exist — nothing to stamp")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"{path} is unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is a {type(data).__name__}, not a JSON object")
    return data


def merge_source_state(existing: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
    """Return ``existing`` with ``source_state`` set, every other key untouched.

    Idempotent by replacement: a prior block (even a garbage one) is overwritten
    rather than merged into or nested, so running twice equals running once. Key
    order is preserved and the stamp appends on first write.
    """
    out = dict(existing)
    out[BLOCK_KEY] = block
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Stamp the test-results record with the state it describes.")
    ap.add_argument("--project-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--run-id", default=None,
                    help=f"iterate/pipeline run id (default: <root>/{RUN_CONFIG_REL}::run_id)")
    ap.add_argument("--results", default=None,
                    help=f"record to stamp (default: <root>/{RESULTS_REL})")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()

    results = Path(args.results) if args.results else project_root / RESULTS_REL
    if not results.is_absolute():
        results = project_root / results

    try:
        record = load_record(results)
    except ValueError as exc:
        sys.stderr.write(f"stamp_test_results: {exc}\n")
        return 1

    run_id = _resolve_run_id(args.run_id, project_root, record)

    # The record is excluded from the dirty calculation because this runs AFTER it
    # was written — without the exclusion `dirty` would be True on every run and
    # would carry no information at all. Passed ABSOLUTE: `resolve_git_state`
    # re-expresses it against the repo root, which is what git prints, so the
    # exclusion still matches when --project-root is a subdirectory of the repo.
    state = resolve_git_state(
        project_root, run_id=run_id, exclude_paths=(str(results.resolve()),)
    )

    block = to_block(state)
    durable_atomic_write(results, json.dumps(merge_source_state(record, block), indent=2) + "\n")
    print(
        f"stamp_test_results: run={block['run_id'] or UNKNOWN_RUN} "
        f"commit={(block['commit'] or UNKNOWN_RUN)[:SHORT_SHA_LEN]} "
        f"dirty={block['dirty']} -> {results}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
