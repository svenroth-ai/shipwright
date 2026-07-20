"""Unit tests for shared/scripts/lib/drift_parsers.py.

These tests cover the pure-function surface that iterate 12.0 extracted
out of the check_drift.py hook and out of compliance data_collector.py.
A separate subprocess test below verifies the hook still bootstraps
cleanly when invoked with a minimal environment (no PYTHONPATH).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.drift_parsers import (
    build_paths_from_entries,
    collect_requirements_from_planning,
    extract_dev_blocks,
    extract_structure_block,
    find_nearest_makefile,
    find_nearest_package_json,
    find_nearest_pyproject_toml,
    load_gitignore,
    parse_fr_table,
    parse_make_refs,
    parse_npm_run_refs,
    parse_structure_entries,
    parse_uv_run_refs,
    read_package_scripts,
)


# ---------------------------------------------------------------------------
# Structure-block parser
# ---------------------------------------------------------------------------

def test_extract_structure_block_returns_inner_text():
    md = "## Structure\n\n```\nsrc/\n  app/\n```\n"
    assert extract_structure_block(md) == "src/\n  app/"


def test_extract_structure_block_none_when_missing():
    assert extract_structure_block("# nothing here\n") is None


def test_parse_structure_entries_handles_nested_dirs_and_comments():
    block = "src/         # root\n  app/       # app dir\n  lib/\n    utils.py\n"
    entries = parse_structure_entries(block)
    assert entries == [
        (0, "src", True),
        (2, "app", True),
        (2, "lib", True),
        (4, "utils.py", False),
    ]


def test_build_paths_from_entries_reconstructs_nesting():
    entries = [(0, "src", True), (2, "app", True), (4, "page.tsx", False), (2, "lib", True)]
    paths = build_paths_from_entries(entries)
    assert paths == [
        ("src", True),
        ("src/app", True),
        ("src/app/page.tsx", False),
        ("src/lib", True),
    ]


# ---------------------------------------------------------------------------
# .gitignore reader
# ---------------------------------------------------------------------------

def test_load_gitignore_returns_plain_top_level_names(tmp_path):
    (tmp_path / ".gitignore").write_text(
        "# comment\nnode_modules/\n.venv\ndist/\n*.log\nbuild/output\n"
    )
    ignored = load_gitignore(tmp_path)
    # Plain names survive; wildcards and nested paths are ignored.
    assert "node_modules" in ignored
    assert ".venv" in ignored
    assert "dist" in ignored
    assert "*.log" not in ignored
    assert "build/output" in ignored  # treated as a plain name


def test_load_gitignore_missing_returns_empty(tmp_path):
    assert load_gitignore(tmp_path) == set()


# ---------------------------------------------------------------------------
# Dev block + command parsers
# ---------------------------------------------------------------------------

def test_extract_dev_blocks_returns_bash_sections():
    md = (
        "## Development\n\n"
        "```bash\nnpm run dev\n```\n\n"
        "## Something\n\n## Development\n\n```bash\nuv run pytest tests/\n```\n"
    )
    blocks = extract_dev_blocks(md)
    assert "npm run dev" in blocks[0]
    assert "uv run pytest" in blocks[1]


def test_parse_npm_run_refs_captures_cd_prefix():
    refs = parse_npm_run_refs("cd webui && npm run dev\nnpm run test")
    assert refs[0].cd_target == "webui"
    assert refs[0].script == "dev"
    assert refs[1].cd_target is None
    assert refs[1].script == "test"


def test_parse_uv_run_refs_captures_tool():
    refs = parse_uv_run_refs("uv run pytest tests/\ncd shared && uv run ./scripts/foo.py")
    assert refs[0].tool == "pytest"
    assert refs[1].cd_target == "shared"


def test_parse_make_refs_captures_targets():
    refs = parse_make_refs("make build\ncd packages/api && make test-integration")
    assert refs[0].target == "build"
    assert refs[1].cd_target == "packages/api"
    assert refs[1].target == "test-integration"


# ---------------------------------------------------------------------------
# Nearest-ancestor finders
# ---------------------------------------------------------------------------

def test_find_nearest_package_json_walks_upward(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    found = find_nearest_package_json(sub, tmp_path)
    assert found == str(tmp_path / "package.json")


def test_find_nearest_pyproject_toml_stops_at_root(tmp_path):
    sub = tmp_path / "a"
    sub.mkdir()
    assert find_nearest_pyproject_toml(sub, tmp_path) is None


def test_find_nearest_makefile_finds_file(tmp_path):
    # Windows filesystems are case-insensitive so we can't assert a specific
    # case in the returned path — only that the finder returns *some*
    # Makefile variant located in the expected directory.
    (tmp_path / "Makefile").write_text("all:\n\t@echo ok\n")
    found = find_nearest_makefile(tmp_path, tmp_path)
    assert found is not None
    assert Path(found).parent == tmp_path
    assert Path(found).name.lower() in {"makefile", "gnumakefile"}


def test_read_package_scripts_returns_scripts_object(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"dev": "vite"}}')
    assert read_package_scripts(tmp_path / "package.json") == {"dev": "vite"}


def test_read_package_scripts_malformed_returns_empty(tmp_path):
    (tmp_path / "package.json").write_text("not json")
    assert read_package_scripts(tmp_path / "package.json") == {}


# ---------------------------------------------------------------------------
# FR table parser
# ---------------------------------------------------------------------------

def test_parse_fr_table_extracts_rows():
    md = (
        "| ID | Text | Priority |\n"
        "|----|------|----------|\n"
        "| FR-01.01 | User can log in | Must |\n"
        "| FR-01.02 | User can log out | Should |\n"
    )
    frs = parse_fr_table(md, split="01-auth", spec_path=".shipwright/planning/01-auth/spec.md")
    assert len(frs) == 2
    assert frs[0].id == "FR-01.01"
    assert frs[0].priority == "Must"
    assert frs[1].priority == "Should"
    assert frs[0].split == "01-auth"


def test_collect_requirements_from_planning_walks_splits(tmp_path):
    planning = tmp_path / ".shipwright" / "planning"
    (planning / "01-auth").mkdir(parents=True)
    (planning / "01-auth" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n" "| FR-01.01 | login | Must |\n"
    )
    (planning / "02-dashboard").mkdir()
    (planning / "02-dashboard" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n" "| FR-02.01 | show chart | Should |\n"
    )
    frs = collect_requirements_from_planning(tmp_path)
    assert {f.id for f in frs} == {"FR-01.01", "FR-02.01"}


def test_collect_requirements_no_planning_returns_empty(tmp_path):
    assert collect_requirements_from_planning(tmp_path) == []


# ---------------------------------------------------------------------------
# FR table parser — adopted (5-data-column) format
# ---------------------------------------------------------------------------
#
# /shipwright-adopt produces FR rows with five data columns:
#   | ID | Name | Priority | Description | Source |
# whereas /shipwright-project (Greenfield) produces three:
#   | ID | Text | Priority |
# Both must parse cleanly. For the 5-col format, the FR's `text`
# is the Description column (col 4) — the Name column is a slug
# like "/shipwright-run" and is not the FR's semantic body.
# Producer/consumer markdown drift; see ADR-031.

ADOPT_FIVE_COL_FIXTURE = (
    "| ID | Name | Priority | Description | Source |\n"
    "|----|------|----------|-------------|--------|\n"
    "| FR-01.01 | /shipwright-run | Must | Orchestrate the full Shipwright SDLC pipeline. | enrichment.json |\n"
    "| FR-01.10 | /shipwright-compliance | Must | Generate audit-ready compliance documentation. | enrichment.json |\n"
    "| FR-01.13 | /shipwright-adopt | Should | Onboard an existing repository into the Shipwright SDLC. | enrichment.json |\n"
)


def test_parse_fr_table_extracts_rows_from_adopt_5col_format():
    frs = parse_fr_table(
        ADOPT_FIVE_COL_FIXTURE,
        split="01-adopted",
        spec_path=".shipwright/planning/01-adopted/spec.md",
    )
    assert len(frs) == 3
    assert frs[0].id == "FR-01.01"
    assert frs[0].priority == "Must"
    # Description (col 4), not Name (col 2)
    assert frs[0].text == "Orchestrate the full Shipwright SDLC pipeline."
    assert frs[2].id == "FR-01.13"
    assert frs[2].priority == "Should"
    assert frs[2].text == "Onboard an existing repository into the Shipwright SDLC."


def test_parse_fr_table_3col_and_5col_both_match_in_one_doc():
    """A doc that mixes 3-col and 5-col rows still parses every row."""
    md = (
        "| ID | Text | Priority |\n"
        "|----|------|----------|\n"
        "| FR-01.01 | greenfield row | Must |\n"
        "\n"
        "| ID | Name | Priority | Description | Source |\n"
        "|----|------|----------|-------------|--------|\n"
        "| FR-02.01 | /adopted | Should | adopted row description | enrichment.json |\n"
    )
    frs = parse_fr_table(md, split="mixed", spec_path="x")
    assert {f.id: f.text for f in frs} == {
        "FR-01.01": "greenfield row",
        "FR-02.01": "adopted row description",
    }


def test_collect_requirements_walks_5col_adopt_split(tmp_path):
    planning = tmp_path / ".shipwright" / "planning" / "01-adopted"
    planning.mkdir(parents=True)
    (planning / "spec.md").write_text(ADOPT_FIVE_COL_FIXTURE, encoding="utf-8")
    frs = collect_requirements_from_planning(tmp_path)
    assert {f.id for f in frs} == {"FR-01.01", "FR-01.10", "FR-01.13"}


def test_parse_fr_table_real_adopted_spec_extracts_all_frs():
    """Round-trip probe (`references/round-trip-tests.md` Section 1):
    feed the actual file `/shipwright-adopt` produced into the consumer.
    Catches the producer/consumer markdown boundary drift this iterate fixes.
    """
    repo_root = Path(__file__).resolve().parents[2]
    spec = repo_root / ".shipwright" / "planning" / "01-adopted" / "spec.md"
    if not spec.exists():
        pytest.skip("01-adopted/spec.md not present in this checkout")  # test-hygiene: allow-silent-skip: defensive guard for partial/non-repo checkout; file is present in CI
    content = spec.read_text(encoding="utf-8")
    frs = parse_fr_table(
        content,
        split="01-adopted",
        spec_path=".shipwright/planning/01-adopted/spec.md",
    )
    ids = {f.id for f in frs}
    # Spec ships 13 FRs (FR-01.01 through FR-01.13). Probe for the
    # FRs this iterate names explicitly + the broader floor.
    assert "FR-01.10" in ids, f"FR-01.10 missing from {sorted(ids)}"
    assert "FR-01.13" in ids, f"FR-01.13 missing from {sorted(ids)}"
    assert len(frs) >= 13, f"expected >=13 FRs, got {len(frs)}: {sorted(ids)}"


# ---------------------------------------------------------------------------
# FR table parser — `## Removed Requirements` section exclusion
# ---------------------------------------------------------------------------
#
# A REMOVE-classified iterate moves a deprecated FR row out of the live
# `## Functional Requirements` table into a `## Removed Requirements` (or
# `### Removed Requirements`) section. Those rows still look like FR table
# rows, but parse_fr_table MUST NOT return them as live requirements — they
# would otherwise resurface in RTM coverage and drift checks forever.
# Mirrored in data_collector.collect_requirements (same fixture probed in
# plugins/shipwright-compliance/tests/test_data_collector.py).

REMOVED_REQ_FIXTURE = (
    "## 2. Functional Requirements\n"
    "\n"
    "| ID | Text | Priority |\n"
    "|----|------|----------|\n"
    "| FR-01.01 | live requirement | Must |\n"
    "\n"
    "### Removed Requirements\n"
    "\n"
    "| ID | Requirement | Priority | Removed by | status |\n"
    "|----|-------------|----------|------------|--------|\n"
    "| FR-01.99 | obsolete flow | Must | iterate-20260516-x | status: deprecated |\n"
    "\n"
    "## 3. Quality Requirements\n"
    "\n"
    "| FR-01.02 | another live requirement | Should |\n"
)


def test_parse_fr_table_excludes_removed_requirements_section():
    frs = parse_fr_table(REMOVED_REQ_FIXTURE, split="01", spec_path="x")
    ids = {f.id for f in frs}
    assert ids == {"FR-01.01", "FR-01.02"}
    assert "FR-01.99" not in ids


def test_parse_fr_table_resumes_after_removed_section_closes():
    """A heading at the Removed section's level-or-shallower closes it, so
    a live FR table further down the spec still parses."""
    frs = parse_fr_table(REMOVED_REQ_FIXTURE, split="01", spec_path="x")
    assert any(f.id == "FR-01.02" for f in frs)


def test_parse_fr_table_h2_removed_requirements_also_excluded():
    """`## Removed Requirements` (h2) excludes its rows just like the h3 form."""
    md = (
        "| ID | Requirement | Priority |\n" "| FR-01.01 | live | Must |\n"
        "## Removed Requirements\n"
        "| FR-01.99 | dead | Must |\n"
    )
    frs = parse_fr_table(md, split="01", spec_path="x")
    assert {f.id for f in frs} == {"FR-01.01"}


# ---------------------------------------------------------------------------
# Hook bootstrap (GPT R2 fix): check_drift.py must import drift_parsers
# when invoked as a subprocess with a minimal environment (no PYTHONPATH).
# ---------------------------------------------------------------------------

def test_check_drift_hook_bootstrap_subprocess(tmp_path):
    """Spawn check_drift.py with a minimal env and confirm it runs.

    The hook execution context in Claude Code has an unpredictable
    sys.path; the bootstrap block in check_drift.py must re-add
    ``shared/scripts/`` so ``lib.drift_parsers`` resolves. Without the
    bootstrap this would ImportError at startup.
    """
    hook = Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "check_drift.py"
    assert hook.exists(), f"hook not found at {hook}"

    # Seed a minimal project so the hook has a CLAUDE.md to parse.
    (tmp_path / "CLAUDE.md").write_text(
        "# Test\n\n## Structure\n\n```\n" + tmp_path.name + "/\n  stuff/\n```\n"
    )
    (tmp_path / "stuff").mkdir()

    # Minimal env: strip PYTHONPATH to prove the bootstrap is load-bearing.
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PYTHONPATH", "PYTHONHOME")
    }
    # Keep PATH so Python can find its own libraries.
    env.setdefault("PATH", os.environ.get("PATH", ""))

    result = subprocess.run(
        [sys.executable, str(hook)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        f"hook bootstrap failed: stderr={result.stderr!r} stdout={result.stdout!r}"
    )
