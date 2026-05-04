"""boundary_coverage_report — Sub-Iterate D / ADR-027.

Scans `.shipwright/planning/iterate/**/*.md` for `## Affected Boundaries`
sections (introduced by Sub-Iterate A, ADR-024), correlates each spec
with commits in `shipwright_events.jsonl`, and emits a coverage report
in markdown + JSON.

Findings:
- Specs whose changed-files in the corresponding commit match
  `is_io_boundary_change()` BUT lack an `## Affected Boundaries` section
  are flagged as **drift signals** — likely missed boundary declarations.
- For each declared boundary, a heuristic round-trip-test detector
  scans test files for the producer's bare name; presence flips
  `round_trip_tested = True`.

CLI:
  uv run plugins/shipwright-test/scripts/tools/boundary_coverage_report.py \
    --project-root . \
    --output-markdown .shipwright/test-reports/boundary-coverage-YYYY-MM-DD.md \
    --output-json shipwright_test_results.json#boundary_coverage_report

Used by:
- `/shipwright-test` flag `--report-boundary-coverage` (documented in
  `plugins/shipwright-test/skills/test/SKILL.md`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Bring in is_io_boundary_change from the iterate plugin (ADR-024).
# ---------------------------------------------------------------------------
_REPO_ROOT_GUESS = Path(__file__).resolve().parents[4]
_ITERATE_LIB = _REPO_ROOT_GUESS / "plugins" / "shipwright-iterate" / "scripts" / "lib"
if str(_ITERATE_LIB) not in sys.path:
    sys.path.insert(0, str(_ITERATE_LIB))

try:
    from classify_complexity import is_io_boundary_change  # type: ignore
except Exception:  # pragma: no cover — fallback if iterate plugin missing
    def is_io_boundary_change(changed_files):  # type: ignore
        if not changed_files:
            return False
        patterns = (
            r"(^|/)\.env(\..+)?$",
            r"(^|/)hooks\.json$",
            r"(^|/)settings\.json$",
            r"(^|/)[^/]*_config\.json$",
            r"(^|/)[^/]*_state\.json$",
        )
        for path in changed_files:
            normalized = path.replace("\\", "/")
            for pattern in patterns:
                if re.search(pattern, normalized):
                    return True
        return False


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Boundary:
    """One row of the `## Affected Boundaries` table."""

    producer: str
    consumer: str
    format: str

    def to_dict(self) -> dict:
        return {"producer": self.producer, "consumer": self.consumer, "format": self.format}


@dataclass
class SpecBoundaries:
    """Boundaries declared by a single iterate spec (zero or more rows)."""

    spec_path: Path
    boundaries: list[Boundary] = field(default_factory=list)


@dataclass
class BoundaryResult:
    """A boundary plus detected round-trip-test status.

    `round_trip_tested` semantics (E spec HIGH-5):
    - True: a test file in the matched commit's `changed_files` mentions
      the producer.
    - False: the matched commit's `changed_files` are present, but no
      test file in that intersection mentions the producer.
    - "unknown": the matched commit lacks a `changed_files` field on the
      event (legacy events from before MEDIUM-D1). Falls back to the
      old full-walk heuristic for the value, but exposes "unknown" so
      consumers can distinguish "we don't have evidence either way"
      from "we looked and found nothing".
    """

    boundary: Boundary
    round_trip_tested: bool | str  # True | False | "unknown"

    def to_dict(self) -> dict:
        return {
            **self.boundary.to_dict(),
            "round_trip_tested": self.round_trip_tested,
        }


@dataclass
class CoverageRow:
    """One row of the coverage report — one iterate spec."""

    spec_path: Path
    boundary_results: list[BoundaryResult]
    commits: list[str]
    drift_signal: bool
    drift_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "spec_path": str(self.spec_path),
            "boundaries": [br.to_dict() for br in self.boundary_results],
            "commits": list(self.commits),
            "drift_signal": self.drift_signal,
            "drift_reason": self.drift_reason,
        }


# ---------------------------------------------------------------------------
# Markdown table parser
# ---------------------------------------------------------------------------

# Heading: literal "## Affected Boundaries" with optional trailing whitespace.
_HEADING_RE = re.compile(r"^##\s+Affected Boundaries\s*$")
# Next H2 (any). Used to bound the section.
_NEXT_H2_RE = re.compile(r"^##\s+\S")
# Table separator row like |---|---|---| or |:--|:-:|--:|
_SEPARATOR_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def _read_text_lenient(path: Path) -> str:
    """Read file text, stripping a UTF-8 BOM if present and normalizing CRLF."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    # Normalize CRLF and lone CR — the parser splits on \n only after this.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _split_table_row(line: str) -> list[str] | None:
    """Split a markdown table row into trimmed cells.

    Returns None if the line is not a table row (no leading/trailing pipes
    and no internal pipes).
    """
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    # Drop the leading/trailing pipes, split, strip cells.
    inner = stripped[1:-1]
    cells = [c.strip() for c in inner.split("|")]
    return cells


def parse_affected_boundaries(spec_path: Path) -> list[Boundary]:
    """Extract Boundary rows from the `## Affected Boundaries` section.

    Tolerant of:
    - UTF-8 BOM
    - CRLF line endings
    - Whitespace inside cells
    - Markdown alignment markers in the separator row (|:--|:-:|--:|)
    - Section present but empty (no table) → returns []
    - Section absent → returns []
    """
    if not spec_path.exists():
        return []
    text = _read_text_lenient(spec_path)
    lines = text.split("\n")
    in_section = False
    table_rows: list[list[str]] = []
    for line in lines:
        if _HEADING_RE.match(line):
            in_section = True
            continue
        if in_section and _NEXT_H2_RE.match(line):
            break
        if not in_section:
            continue
        if _SEPARATOR_RE.match(line):
            continue
        cells = _split_table_row(line)
        if cells is None:
            continue
        table_rows.append(cells)

    # First table row is the header (Producer | Consumer | Format).
    # We tolerate the header having a different case / wording — we just
    # require >=3 columns and skip it.
    boundaries: list[Boundary] = []
    if not table_rows:
        return []
    # Skip the header row (the first one).
    data_rows = table_rows[1:]
    for cells in data_rows:
        if len(cells) < 3:
            continue
        producer, consumer, fmt = cells[0], cells[1], cells[2]
        if not producer and not consumer and not fmt:
            continue
        boundaries.append(Boundary(producer=producer, consumer=consumer, format=fmt))
    return boundaries


def _render_boundaries_table(boundaries: Iterable[Boundary]) -> str:
    """Render a list of Boundary rows back to a markdown table."""
    lines = ["| Producer | Consumer | Format |", "|---|---|---|"]
    for b in boundaries:
        lines.append(f"| {b.producer} | {b.consumer} | {b.format} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# scan_specs — walk planning/iterate/**
# ---------------------------------------------------------------------------


def _iterate_planning_dir(project_root: Path) -> Path:
    return project_root / ".shipwright" / "planning" / "iterate"


def scan_specs(project_root: Path) -> list[SpecBoundaries]:
    """Walk `.shipwright/planning/iterate/**/*.md` and parse each spec."""
    root = _iterate_planning_dir(project_root)
    if not root.exists():
        return []
    specs: list[SpecBoundaries] = []
    for spec_path in sorted(root.rglob("*.md")):
        boundaries = parse_affected_boundaries(spec_path)
        specs.append(SpecBoundaries(spec_path=spec_path, boundaries=boundaries))
    return specs


# ---------------------------------------------------------------------------
# correlate_with_commits — drift signal + round-trip heuristic
# ---------------------------------------------------------------------------


def _load_events(events_path: Path) -> list[dict]:
    if not events_path.exists():
        return []
    events: list[dict] = []
    try:
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return events


def _spec_slug(spec_path: Path) -> str:
    """A loose slug used to match spec → event description."""
    return spec_path.stem.lower()


def _slug_matches_description(slug: str, description: str) -> bool:
    """Return True iff `slug` is a meaningful match in `description`.

    E spec HIGH-6: short slugs (e.g. `A.md`, `r1.md`) cause false-positive
    matches against arbitrary commit descriptions. Apply a length-based
    rule:
    - len(slug) >= 8 → plain substring match (high specificity already).
    - len(slug) <  8 → require `\\b{slug}\\b` word-boundary regex.
    """
    if not slug:
        return False
    desc = description.lower()
    if len(slug) >= 8:
        return slug in desc
    pattern = r"\b" + re.escape(slug) + r"\b"
    return re.search(pattern, desc) is not None


def _producer_bare_name(producer: str) -> str:
    """Strip backticks, ::method suffix, .py extension; return bare token."""
    s = producer.strip("`").strip()
    # Take the part before "::"
    if "::" in s:
        s = s.split("::", 1)[0]
    # Drop .py
    if s.endswith(".py"):
        s = s[:-3]
    # Drop path components — keep just the last segment
    s = s.replace("\\", "/").split("/")[-1]
    return s


def _scan_test_files_for_producer(project_root: Path, producer_token: str) -> bool:
    """Heuristic: any tests/**/*.py file mentions the producer token?"""
    if not producer_token or len(producer_token) < 3:
        return False
    for tests_dir in (
        project_root / "tests",
        project_root / "plugins",
        project_root / "shared" / "tests",
    ):
        if not tests_dir.exists():
            continue
        for test_path in tests_dir.rglob("test_*.py"):
            try:
                content = test_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if producer_token in content:
                return True
    return False


def _scan_changed_test_files_for_producer(
    project_root: Path,
    changed_files: list[str],
    producer_token: str,
) -> bool:
    """E spec HIGH-5: scoped variant of `_scan_test_files_for_producer`.

    Only inspects test files that appear in `changed_files`. This avoids
    false positives where an old unrelated test mentions the producer
    name in a comment but was not added/modified by the matched commit.
    """
    if not producer_token or len(producer_token) < 3:
        return False
    if not changed_files:
        return False
    for raw_path in changed_files:
        normalized = raw_path.replace("\\", "/")
        # Only consider test files (test_*.py or *_test.py under tests/).
        name = normalized.rsplit("/", 1)[-1]
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        candidate = project_root / normalized
        if not candidate.exists():
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if producer_token in content:
            return True
    return False


def correlate_with_commits(
    specs: list[SpecBoundaries],
    events_jsonl: Path,
    project_root: Path | None = None,
) -> list[CoverageRow]:
    """Join each spec to events.jsonl commits + run round-trip heuristic."""
    events = _load_events(events_jsonl)
    rows: list[CoverageRow] = []
    project_root = project_root or events_jsonl.parent

    for spec in specs:
        # Match commits by description containing the spec slug (best-effort).
        # E spec HIGH-6: short slugs require word-boundary match.
        slug = _spec_slug(spec.spec_path)
        matched = []
        all_changed_files: list[str] = []
        any_matched_event_lacks_changed_files = False
        for evt in events:
            desc = evt.get("description") or ""
            commit = evt.get("commit") or ""
            if not _slug_matches_description(slug, desc):
                continue
            matched.append(commit)
            cf = evt.get("changed_files")
            if isinstance(cf, list) and cf:
                all_changed_files.extend(cf)
            else:
                # E spec HIGH-5 fallback: at least one matched event has
                # no changed_files → use "unknown" marker for tested status.
                any_matched_event_lacks_changed_files = True

        # Drift signal: spec has no boundaries declared, but at least one
        # matched commit touches IO files.
        drift = False
        drift_reason = ""
        if not spec.boundaries:
            # If we have no commit linkage but the spec itself mentions IO
            # patterns in its prose, also flag.
            if all_changed_files and is_io_boundary_change(all_changed_files):
                drift = True
                drift_reason = (
                    f"matched commits changed IO-boundary files "
                    f"({sorted(set(all_changed_files))[:3]}) but spec lacks "
                    f"## Affected Boundaries section"
                )
            else:
                # Fallback: scan spec text for IO file path mentions
                try:
                    spec_text = _read_text_lenient(spec.spec_path)
                except OSError:
                    spec_text = ""
                inferred_files = re.findall(
                    r"[^\s`'\"]*(?:\.env(?:\.[a-zA-Z0-9_-]+)?|hooks\.json|settings\.json|"
                    r"[A-Za-z0-9_-]+_config\.json|[A-Za-z0-9_-]+_state\.json)",
                    spec_text,
                )
                if inferred_files and is_io_boundary_change(inferred_files):
                    drift = True
                    drift_reason = (
                        f"spec text mentions IO-boundary file(s) "
                        f"({sorted(set(inferred_files))[:3]}) but lacks "
                        f"## Affected Boundaries section"
                    )

        boundary_results = []
        for b in spec.boundaries:
            token = _producer_bare_name(b.producer)
            # E spec HIGH-5: scope round-trip evidence to test files in
            # the matched commit's changed_files. If we have those, only
            # those count. If we DON'T (legacy events), fall back to the
            # full-walk and mark the result "unknown" so consumers know
            # the audit signal is degraded.
            if matched and all_changed_files:
                tested: bool | str = _scan_changed_test_files_for_producer(
                    project_root, all_changed_files, token
                ) if project_root else False
            elif matched and any_matched_event_lacks_changed_files:
                # Fallback path. Run the legacy full-walk for the value
                # but expose the result as "unknown" rather than False.
                _ = (
                    _scan_test_files_for_producer(project_root, token)
                    if project_root else False
                )
                tested = "unknown"
            else:
                # No matched commits at all (or no project_root) — old
                # behavior: full-walk.
                tested = (
                    _scan_test_files_for_producer(project_root, token)
                    if project_root else False
                )
            boundary_results.append(BoundaryResult(boundary=b, round_trip_tested=tested))

        rows.append(CoverageRow(
            spec_path=spec.spec_path,
            boundary_results=boundary_results,
            commits=matched,
            drift_signal=drift,
            drift_reason=drift_reason,
        ))
    return rows


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_json(rows: list[CoverageRow]) -> dict:
    total_boundaries = sum(len(r.boundary_results) for r in rows)
    # E spec HIGH-5: round_trip_tested may be True/False/"unknown".
    # Only count strictly-True for the headline tested counter.
    tested_boundaries = sum(
        1 for r in rows for br in r.boundary_results
        if br.round_trip_tested is True
    )
    unknown_boundaries = sum(
        1 for r in rows for br in r.boundary_results
        if br.round_trip_tested == "unknown"
    )
    drift_count = sum(1 for r in rows if r.drift_signal)
    return {
        "summary": {
            "specs_scanned": len(rows),
            "specs_with_boundaries": sum(1 for r in rows if r.boundary_results),
            "total_boundaries": total_boundaries,
            "round_trip_tested": tested_boundaries,
            "round_trip_unknown": unknown_boundaries,
            "drift_signals": drift_count,
        },
        "rows": [r.to_dict() for r in rows],
    }


def render_markdown(rows: list[CoverageRow]) -> str:
    j = render_json(rows)
    s = j["summary"]
    out = ["# Boundary Coverage Report", ""]
    out.append("## Coverage Summary")
    out.append("")
    out.append(f"- Specs scanned: **{s['specs_scanned']}**")
    out.append(f"- Specs with `## Affected Boundaries`: **{s['specs_with_boundaries']}**")
    out.append(f"- Total boundaries declared: **{s['total_boundaries']}**")
    out.append(f"- Round-trip tested (heuristic): **{s['round_trip_tested']}**")
    out.append(f"- Drift signals: **{s['drift_signals']}**")
    out.append("")

    out.append("## Per-Iterate Breakdown")
    out.append("")
    out.append("| Spec | Boundaries | Round-trip Tested | Commits | Drift |")
    out.append("|---|---|---|---|---|")
    for r in rows:
        spec_name = r.spec_path.name
        bcount = len(r.boundary_results)
        tested = sum(1 for br in r.boundary_results if br.round_trip_tested is True)
        unknown = sum(
            1 for br in r.boundary_results if br.round_trip_tested == "unknown"
        )
        commit_short = ", ".join(c[:7] for c in r.commits[:3]) if r.commits else "—"
        drift_marker = "DRIFT" if r.drift_signal else ""
        tested_cell = f"{tested}/{bcount}"
        if unknown:
            tested_cell += f" ({unknown} unknown)"
        out.append(
            f"| `{spec_name}` | {bcount} | {tested_cell} | {commit_short} | {drift_marker} |"
        )
    out.append("")

    drift_rows = [r for r in rows if r.drift_signal]
    if drift_rows:
        out.append("## Drift Signals")
        out.append("")
        out.append(
            "Iterates whose commits or spec text touched IO-boundary files but "
            "did NOT declare an `## Affected Boundaries` section. Audit hook for "
            "Sub-Iterate A's `touches_io_boundary` discipline."
        )
        out.append("")
        for r in drift_rows:
            out.append(f"- `{r.spec_path.name}` — {r.drift_reason}")
        out.append("")

    out.append("## Boundary Detail")
    out.append("")
    for r in rows:
        if not r.boundary_results:
            continue
        out.append(f"### `{r.spec_path.name}`")
        out.append("")
        out.append("| Producer | Consumer | Format | Round-trip Tested |")
        out.append("|---|---|---|---|")
        for br in r.boundary_results:
            if br.round_trip_tested is True:
                tested_str = "yes"
            elif br.round_trip_tested == "unknown":
                tested_str = "unknown"
            else:
                tested_str = "no"
            out.append(
                f"| {br.boundary.producer} | {br.boundary.consumer} | "
                f"{br.boundary.format} | {tested_str} |"
            )
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def merge_into_test_results(
    json_obj: dict,
    target_path: Path,
) -> None:
    """Atomically merge the report JSON into shipwright_test_results.json.

    Reads the existing file (if any), sets the
    `boundary_coverage_report` key to `json_obj`, and writes back via
    `tmp.replace(target)` for atomicity. Other top-level keys are
    preserved.

    E spec HIGH-4: callers can use this in lieu of the standalone
    `merge_boundary_coverage.py` helper.
    """
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    else:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing["boundary_coverage_report"] = json_obj
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp_path.replace(target_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--events-jsonl",
        type=Path,
        default=None,
        help="Path to shipwright_events.jsonl (default: <project-root>/shipwright_events.jsonl)",
    )
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print JSON to stdout (in addition to or instead of file output).",
    )
    parser.add_argument(
        "--merge-into",
        type=Path,
        default=None,
        help="Atomically merge the JSON report into the given file under the "
             "'boundary_coverage_report' key. Other top-level keys are "
             "preserved. Typical target: shipwright_test_results.json.",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    events_path = args.events_jsonl or (project_root / "shipwright_events.jsonl")

    specs = scan_specs(project_root)
    rows = correlate_with_commits(specs, events_path, project_root=project_root)
    json_obj = render_json(rows)
    md = render_markdown(rows)

    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(md, encoding="utf-8")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(json_obj, indent=2), encoding="utf-8")
    if args.merge_into:
        merge_into_test_results(json_obj, args.merge_into)
    if args.print_json or (
        not args.output_markdown
        and not args.output_json
        and not args.merge_into
    ):
        print(json.dumps(json_obj, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
