"""Mine test files for Acceptance Criteria (Fix 5).

Tests are the most honest spec a repo carries. The miner maps each FR's
`source_file` onto its sibling test files (Jest / Vitest / Mocha shape
in JS/TS, `def test_*` + docstring in Python) and harvests the test
descriptions as bullet-point ACs.

Used only when `enrichment.acceptance_draft` is empty / "TBD" — the
enrichment is the richest source when it exists.
"""

from __future__ import annotations

from pathlib import Path

from lib.test_acceptance_miner import mine_acceptance_criteria


# ---------------------------------------------------------------------------
# Sibling-file resolution
# ---------------------------------------------------------------------------


def test_returns_empty_when_no_sibling_test_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.ts").write_text("export const foo = 1;\n", encoding="utf-8")
    result = mine_acceptance_criteria(tmp_path, "src/foo.ts")
    assert result == []


def test_returns_empty_when_source_file_is_dash(tmp_path: Path) -> None:
    """Some FRs come from crawl-only origins with no source_file. Should be
    a clean no-op, not an error."""
    assert mine_acceptance_criteria(tmp_path, "—") == []
    assert mine_acceptance_criteria(tmp_path, "") == []


# ---------------------------------------------------------------------------
# Jest / Vitest shape
# ---------------------------------------------------------------------------


def test_mines_vitest_describe_it_pairs(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "users.ts").write_text("export const users = [];\n", encoding="utf-8")
    (src / "users.test.ts").write_text(
        "import { describe, it, expect } from 'vitest';\n"
        "describe('users service', () => {\n"
        "  it('returns the active list when called without args', () => {});\n"
        "  it('filters out deleted entries', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/users.ts")
    assert "users service: returns the active list when called without args" in result
    assert "users service: filters out deleted entries" in result


def test_mines_jest_test_calls(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "math.ts").write_text("export const add = (a,b)=>a+b;\n", encoding="utf-8")
    (src / "math.test.ts").write_text(
        "test('add returns the sum of two numbers', () => {});\n"
        "test('add handles negative inputs', () => {});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/math.ts")
    assert any("add returns the sum of two numbers" in ac for ac in result)
    assert any("add handles negative inputs" in ac for ac in result)


def test_mines_jest_spec_suffix(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
    (src / "index.spec.tsx").write_text(
        "describe('App', () => {\n"
        "  it('renders the header', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/index.tsx")
    assert any("renders the header" in ac for ac in result)


def test_mines_underscore_tests_directory_layout(tmp_path: Path) -> None:
    """`__tests__/foo.test.ts` is the conventional sibling location."""
    (tmp_path / "src" / "__tests__").mkdir(parents=True)
    (tmp_path / "src" / "foo.ts").write_text("export const foo = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "__tests__" / "foo.test.ts").write_text(
        "it('foo computes the right value', () => {});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/foo.ts")
    assert any("foo computes the right value" in ac for ac in result)


def test_mines_top_level_tests_directory_layout(tmp_path: Path) -> None:
    """`tests/foo.test.ts` parallel to `src/foo.ts` is also conventional."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "bar.ts").write_text("export const bar = 1;\n", encoding="utf-8")
    (tmp_path / "tests" / "bar.test.ts").write_text(
        "it('bar handles edge cases', () => {});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/bar.ts")
    assert any("bar handles edge cases" in ac for ac in result)


# ---------------------------------------------------------------------------
# Python pytest shape
# ---------------------------------------------------------------------------


def test_mines_pytest_test_functions_with_docstrings(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    (tmp_path / "src" / "test_calc.py").write_text(
        "def test_add_returns_sum():\n"
        "    \"\"\"add returns the sum of two integers.\"\"\"\n"
        "    pass\n"
        "def test_add_handles_negatives():\n"
        "    pass\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/calc.py")
    assert any("add returns the sum of two integers" in ac for ac in result)
    # No docstring → fall back to humanized function name (underscores → spaces).
    assert any("add handles negatives" in ac for ac in result)


def test_mines_pytest_top_level_tests_dir(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def foo(): pass\n", encoding="utf-8")
    (tmp_path / "tests" / "test_foo.py").write_text(
        "def test_foo_works():\n    pass\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/foo.py")
    assert any("foo works" in ac.lower() for ac in result)


# ---------------------------------------------------------------------------
# Cap + ordering invariants
# ---------------------------------------------------------------------------


def test_caps_at_ten_acs_per_fr(tmp_path: Path) -> None:
    """The 11th + ACs are dropped to keep spec.md scannable."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.ts").write_text("export const x = 1;\n", encoding="utf-8")
    body_lines = [f"it('case {i}', () => {{}});" for i in range(20)]
    (tmp_path / "src" / "x.test.ts").write_text("\n".join(body_lines), encoding="utf-8")
    result = mine_acceptance_criteria(tmp_path, "src/x.ts")
    assert len(result) == 10
