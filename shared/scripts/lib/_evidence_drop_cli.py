"""``evidence_drop`` CLI arg-parsing/validation leg (split for the 300-LOC guideline).

Pure functions only — no filesystem writes, no provenance/staging logic (that stays
in ``evidence_drop`` itself). Split out rather than grown in place once the Stage-3
review fix (``_missing_named_sources``) pushed the combined file over the limit.

Imported both ways (ADR-045-style dual-form, mirroring ``backfill_signals.py`` /
``_backfill_fold.py``): flat when ``evidence_drop.py`` is executed directly as a
script (``uv run shared/scripts/lib/evidence_drop.py ...`` puts this directory on
``sys.path``), relative when imported as ``lib.evidence_drop``.
"""

from __future__ import annotations

from pathlib import Path


def parse_junit_args(values: list[str]) -> list[tuple[str, str]]:
    """Parse repeated ``--junit`` CLI values into ``[(base, path), ...]`` (E-B/E-C).

    Each value is either ``<path>`` (bare — legacy single-report form, base = project
    root ``""``) or ``<base>=<path>`` (E-B repeatable multi-root form). Bare is ONLY
    accepted when it is the SOLE ``--junit``; with 2+, every value needs an explicit
    ``base=`` (empty base spelled ``=<path>``) — a bare path among 2+ is REJECTED, not
    silently defaulted (AC: "ein Report ohne Basis wird abgelehnt").

    A **duplicate base is legal and common** — this repo alone has FOUR roots that all
    rebase at base ``""`` (Stage-2 review: rejecting a repeated base broke the workflow
    E-B exists for, and disagreed with the ``stage_reports`` API, which never rejected
    it). Staged entries are an ORDERED LIST — nothing is keyed by base, so nothing
    silently overwrites a same-base sibling. What IS rejected: an exact duplicate
    ``(base, path)`` pair, or the same source ``path`` twice — both a copy-paste mistake.
    """
    if not values:
        return []
    if len(values) == 1 and "=" not in values[0]:
        return [("", values[0])]
    parsed: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    for raw in values:
        if "=" not in raw:
            raise SystemExit(
                f"--junit {raw!r}: a base is required once more than one --junit is given "
                "(use --junit <base>=<path>; an explicit empty base is --junit =<path>)"
            )
        base, _, path = raw.partition("=")
        if (base, path) in seen_pairs:
            raise SystemExit(f"--junit: duplicate --junit {base!r}={path!r} given twice")
        if path in seen_paths:
            raise SystemExit(f"--junit: the same source path {path!r} was given more than once")
        seen_pairs.add((base, path))
        seen_paths.add(path)
        parsed.append((base, path))
    return parsed


def missing_named_sources(
    junit_reports: list[tuple[str, str]], playwright: str | None, vitest: str | None
) -> list[str]:
    """Every NAMED ``--junit``/``--playwright``/``--vitest`` source that does not exist.

    ``stage_reports`` itself skips a missing source silently — right for a
    programmatic caller like ``run_full_suite_evidence.stage_all``, which already
    filtered to roots it KNOWS produced a report. The CLI is different: every path
    here was NAMED BY A HUMAN, so missing means typo, not a legitimate skip —
    Stage-3 review found the CLI staged nothing and exited 0 on a typo (same bug
    class already fixed for ``--head-commit`` defaulting to empty).
    """
    missing = [path for _, path in junit_reports if not Path(path).is_file()]
    for src in (playwright, vitest):
        if src is not None and not Path(src).is_file():
            missing.append(src)
    return missing


__all__ = ["parse_junit_args", "missing_named_sources"]
