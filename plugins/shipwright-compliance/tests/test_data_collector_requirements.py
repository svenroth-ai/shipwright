"""``collect_requirements``: what the RTM reads out of a spec.md FR table.

Split out of ``test_data_collector.py``, which S4 pushed from 1253 to 1278 lines
— past its baseline and into an anti-ratchet block. Trimming 25 lines to squeak
under would have been the dishonest fix: the file was already 1253 lines, and an
``exception`` state with an ADR licenses a file's EXISTING size, never its
growth.

The seam is cohesive rather than arbitrary, and it is the surface S4 actually
changed: everything here answers "given a spec.md, which FR rows does the
compliance collector see, and what text does it take for each?" — the column
shapes (3-, 5-, 6-column), the removed-requirements section, and the table
governance rules. Its parent keeps configs, splits, sections, decisions,
dependencies, SBOM/licence resolution and event-log joins, none of which touch
the FR table.

Every test moved verbatim; the split adds no assertion and removes none.
"""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import RequirementInfo, collect_requirements


class TestCollectRequirementsAdoptFiveCol:
    """Coverage for FR tables produced by /shipwright-adopt (5-data-column).

    Greenfield specs use ``| ID | Text | Priority |`` (3 data columns).
    Adopt specs use ``| ID | Name | Priority | Description | Source |`` (5).
    The compliance RTM consumer must extract from both — the 5-col semantic
    body is the Description column, not the Name column. See ADR-031.
    """

    ADOPT_SPEC_BODY = (
        "# Specification — adopted\n\n"
        "## Functional Requirements\n\n"
        "| ID | Name | Priority | Description | Source |\n"
        "|----|------|----------|-------------|--------|\n"
        "| FR-01.01 | /shipwright-run | Must | Orchestrate the full Shipwright SDLC pipeline. | enrichment.json |\n"
        "| FR-01.10 | /shipwright-compliance | Must | Generate audit-ready compliance documentation. | enrichment.json |\n"
        "| FR-01.13 | /shipwright-adopt | Should | Onboard an existing repository into the Shipwright SDLC. | enrichment.json |\n"
    )

    def test_collect_requirements_extracts_all_5col_rows(self, tmp_path: Path):
        planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(self.ADOPT_SPEC_BODY, encoding="utf-8")

        reqs = collect_requirements(tmp_path)

        ids = {r.id for r in reqs}
        assert ids == {"FR-01.01", "FR-01.10", "FR-01.13"}
        first = next(r for r in reqs if r.id == "FR-01.01")
        # Description (col 4), not Name (col 2)
        assert first.text == "Orchestrate the full Shipwright SDLC pipeline."
        assert first.priority == "Must"
        assert first.split == "01-adopted"
        assert first.spec_path == ".shipwright/planning/01-adopted/spec.md"
        assert isinstance(first, RequirementInfo)

    def test_collect_requirements_real_adopted_spec(self):
        """Round-trip probe against the actual /shipwright-adopt output.

        Ensures the consumer agrees with the producer on every FR in the
        repo's own ``.shipwright/planning/01-adopted/spec.md``.
        """
        repo_root = Path(__file__).resolve().parents[3]
        spec = repo_root / ".shipwright" / "planning" / "01-adopted" / "spec.md"
        if not spec.exists():
            import pytest
            pytest.skip("01-adopted/spec.md not present in this checkout")  # test-hygiene: allow-silent-skip: defensive guard for partial/non-repo checkout; file is present in CI

        # collect_requirements walks {project_root}/.shipwright/planning/*/spec.md
        reqs = collect_requirements(repo_root)
        ids = {r.id for r in reqs}
        assert "FR-01.10" in ids, f"FR-01.10 missing from {sorted(ids)}"
        assert "FR-01.13" in ids, f"FR-01.13 missing from {sorted(ids)}"
        assert len(reqs) >= 13, f"expected >=13 FRs, got {len(reqs)}: {sorted(ids)}"

    def test_collect_requirements_3col_greenfield_still_works(self, tmp_path: Path):
        """Backward-compatibility: existing 3-col Greenfield specs unaffected."""
        planning = tmp_path / ".shipwright" / "planning" / "01-auth"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(
            "| ID | Text | Priority |\n"
            "|----|------|----------|\n"
            "| FR-01.01 | User can log in | Must |\n"
            "| FR-01.02 | User can log out | Should |\n",
            encoding="utf-8",
        )

        reqs = collect_requirements(tmp_path)
        assert {r.id for r in reqs} == {"FR-01.01", "FR-01.02"}
        first = next(r for r in reqs if r.id == "FR-01.01")
        assert first.text == "User can log in"
        assert first.priority == "Must"


class TestCollectRequirementsSixCol:
    """Coverage for 6-column FR tables (adopt specs with a trailing column).

    Some /shipwright-adopt outputs append a sixth column (e.g. an inference
    Confidence score) after Source. Before the BUG-A fix the FR-table regex
    demanded end-of-line right after the Description+Source pair, so every
    6-column row silently failed to parse — collapsing RTM coverage to 0%.
    The consumer must parse every FR row regardless of trailing columns; the
    semantic body stays the Description column (group 4). See ADR-031 for the
    3-/5-column lineage.
    """

    SIX_COL_BODY = (
        "# Specification — adopted\n\n"
        "## Functional Requirements\n\n"
        "| ID | Name | Priority | Description | Source | Confidence |\n"
        "|----|------|----------|-------------|--------|------------|\n"
        "| FR-01.01 | dashboard | Must | User views active projects. | src/app/dashboard/page.tsx | 0.82 |\n"
        "| FR-01.02 | login | Must | User authenticates via magic link. | src/app/login/page.tsx | 0.91 |\n"
        "| FR-01.03 | settings | Should | User edits profile preferences. | src/app/settings/page.tsx | 0.55 |\n"
    )

    def test_collect_requirements_extracts_all_6col_rows(self, tmp_path: Path):
        planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(self.SIX_COL_BODY, encoding="utf-8")

        reqs = collect_requirements(tmp_path)

        ids = {r.id for r in reqs}
        assert ids == {"FR-01.01", "FR-01.02", "FR-01.03"}
        first = next(r for r in reqs if r.id == "FR-01.01")
        # Body is the Description column (4) — not Name (2), not Confidence (6).
        assert first.text == "User views active projects."
        assert first.priority == "Must"
        assert first.split == "01-adopted"
        assert isinstance(first, RequirementInfo)

    def test_six_col_ignores_trailing_columns(self, tmp_path: Path):
        """A 7+-column row still parses; columns past Source are ignored."""
        planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(
            "| ID | Name | Priority | Description | Source | Confidence | Notes |\n"
            "|----|------|----------|-------------|--------|------------|-------|\n"
            "| FR-01.01 | dashboard | Must | User views active projects. | src/x.tsx | 0.82 | n/a |\n",
            encoding="utf-8",
        )
        reqs = collect_requirements(tmp_path)
        assert len(reqs) == 1
        assert reqs[0].text == "User views active projects."
        assert reqs[0].priority == "Must"


class TestCollectRequirementsRemovedSection:
    """A `## Removed Requirements` section is excluded from RTM coverage.

    A REMOVE-classified iterate moves a deprecated FR row into a
    `## Removed Requirements` (or `### Removed Requirements`) section. Those
    rows still look like FR table rows, but collect_requirements MUST NOT
    return them — otherwise the RTM keeps reporting a deleted capability as
    an uncovered/failing requirement. Mirrors the parse_fr_table exclusion
    in shared/scripts/lib/drift_parsers.py (same fixture, same expectations).
    """

    REMOVED_REQ_BODY = (
        "# Specification — adopted\n\n"
        "## 2. Functional Requirements\n\n"
        "| ID | Text | Priority |\n"
        "|----|------|----------|\n"
        "| FR-01.01 | live requirement | Must |\n\n"
        "### Removed Requirements\n\n"
        "| ID | Requirement | Priority | Removed by | status |\n"
        "|----|-------------|----------|------------|--------|\n"
        "| FR-01.99 | obsolete flow | Must | iterate-20260516-x | status: deprecated |\n\n"
        "## 3. Quality Requirements\n\n"
        "| FR-01.02 | another live requirement | Should |\n"
    )

    def test_removed_requirements_rows_excluded(self, tmp_path: Path):
        planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(self.REMOVED_REQ_BODY, encoding="utf-8")

        reqs = collect_requirements(tmp_path)

        ids = {r.id for r in reqs}
        assert ids == {"FR-01.01", "FR-01.02"}
        assert "FR-01.99" not in ids

    def test_h2_removed_requirements_excluded(self, tmp_path: Path):
        planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        # The header row is REQUIRED since S4 withdrew the headerless positional
        # fallback (convergence rule C6). This fixture had none, and its intent
        # -- "an H2 Removed-Requirements section excludes its rows" -- is
        # orthogonal to that, so the header is added rather than the assertion
        # weakened. The headerless case gets its own test below.
        (planning / "spec.md").write_text(
            "| ID | Requirement | Priority |\n"
            "| FR-01.01 | live | Must |\n"
            "## Removed Requirements\n"
            "| FR-01.99 | dead | Must |\n",
            encoding="utf-8",
        )

        reqs = collect_requirements(tmp_path)
        assert {r.id for r in reqs} == {"FR-01.01"}

    def test_a_table_with_no_header_at_all_yields_nothing(self, tmp_path: Path):
        """BEHAVIOUR CHANGE, S4 (rule C6 withdrawn).

        A table with no header naming a Priority column no longer parses
        positionally. Both external plan reviewers argued for this, and the
        composition route made it necessary: a stale column map surviving a
        heading plus a positional fallback is what let a coverage table keyed by
        FR id yield requirements. Both writers always emit a header, so this
        path was a degraded mode rather than a format -- and the rows are
        RECORDED (`invalid_ids`, reason `no_governing_header`), not lost.
        """
        planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(
            "| FR-01.01 | live | Must |\n", encoding="utf-8",
        )

        assert collect_requirements(tmp_path) == []


class TestCollectRequirementsColumnWidths:
    """Consolidated probe: 3-, 5-, and 6-column FR tables all parse.

    Directly covers the BUG-A regression — a single collection run across
    three split dirs, one per supported table width, asserting every FR row
    surfaces with the correct semantic body.
    """

    def test_all_column_widths_parse(self, tmp_path: Path):
        specs = {
            "01-three-col": (
                "| ID | Text | Priority |\n"
                "|----|------|----------|\n"
                "| FR-01.01 | User can log in | Must |\n"
            ),
            "02-five-col": (
                "| ID | Name | Priority | Description | Source |\n"
                "|----|------|----------|-------------|--------|\n"
                "| FR-02.01 | run | Must | Orchestrate the pipeline. | enrichment.json |\n"
            ),
            "03-six-col": (
                "| ID | Name | Priority | Description | Source | Confidence |\n"
                "|----|------|----------|-------------|--------|------------|\n"
                "| FR-03.01 | adopt | Should | Onboard an existing repo. | enrichment.json | 0.6 |\n"
            ),
        }
        for split_name, body in specs.items():
            planning = tmp_path / ".shipwright" / "planning" / split_name
            planning.mkdir(parents=True)
            (planning / "spec.md").write_text(body, encoding="utf-8")

        reqs = collect_requirements(tmp_path)
        by_id = {r.id: r for r in reqs}

        # Every FR row across all three table widths parsed.
        assert set(by_id) == {"FR-01.01", "FR-02.01", "FR-03.01"}
        # 3-col body = Text column (group 2).
        assert by_id["FR-01.01"].text == "User can log in"
        # 5-col body = Description column (group 4).
        assert by_id["FR-02.01"].text == "Orchestrate the pipeline."
        # 6-col body = Description column (group 4); trailing Confidence ignored.
        assert by_id["FR-03.01"].text == "Onboard an existing repo."
