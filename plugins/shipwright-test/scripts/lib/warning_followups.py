#!/usr/bin/env python3
"""Durable follow-ups for the test layers that warn without stopping the run.

Four layers report a failure without blocking: browser tests, cross-page
consistency, screen-vs-mockup fidelity, and the performance budget. Only the
last one left anything behind (``performance_check._emit_failures_to_triage``);
the other three warned to stdout and evaporated at session end, so a suite that
had been failing for six weeks looked exactly like one that broke this morning.

This extends the same pattern to the other three, driven by the record the
phase already writes — ``shipwright_test_results.json``. Reading the finished
record rather than inventing per-layer sidecar files keeps one source of truth
(and makes the emitter re-runnable over an existing record).

Two deliberate differences from the performance producer:

* ``match_commit=False`` + ``window_seconds=None``. A budget overrun is a
  property of a commit; a persistently broken suite is **one issue until
  somebody fixes it**. With commit matching, a red suite would file a fresh
  item on every commit — the opposite of "a persistent failure does not
  multiply".
* Failures listed in ``shipwright_known_failures.json`` are reported as
  known-and-accepted and file nothing. They are not new work.

Emission is best-effort: it never raises into the phase and never changes an
exit code. A warning layer must not become blocking through its own
bookkeeping.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.

Usage:
    uv run warning_followups.py --project-root . [--results-file PATH] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from text_safety import sanitize  # noqa: E402 — same normalization both producers use
from warning_followup_items import EMITTERS  # noqa: E402

RESULTS_NAME = "shipwright_test_results.json"
_TITLE_CAP = 160
_DETAIL_CAP = 2000


def _append(project_root: Path, **kwargs) -> str | None:
    """Thin seam over the triage writer — patched in tests, and the single
    place the durability policy (no commit matching, no window) is set."""
    from triage import append_triage_item_idempotent  # noqa: PLC0415

    kwargs.setdefault("match_commit", False)
    kwargs.setdefault("window_seconds", None)
    kwargs.setdefault("fr_id", "FR-01.06")
    # Test titles, spec paths, category and screen names are authored
    # elsewhere and land verbatim in the record; normalize before both the
    # write and the dedup key (external code review, R8/C3).
    kwargs["title"] = sanitize(str(kwargs.get("title", "")))[:_TITLE_CAP]
    kwargs["detail"] = sanitize(str(kwargs.get("detail", "")))[:_DETAIL_CAP]
    kwargs["dedup_key"] = sanitize(str(kwargs.get("dedup_key", "")))
    return append_triage_item_idempotent(project_root, **kwargs)


def _read_results(project_root: Path, results_file: Path | None = None) -> dict:
    path = results_file or (project_root / RESULTS_NAME)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _layer(results: dict, name: str) -> dict:
    """The layer's block, or ``{}`` when the layer did not run.

    ``skipped`` carries two meanings in this record and they must not be
    conflated: the **boolean flag** `skipped: true` means *this layer never
    ran* (paired with a `skip_reason`), while an **integer** `skipped: 3` is a
    count of skipped tests inside a layer that did run. Treating the count as
    the flag discarded a layer that ran and had real failures alongside skips.
    """
    block = results.get(name)
    if not isinstance(block, dict):
        return {}
    if block.get("skipped") is True:
        return {}
    return block


def _e2e_failure_names(e2e: dict) -> list[str]:
    """``file › title`` for each reported browser-test failure."""
    names = []
    for failure in e2e.get("failures") or []:
        if not isinstance(failure, dict):
            continue
        file = str(failure.get("file", "")).strip()
        title = str(failure.get("title", "")).strip()
        names.append(f"{file} › {title}" if file else title)
    return [n for n in names if n]


def _layer_failed(layer: dict) -> bool:
    """Did this layer report a **failure**, however coarsely?

    A record may say a layer failed through counts alone — `passed < total`, or
    an explicit `failed` — without the per-finding arrays. That is still a
    reported failure, and AC3 says a reported failure outlives the session. The
    identity-driven emitters cannot see it, so this predicate drives the
    aggregate fallback (external code review on the delivered head).

    **A skipped test is not a failure.** Delegates the arithmetic to
    `known_failures.genuine_failure_count`, the same SSoT the validator uses,
    so a fully-skipped layer (`{"passed": 0, "skipped": 3, "total": 3}`) cannot
    become a persistent false follow-up. Filing one would be worse than the gap
    it closes: it teaches the operator to ignore triage, which is this card's
    own thesis turned on its head.
    """
    from known_failures import genuine_failure_count  # noqa: PLC0415

    passed, total = layer.get("passed"), layer.get("total")
    if not isinstance(passed, int) or not isinstance(total, int) or total <= 0:
        failed = layer.get("failed")
        return isinstance(failed, int) and not isinstance(failed, bool) and failed > 0

    skipped = layer.get("skipped")
    return genuine_failure_count(
        passed=passed,
        total=total,
        failed=layer.get("failed"),
        # `skipped` doubles as the layer's skip FLAG; only a count is arithmetic.
        skipped=skipped if isinstance(skipped, int) and not isinstance(skipped, bool) else None,
    ) > 0


def summarize_warning_layers(
    project_root: Path | str, results_file: Path | None = None,
) -> dict:
    """What each warning-only layer actually found, accepted split from genuine.

    The accepted split is by **identity** — a declared failure that did not
    fire this run excuses nothing. An unreadable accepted list excuses nothing
    either, and says so.
    """
    from known_failures import load_accepted_baseline, split_accepted  # noqa: PLC0415

    root = Path(project_root)
    results = _read_results(root, results_file)
    baseline = load_accepted_baseline(root)

    e2e = _layer(results, "e2e")
    accepted, genuine = split_accepted(_e2e_failure_names(e2e), baseline)

    consistency = _layer(results, "consistency")
    bad_categories = [
        name for name, cat in (consistency.get("categories") or {}).items()
        if isinstance(cat, dict) and cat.get("status") == "INCONSISTENT"
    ]

    fidelity = _layer(results, "design_fidelity")
    diverging = [
        screen for screen in (fidelity.get("screens") or [])
        if isinstance(screen, dict) and screen.get("status") in ("needs_review", "error")
    ]

    # A layer that reports a failure through counts alone still has to leave a
    # follow-up — the identity emitters see nothing there, so each layer
    # declares whether it needs the aggregate fallback instead.
    return {
        "e2e": {
            "known_accepted": accepted,
            "genuine": genuine,
            "flaky": e2e.get("flaky", 0) or 0,
            "flaky_tests": e2e.get("flaky_tests") or [],
            "unidentified_failure": _layer_failed(e2e) and not (accepted or genuine),
            "counts": {"passed": e2e.get("passed"), "total": e2e.get("total")},
        },
        "consistency": {
            "inconsistent_categories": bad_categories,
            "unidentified_failure": _layer_failed(consistency) and not bad_categories,
            "counts": {"passed": consistency.get("passed"),
                       "total": consistency.get("total")},
        },
        "design_fidelity": {
            "diverging_screens": [s.get("mockup", "") for s in diverging],
            "unidentified_failure": _layer_failed(fidelity) and not diverging,
            "counts": {"passed": fidelity.get("passed"), "total": fidelity.get("total")},
        },
        "accepted_baseline": {
            "present": baseline.present,
            "malformed": baseline.malformed,
            "declared": baseline.baseline_failure_count,
        },
    }


def emit_warning_followups(
    project_root: Path | str,
    *,
    results_file: Path | None = None,
    run_id: str | None = None,
    commit: str | None = None,
) -> int:
    """File one durable follow-up per failing warning-only finding.

    Returns the number of NEW items appended. Errors are logged to stderr and
    swallowed — emission never blocks.
    """
    root = Path(project_root)
    try:
        summary = summarize_warning_layers(root, results_file)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[test-warning] could not read results: {type(exc).__name__}: {exc}\n")
        return 0

    appended = 0
    for emit in EMITTERS:
        try:
            appended += emit(_append, root, summary, run_id, commit)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[test-warning] {emit.__name__} failed: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


def main() -> int:
    parser = argparse.ArgumentParser(
        description="File durable follow-ups for warning-only test layers")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--results-file", default=None,
                        help=f"defaults to <project-root>/{RESULTS_NAME}")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--summary-only", action="store_true",
                        help="report accepted-vs-genuine; file nothing")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    results_file = Path(args.results_file) if args.results_file else None

    summary = summarize_warning_layers(root, results_file)
    appended = 0
    if not args.summary_only:
        appended = emit_warning_followups(
            root, results_file=results_file, run_id=args.run_id, commit=args.commit)

    out = {"summary": summary, "triage_appended": appended}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        e2e = summary["e2e"]
        print(f"Browser tests:   {len(e2e['genuine'])} genuine failure(s), "
              f"{len(e2e['known_accepted'])} known-and-accepted, "
              f"{e2e['flaky']} passed only on retry")
        print(f"Consistency:     {len(summary['consistency']['inconsistent_categories'])} "
              f"inconsistent categor(y/ies)")
        print(f"Design fidelity: {len(summary['design_fidelity']['diverging_screens'])} "
              f"diverging screen(s)")
        if summary["accepted_baseline"]["malformed"]:
            print("  WARNING: shipwright_known_failures.json is unreadable — "
                  "nothing was excused on its strength")
        print(f"Follow-ups filed: {appended}")
    return 0


__all__ = ["emit_warning_followups", "summarize_warning_layers"]


if __name__ == "__main__":
    sys.exit(main())
