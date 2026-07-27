#!/usr/bin/env python3
"""Adopt Step E.18 — record what was inherited, and ask for the catalogue to be
questioned (FR-01.13, trg-1aa5a8ab).

Runs after Step E.17 (which produces the backfill report and the repo-wide skip
inventory) and BEFORE Step F, so the first compliance seeding already sees the
register. It does three things, all about describing the onboarded repository
honestly:

1. writes ``shipwright_known_failures.json`` — inherited failures in the shape
   the audit phase already reads, and inherited coverage gaps beside them;
2. files the follow-up that takes the **derived requirements catalogue** to a
   person, following ``shared/requirement-elicitation.md``. Reading the code is a
   start; it is not enough. This repository is the proof — its own catalogue came
   from onboarding, and a campaign now exists to repair it years later;
3. files one follow-up per non-empty inherited gap class, which is the
   destination a brownfield journey-coverage gap routes to instead of blocking.

**This step is the single owner of triage filing for this feature.** It is the
first step that runs after the Triage Inbox is scaffolded (E.16), so filing from
Step E would write into a store that does not exist yet.

ADR-045 (precise): the only ``lib`` package that binds in THIS interpreter is
``shared/scripts/lib``, and only lazily, when ``triage.append_triage_item_idempotent``
imports ``lib.file_lock`` at call time. The two plugin modules are imported BARE
off ``scripts/lib`` and neither binds a ``lib`` package of its own —
``derived_catalogue`` reaches ``spec_table`` (which does) only from ``summarize``,
which this tool never calls.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import derived_catalogue as dc  # noqa: E402
import derived_catalogue_doc as dcd  # noqa: E402
import inherited_baseline as ib  # noqa: E402
from cli_paths import unquoted_path  # noqa: E402

# plugins/shipwright-adopt/scripts/tools/<file> → parents[4] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]

_BACKFILL_REL = ".shipwright/backfill/backfill-report.json"
_TRACEABILITY_REL = ".shipwright/adopt/traceability-baseline.json"


def _read_optional_json(path: Path, *, written_by: str) -> dict[str, Any]:
    """Read an optional Step E.17 artifact.

    **Absent is fine; present-and-broken is not.** Both inputs are legitimately
    absent — a zero-test repo backfills to nothing, a repo with no rot has no
    inventory — and crashing on that would turn the cleanest possible inheritance
    into an onboarding failure.

    But treating a *corrupt* file as absent would be worse than either: this step
    would silently record every requirement as untested and no test as disabled,
    then file triage cards asserting an inherited state it never actually read
    (external code review). A file that exists and cannot be trusted stops the
    step and names what to re-run.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"ERROR: {path} exists but cannot be read: {exc}\n"
            f"  It is written by {written_by}; fix or delete it and re-run that step."
        ) from exc
    if not isinstance(data, dict):
        raise SystemExit(
            f"ERROR: {path} is not a JSON object (got {type(data).__name__}).\n"
            f"  It is written by {written_by}; fix or delete it and re-run that step."
        )
    return data


def _load_catalogue(project_root: Path) -> dc.DerivedCatalogue:
    """The catalogue Step E wrote. A hard prerequisite, unlike the two above.

    Without it this step cannot know which requirements exist, so every coverage
    gap it reported would be a guess. Fail closed and name the step that writes
    it rather than emitting a confident, empty register.
    """
    path = project_root / dc.SUMMARY_REL
    if not path.exists():
        raise SystemExit(
            f"ERROR: {dc.SUMMARY_REL} is missing at {project_root}.\n"
            "  It is written by Step E (generate_adoption_artifacts.py); run that first."
        )
    doc = _read_optional_json(path, written_by="Step E (generate_adoption_artifacts.py)")
    try:
        return dcd.catalogue_from_document(doc)
    except dcd.CatalogueDocumentError as exc:
        raise SystemExit(
            f"ERROR: {dc.SUMMARY_REL} is not a usable catalogue: {exc}\n"
            "  Re-run Step E (generate_adoption_artifacts.py) to regenerate it."
        ) from exc


def _file_triage(project_root: Path, cards: list[dict[str, Any]], *, dry_run: bool) -> dict:
    """Append every card idempotently to the TRACKED store (ships in Step H).

    ``to_outbox=False`` and ``window_seconds=None``, matching
    ``seed_traceability_baseline._file_triage``: the cards must land in the Step H
    commit so the Inbox shows them from day one, and a re-adopt must never
    duplicate them.
    """
    if dry_run:
        return {"appended": 0, "would_append": len(cards), "dry_run": True}
    sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
    from triage import append_triage_item_idempotent  # noqa: PLC0415

    appended = 0
    for card in cards:
        new_id = append_triage_item_idempotent(
            project_root, source="adopt-inherited-baseline",
            severity=card["severity"], kind=card["kind"], title=card["title"],
            detail=card["detail"], dedup_key=card["dedup_key"], fr_id=card.get("fr_id"),
            window_seconds=None, to_outbox=False,
        )
        if new_id:
            appended += 1
    return {"appended": appended, "candidates": len(cards)}


def run(
    project_root: Path, *, failures_path: Path | None, dry_run: bool,
) -> dict[str, Any]:
    catalogue = _load_catalogue(project_root)

    observed = None
    if failures_path is not None:
        try:
            payload = json.loads(failures_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"ERROR: cannot read --failures-json {failures_path}: {exc}") from exc
        try:
            observed = ib.parse_observed_failures(payload)
        except ib.BaselineInputError as exc:
            # Fails closed: a payload we cannot trust must not become an empty
            # register, because empty reads as a clean inheritance.
            raise SystemExit(f"ERROR: --failures-json is not a usable baseline: {exc}") from exc

    e17 = "Step E.17 (seed_traceability_baseline.py)"
    register = ib.build_register(
        fr_ids=[r.fr_id for r in catalogue.requirements],
        backfill_report=_read_optional_json(project_root / _BACKFILL_REL, written_by=e17),
        skip_inventory=list(
            (_read_optional_json(project_root / _TRACEABILITY_REL, written_by=e17)
             .get("skip_inventory") or {}).get("findings") or []
        ),
        observed=observed,
        adopted_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
    )

    cards: list[dict[str, Any]] = []
    if (confirm := dc.confirmation_triage(catalogue, split_name=catalogue.split_name)):
        cards.append(confirm)
    cards.extend(ib.gap_triage(register))
    triage_result = _file_triage(project_root, cards, dry_run=dry_run)

    summary = {
        "schema_version": 1,
        "derived_requirements": catalogue.total,
        "unconfirmed_requirements": catalogue.unconfirmed,
        "baseline_observed": register["baseline_observed"],
        "baseline_failure_count": register["baseline_failure_count"],
        "inherited_coverage_gaps": register["inherited_coverage_gaps"]["counts"],
        "confirmation_dedup_key": dc.CONFIRMATION_DEDUP_KEY,
        "triage": triage_result,
        "dry_run": dry_run,
    }
    if not dry_run:
        ib.write_register(project_root, register)
        summary["written"] = ib.REGISTER_REL
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Adopt Step E.18 — inherited baseline + catalogue-confirmation follow-up",
    )
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    parser.add_argument(
        "--failures-json", type=unquoted_path, default=None,
        help="An OBSERVED baseline test run: {source, command, failing_tests[]}. "
             "Omit when no run was made — the register then records "
             "`baseline_observed: false` rather than a confident zero.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only: no register, no triage")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(json.dumps({"success": False, "error": f"not a directory: {project_root}"}))
        return 1

    summary = run(project_root, failures_path=args.failures_json, dry_run=args.dry_run)
    print(json.dumps({"success": True, **summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
