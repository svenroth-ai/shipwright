"""Unit tests for artifact_writer."""

import re
from pathlib import Path

import pytest

from lib.artifact_writer import (
    ADR_OUTPUT_MAX_NUMBER,
    ARCHITECTURE_MARKER_VERSION,
    NO_ARCHITECTURE_SYNC,
    _render_architecture_md,
    _render_decision_log,
    parse_architecture_marker,
    render_architecture_marker,
    write_agent_docs,
    write_claude_md,
    write_spec,
)


def test_write_claude_md(tmp_path: Path) -> None:
    path = write_claude_md(
        tmp_path,
        project_name="Demo",
        profile="supabase-nextjs",
        stack={"runtime": {"node": "22.x"}, "frontend": {"next": "Next.js@16"}, "backend": {}, "database": {}, "auth": {}},
        commands={"build": "npm run build", "test": "npx vitest", "dev": "npm run dev"},
        product_description="A demo app that does X, Y, Z.",
    )
    content = path.read_text(encoding="utf-8")
    assert "# Demo" in content
    assert "supabase-nextjs" in content
    assert "A demo app that does X, Y, Z." in content
    assert "npm run build" in content
    assert "/shipwright-iterate" in content


def test_write_agent_docs(tmp_path: Path) -> None:
    paths = write_agent_docs(
        tmp_path,
        project_name="Demo", profile="supabase-nextjs", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[{"name": "presentation", "paths": ["src/app"]}],
        loc_by_layer={"presentation": 100},
        architecture_diagram="```\n(diagram)\n```",
        data_flow_description="Data flows from X to Y.",
        conventions={"linter": "eslint-flat", "formatter": "prettier"},
        conventions_prose="Test conventions prose.",
        features_count=3, commits_total=42, contributors_total=2,
        nested_excluded=["webui"], commit_sha="abc",
        retroactive_adrs=[],
    )
    names = [p.name for p in paths]
    assert "architecture.md" in names
    assert "conventions.md" in names
    assert "decision_log.md" in names
    assert "build_dashboard.md" in names
    dec = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    # Adopt's output canon is 3-digit zero-padded ADR ids, starting at
    # ADR-001 for greenfield (no pre-existing decision_log.md).
    assert "ADR-001" in dec
    assert "ADR-0001" not in dec  # the old 4-digit form must not regress
    assert "Adopt" in dec
    dash = (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
    assert "42" in dash  # commits_total
    assert "webui" in dash


def test_write_agent_docs_picks_next_free_adr_id_from_existing_log(
    tmp_path: Path,
) -> None:
    """Brownfield regression — adopt must parse the existing log for max
    ADR id and start its adoption ADR at max + 1, not at the hardcoded
    ADR-001 / ADR-0001. This is the core bug from shipwright-webui's
    2026-04-30 adopt run, where 4-digit ADR-0053 silently collided
    with already-written ADR-053..ADR-058.

    Fixture mirrors the spec's brownfield_log_with_gap.md scenario:
    a sparse log with a 027→045 gap, a 045b disambiguation suffix,
    and an ADR-058 H3 entry. Expected adoption id is ADR-059.
    """
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    (agent_docs / "decision_log.md").write_text(
        "# Decision Log — original\n\n"
        "## ADR-001: Use Postgres\n\nDecided.\n\n---\n\n"
        "## ADR-002: Adopt monorepo\n\nDecided.\n\n---\n\n"
        "## ADR-027: Switch to NATS\n\nDecided.\n\n---\n\n"
        "## ADR-045: Pivot to assistant-ui\n\nDecided.\n\n---\n\n"
        "## ADR-045b: Pivot follow-up\n\nDisambig suffix.\n\n---\n\n"
        "## ADR-053: ADR-053: Stylistic duplication\n\nDecided.\n\n---\n\n"
        "### ADR-058: Compact H3 entry\n\nDecided.\n",
        encoding="utf-8",
    )
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={"linter": "eslint", "formatter": "prettier"},
        conventions_prose="",
        features_count=0, commits_total=10, contributors_total=1,
        nested_excluded=[], commit_sha=None, retroactive_adrs=[],
    )
    body = (agent_docs / "decision_log.md").read_text(encoding="utf-8")
    # Adoption ADR is ADR-059 (max 058 + 1), 3-digit canon
    assert "ADR-059: Adopt this repository into the Shipwright SDLC" in body
    # The old broken 4-digit form must not appear
    assert "ADR-0059" not in body
    assert "ADR-0001" not in body  # adopt-side; existing user ADRs are 3-digit here
    # Pre-existing entries still present verbatim
    assert "ADR-045b: Pivot follow-up" in body
    assert "ADR-053: ADR-053: Stylistic duplication" in body
    assert "### ADR-058: Compact H3 entry" in body


def test_write_agent_docs_retroactive_adrs_continue_from_max_plus_one(
    tmp_path: Path,
) -> None:
    """Retroactive ADRs continue numbering after the adoption ADR. With
    max existing = 27 and 2 retroactive ADRs the layout is:
        ADR-028: adoption
        ADR-029: retroactive #1
        ADR-030: retroactive #2
    """
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    (agent_docs / "decision_log.md").write_text(
        "# Decision Log\n\n## ADR-027: Existing\n\nBody.\n",
        encoding="utf-8",
    )
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=0, commits_total=1, contributors_total=1,
        nested_excluded=[], commit_sha=None,
        retroactive_adrs=[
            {"sha": "abc1234", "subject": "Retroactive one",
             "context": "ctx", "decision": "dec", "consequences": "csq"},
            {"sha": "def5678", "subject": "Retroactive two",
             "context": "ctx", "decision": "dec", "consequences": "csq"},
        ],
    )
    body = (agent_docs / "decision_log.md").read_text(encoding="utf-8")
    assert "ADR-028: Adopt this repository" in body
    assert "ADR-029: Retroactive one" in body
    assert "ADR-030: Retroactive two" in body
    # Existing ADR-027 preserved
    assert "ADR-027: Existing" in body


def test_render_decision_log_emits_h3_adoption_heading() -> None:
    """Adopt's output uses H3 (`### ADR-NNN:`) so it round-trips through
    Shipwright's compact-form canon parser (`drift_parsers.parse_adr_headers`).
    Before this fix adopt wrote H2 with colon — a format neither the
    compact (H3-colon) nor the verbose (H2-pipes) regex matched, leaving
    downstream G3 / F1 / F2 / F3 audits blind to the adoption ADR."""
    body = _render_decision_log(
        project_name="Demo", profile="x", scope="full_app",
        commit_sha="abc1234", features_count=3,
        retroactive_adrs=[],
        start_adr_number=1,
    )
    assert "### ADR-001: Adopt this repository into the Shipwright SDLC" in body
    # The old H2 form must not regress. Use line-anchored regex — plain
    # substring match would false-positive (`## ADR-` IS a substring of
    # `### ADR-`).
    assert not re.search(r"^## ADR-001:\s+Adopt", body, re.MULTILINE)


def test_render_decision_log_subheadings_are_h4() -> None:
    """Sub-section headings (Context/Decision/Consequences/Rejected
    alternatives) live under the H3 ADR heading, so they're H4 — not
    H3, which would clash with the ADR-level parser."""
    body = _render_decision_log(
        project_name="Demo", profile="x", scope="full_app",
        commit_sha="abc1234", features_count=3,
        retroactive_adrs=[],
        start_adr_number=1,
    )
    assert "#### Context" in body
    assert "#### Decision" in body
    assert "#### Consequences" in body
    assert "#### Rejected alternatives" in body


def test_render_decision_log_rejects_overflow_above_999() -> None:
    """Adopt's output canon is 3-digit zero-padded. If the next-free
    counter says ADR-1000+, that's a Shipwright-wide convention upgrade,
    not a silent 4-digit serialisation. The renderer must fail loud."""
    with pytest.raises(ValueError, match="3-digit zero-padded"):
        _render_decision_log(
            project_name="Demo", profile="x", scope="full_app",
            commit_sha=None, features_count=0,
            retroactive_adrs=[],
            start_adr_number=ADR_OUTPUT_MAX_NUMBER + 1,
        )


def test_render_decision_log_rejects_overflow_via_retroactive_count() -> None:
    """Same boundary check, but triggered by retroactive ADRs pushing
    the last id past 999."""
    with pytest.raises(ValueError, match="3-digit zero-padded"):
        _render_decision_log(
            project_name="Demo", profile="x", scope="full_app",
            commit_sha=None, features_count=0,
            retroactive_adrs=[
                {"subject": "x", "context": "x", "decision": "x",
                 "consequences": "x", "sha": ""}
            ] * 5,
            start_adr_number=ADR_OUTPUT_MAX_NUMBER - 2,  # 5 retroactive → overflow
        )


def test_write_spec_has_fr_ids(tmp_path: Path) -> None:
    features = [
        {"fr_id": "FR-01.01", "label": "Dashboard", "description": "User views active projects", "source_file": "src/app/dashboard/page.tsx"},
        {"fr_id": "FR-01.02", "label": "Login", "description": "User logs in", "source_file": "src/app/login/page.tsx"},
    ]
    path = write_spec(
        tmp_path,
        project_name="Demo", split_name="01-adopted",
        product_description="Demo app.",
        features=features,
        qr_items=["CI pipeline must pass"],
        constraints=["Node 22.x"],
    )
    content = path.read_text(encoding="utf-8")
    assert "FR-01.01" in content
    assert "FR-01.02" in content
    assert re.search(r"\bFR-\d+\.\d+\b", content)
    assert "Demo app." in content
    assert "CI pipeline must pass" in content


# ---------------------------------------------------------------------------
# Iterate A.1 — architecture marker (drift detector input)
# ---------------------------------------------------------------------------


def test_render_architecture_marker_with_valid_sha() -> None:
    """A valid 7-40 char hex sha renders verbatim into the marker comment."""
    marker = render_architecture_marker("abc1234")
    assert "v=2" in marker
    assert "last-sync=abc1234" in marker

    long_sha = "0123456789abcdef0123456789abcdef01234567"  # 40 chars
    assert f"last-sync={long_sha}" in render_architecture_marker(long_sha)


def test_render_architecture_marker_falls_back_for_invalid_sha() -> None:
    """Anything that isn't a valid commit-sha → ``no-sync-recorded`` sentinel."""
    for bad in (None, "", "not-a-sha", "ABCDEF1", "abc12g4", "abc"):
        marker = render_architecture_marker(bad)
        assert NO_ARCHITECTURE_SYNC in marker, f"bad={bad!r}"
        assert "v=2" in marker


def test_parse_architecture_marker_round_trips() -> None:
    """A rendered marker survives parse + lookup unchanged."""
    sha = "abc1234"
    marker = render_architecture_marker(sha)
    parsed = parse_architecture_marker(f"# Heading\n{marker}\n\nbody")
    assert parsed is not None
    assert parsed["version"] == str(ARCHITECTURE_MARKER_VERSION)
    assert parsed["last_sync"] == sha


def test_parse_architecture_marker_missing_returns_none() -> None:
    """Pre-marker era (no marker line) → None so callers fall back to "unknown"."""
    assert parse_architecture_marker("# Architecture — Demo\n\nno marker here\n") is None


def test_parse_architecture_marker_invalid_sha_normalises_to_sentinel() -> None:
    """A marker carrying garbage in the sha slot is parsed but the sha is
    normalised to ``NO_ARCHITECTURE_SYNC`` — callers never have to revalidate."""
    marker = "<!-- shipwright:architecture v=2 last-sync=not-a-sha -->"
    parsed = parse_architecture_marker(f"# H\n{marker}\n")
    assert parsed is not None
    assert parsed["last_sync"] == NO_ARCHITECTURE_SYNC
    assert parsed["version"] == "2"


def test_parse_architecture_marker_tolerates_v1() -> None:
    """v=1 markers (pre-this-iterate) parse without error; drift detector
    decides how to treat them."""
    marker = "<!-- shipwright:architecture v=1 last-sync=abc1234 -->"
    parsed = parse_architecture_marker(f"# H\n{marker}\n")
    assert parsed is not None
    assert parsed["version"] == "1"
    assert parsed["last_sync"] == "abc1234"


def test_render_architecture_md_embeds_marker(tmp_path: Path) -> None:
    """The marker lives directly under the H1 so the drift detector can read
    it without scanning the rest of the doc."""
    md = _render_architecture_md(
        project_name="Demo",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[],
        architecture_diagram="```mermaid\nflowchart TB\n  A-->B\n```",
        data_flow_description="...",
        profile_name="vite-hono",
        commit_sha="abc1234",
    )
    lines = md.splitlines()
    assert lines[0] == "# Architecture — Demo"
    assert "shipwright:architecture" in lines[1]
    assert "last-sync=abc1234" in lines[1]
    assert "```mermaid" in md


def test_write_agent_docs_writes_architecture_marker(tmp_path: Path) -> None:
    """Smoke-test the writer end-to-end — the marker should land in
    ``.shipwright/agent_docs/architecture.md`` with the commit_sha threaded
    through from the caller."""
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```mermaid\nflowchart TB\nA-->B\n```",
        data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=0, commits_total=1, contributors_total=1,
        nested_excluded=[], commit_sha="abc1234", retroactive_adrs=[],
    )
    arch = (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    parsed = parse_architecture_marker(arch)
    assert parsed == {"version": "2", "last_sync": "abc1234"}
