"""Iterate 2 Sub-2B: known_issues TODO scanner must skip test fixtures by default.

Test-fixture files (under tests/, *_test.py, *.spec.ts, etc.) commonly
contain TODO/FIXME strings as inputs to the inventory tests themselves.
Without a default skip, those landed as 22-of-28 entries in the
shipwright self-adoption's known_issues.md, drowning real findings.

Default: skip test-shaped paths. Opt-in via `scan_tests=True` for
codebases whose test files carry real workflow TODOs.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the plugin's lib importable when pytest is invoked from monorepo root.
_PLUGIN_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_LIB))

from known_issues_inventory import write_known_issues_inventory  # type: ignore[import-not-found]


def _setup_project(tmp_path: Path) -> Path:
    """tmp project with a source TODO and several test-fixture-style TODOs."""
    src = tmp_path / "src" / "feature.py"
    src.parent.mkdir(parents=True)
    src.write_text("# TODO: real source TODO\n", encoding="utf-8")

    # Default-skip targets:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text(
        '"""TODO: fixture string for test"""\n', encoding="utf-8"
    )
    test_in_root = tmp_path / "test_inventory.py"
    test_in_root.write_text("# FIXME: another fixture\n", encoding="utf-8")
    spec_ts = tmp_path / "src" / "feature.spec.ts"
    spec_ts.write_text("// TODO: spec fixture\n", encoding="utf-8")
    test_ts = tmp_path / "src" / "feature.test.ts"
    test_ts.write_text("// HACK: ts test fixture\n", encoding="utf-8")
    py_test = tmp_path / "src" / "module_test.py"
    py_test.write_text("# TODO: trailing-test-suffix fixture\n", encoding="utf-8")

    return tmp_path


def test_default_skips_test_fixtures(tmp_path: Path) -> None:
    """Default scan_tests=False must hide all test-fixture markers."""
    root = _setup_project(tmp_path)
    result = write_known_issues_inventory(root)
    by_marker = result["by_marker"]
    # Only 1 real source TODO survives; all fixture entries are skipped.
    assert by_marker.get("TODO", 0) == 1, (
        f"expected 1 source TODO, got {by_marker}"
    )
    assert by_marker.get("FIXME", 0) == 0, (
        f"FIXME from tests/test_inventory.py should have been skipped"
    )
    assert by_marker.get("HACK", 0) == 0, (
        f"HACK from feature.test.ts should have been skipped"
    )

    body = (root / ".shipwright/agent_docs/known_issues.md").read_text(encoding="utf-8")
    assert "src/feature.py" in body, "source TODO must appear"
    assert "test_foo.py" not in body
    assert "test_inventory.py" not in body
    assert "feature.spec.ts" not in body
    assert "feature.test.ts" not in body
    assert "module_test.py" not in body


def test_scan_tests_includes_fixtures(tmp_path: Path) -> None:
    """With scan_tests=True, fixture entries must come back."""
    root = _setup_project(tmp_path)
    result = write_known_issues_inventory(root, scan_tests=True)
    by_marker = result["by_marker"]
    # 1 source + 4 fixture TODOs (test_foo, test_inventory FIXME, spec.ts, test.ts HACK, module_test.py)
    # Counts: TODO from src + tests/test_foo + spec.ts + module_test.py = 4 TODO total
    # FIXME from test_inventory.py = 1
    # HACK from feature.test.ts = 1
    assert by_marker.get("TODO", 0) >= 4, by_marker
    assert by_marker.get("FIXME", 0) == 1, by_marker
    assert by_marker.get("HACK", 0) == 1, by_marker
