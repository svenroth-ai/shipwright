#!/usr/bin/env python3
"""What one warning-layer follow-up looks like.

Split from ``warning_followups`` (which reads the record and orchestrates) so
each file stays inside the 300-line guideline: this one owns the wording,
severity and dedup key of each item; the other owns when they are emitted.

Every emitter takes the ``append`` seam as its first argument so the durability
policy — no commit matching, no recency window, bounded strings — is set in
exactly one place.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

Append = Callable[..., "str | None"]


def emit_e2e(append: Append, root: Path, summary: dict, run_id, commit) -> int:
    """One item per spec file with genuine failures — not one per assertion.

    Failures listed in the accepted-baseline file are already gone from
    ``genuine``; they are known-and-accepted, not new work.
    """
    by_file: dict[str, list[str]] = {}
    for name in summary["e2e"]["genuine"]:
        file, _, title = name.partition(" › ")
        by_file.setdefault(file or "(unknown spec)", []).append(title or name)

    appended = 0
    for file, titles in by_file.items():
        listed = ", ".join(titles[:5]) + (" …" if len(titles) > 5 else "")
        new_id = append(
            root, source="test-warning", severity="high", kind="bug",
            title=f"[test] browser tests failing in {file}",
            detail=(
                f"{len(titles)} failing browser test(s) in {file}: {listed}. "
                f"Browser tests warn without stopping the run, so this would "
                f"otherwise leave no trace once the session ends. Closes when "
                f"the spec passes again."
            ),
            dedup_key=f"test-warning:e2e:{file}",
            run_id=run_id, commit=commit,
        )
        if new_id is not None:
            appended += 1
    return appended


def emit_flaky(append: Append, root: Path, summary: dict, run_id, commit) -> int:
    """A test that only passed on retry: still a pass, still non-blocking, but
    visible — so one that has needed a retry for weeks surfaces before it fails
    for good."""
    appended = 0
    for test in summary["e2e"]["flaky_tests"]:
        if not isinstance(test, dict):
            continue
        file = str(test.get("file", "")).strip() or "(unknown spec)"
        title = str(test.get("title", "")).strip() or "(unnamed test)"
        retries = test.get("retries", 0)
        new_id = append(
            root, source="test-warning", severity="low", kind="improvement",
            title=f"[test] passes only on retry: {title}",
            detail=(
                f"{file} › {title} failed and then passed after {retries} "
                f"retr{'y' if retries == 1 else 'ies'}. It is still a pass and "
                f"does not block; it is tracked so a test that has needed a "
                f"retry for weeks becomes visible before it fails for good."
            ),
            dedup_key=f"test-warning:flaky:{file}::{title}",
            run_id=run_id, commit=commit,
        )
        if new_id is not None:
            appended += 1
    return appended


def emit_consistency(append: Append, root: Path, summary: dict, run_id, commit) -> int:
    appended = 0
    for category in summary["consistency"]["inconsistent_categories"]:
        new_id = append(
            root, source="test-warning", severity="medium", kind="improvement",
            title=f"[test] cross-page inconsistency: {category}",
            detail=(
                f"The {category} category is used one way on most pages and "
                f"differently on a few. Non-blocking, so it would otherwise "
                f"leave no trace once the session ends."
            ),
            dedup_key=f"test-warning:consistency:{category}",
            run_id=run_id, commit=commit,
        )
        if new_id is not None:
            appended += 1
    return appended


def emit_fidelity(append: Append, root: Path, summary: dict, run_id, commit) -> int:
    appended = 0
    for screen in summary["design_fidelity"]["diverging_screens"]:
        label = screen or "(unnamed screen)"
        new_id = append(
            root, source="test-warning", severity="medium", kind="improvement",
            title=f"[test] screen diverges from its mockup: {label}",
            detail=(
                f"{label} did not match its mockup on the structural checks and "
                f"needs review. Non-blocking, so it would otherwise leave no "
                f"trace once the session ends."
            ),
            dedup_key=f"test-warning:fidelity:{label}",
            run_id=run_id, commit=commit,
        )
        if new_id is not None:
            appended += 1
    return appended


_AGGREGATE_LAYERS = (
    ("e2e", "browser tests"),
    ("consistency", "cross-page consistency"),
    ("design_fidelity", "screen-vs-mockup fidelity"),
)


def emit_unidentified(append: Append, root: Path, summary: dict, run_id, commit) -> int:
    """One item per layer that reported a failure it could not itemize.

    A record may say a layer failed through counts alone (``passed < total``,
    or an explicit ``failed``) without the per-finding arrays the emitters
    above read. That is still a reported failure, and a reported failure has to
    outlive the session — otherwise AC3 holds only for records that happen to
    carry the optional detail. Caught by external code review on the delivered
    head.

    The item says plainly that no per-finding identities were available, so
    nothing was matched against the accepted-failure list. Claiming otherwise
    would be the same overclaim this iterate exists to remove.
    """
    appended = 0
    for key, label in _AGGREGATE_LAYERS:
        layer = summary.get(key) or {}
        if not layer.get("unidentified_failure"):
            continue
        counts = layer.get("counts") or {}
        passed, total = counts.get("passed"), counts.get("total")
        tally = f"{passed}/{total} passing" if isinstance(total, int) else "counts unavailable"
        new_id = append(
            root, source="test-warning", severity="medium", kind="bug",
            title=f"[test] {label} reported a failure ({tally})",
            detail=(
                f"The {label} layer reported a failure ({tally}) but the record "
                f"carries no per-finding detail, so this could not be broken "
                f"down and nothing was matched against the accepted-failure "
                f"list. Non-blocking, so it would otherwise leave no trace once "
                f"the session ends. Re-run the layer to get itemized findings."
            ),
            dedup_key=f"test-warning:{key}:layer",
            run_id=run_id, commit=commit,
        )
        if new_id is not None:
            appended += 1
    return appended


EMITTERS = (emit_e2e, emit_flaky, emit_consistency, emit_fidelity, emit_unidentified)

__all__ = [
    "EMITTERS",
    "emit_consistency",
    "emit_e2e",
    "emit_fidelity",
    "emit_flaky",
    "emit_unidentified",
]
