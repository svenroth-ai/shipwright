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


from lib.drift_parsers import (
    ADRHeader,
    build_paths_from_entries,
    collect_requirements_from_planning,
    extract_adr_id_number,
    extract_dev_blocks,
    extract_structure_block,
    find_duplicate_adr_ids,
    find_gaps_in_adr_ids,
    find_nearest_makefile,
    find_nearest_package_json,
    find_nearest_pyproject_toml,
    load_gitignore,
    parse_adr_headers,
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
    frs = parse_fr_table(md, split="01-auth", spec_path="planning/01-auth/spec.md")
    assert len(frs) == 2
    assert frs[0].id == "FR-01.01"
    assert frs[0].priority == "Must"
    assert frs[1].priority == "Should"
    assert frs[0].split == "01-auth"


def test_collect_requirements_from_planning_walks_splits(tmp_path):
    planning = tmp_path / "planning"
    (planning / "01-auth").mkdir(parents=True)
    (planning / "01-auth" / "spec.md").write_text(
        "| FR-01.01 | login | Must |\n"
    )
    (planning / "02-dashboard").mkdir()
    (planning / "02-dashboard" / "spec.md").write_text(
        "| FR-02.01 | show chart | Should |\n"
    )
    frs = collect_requirements_from_planning(tmp_path)
    assert {f.id for f in frs} == {"FR-01.01", "FR-02.01"}


def test_collect_requirements_no_planning_returns_empty(tmp_path):
    assert collect_requirements_from_planning(tmp_path) == []


# ---------------------------------------------------------------------------
# ADR parser
# ---------------------------------------------------------------------------

def test_parse_adr_headers_handles_compact_format():
    md = (
        "# Decision Log\n\n"
        "### ADR-001: First decision\n"
        "- **Status:** accepted\n\n"
        "### ADR-002: Second decision\n"
        "- **Status:** superseded\n"
        "- **Supersedes:** ADR-001\n"
    )
    headers = parse_adr_headers(md)
    assert len(headers) == 2
    assert headers[0].id == "ADR-001"
    assert headers[0].status == "accepted"
    assert headers[1].supersedes == ("ADR-001",)


def test_parse_adr_headers_handles_old_format():
    md = "## ADR-042 | 2026-04-13 | foo | Commit abcd1234\n### Status: accepted\n"
    headers = parse_adr_headers(md)
    assert len(headers) == 1
    assert headers[0].id == "ADR-042"


def test_extract_adr_id_number_parses_and_rejects():
    assert extract_adr_id_number("ADR-027") == 27
    assert extract_adr_id_number("ADR-") is None
    assert extract_adr_id_number("not an id") is None


def test_find_duplicate_adr_ids_detects_repeats():
    headers = [
        ADRHeader("ADR-001", "a", 1),
        ADRHeader("ADR-002", "b", 2),
        ADRHeader("ADR-001", "a-dup", 3),
    ]
    assert find_duplicate_adr_ids(headers) == ["ADR-001"]


def test_find_gaps_in_adr_ids_detects_missing():
    headers = [
        ADRHeader("ADR-023", "a", 1),
        ADRHeader("ADR-025", "b", 2),
        ADRHeader("ADR-027", "c", 3),
    ]
    assert find_gaps_in_adr_ids(headers) == [24, 26]


def test_find_gaps_in_adr_ids_no_gaps():
    headers = [ADRHeader("ADR-001", "a", 1), ADRHeader("ADR-002", "b", 2)]
    assert find_gaps_in_adr_ids(headers) == []


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
