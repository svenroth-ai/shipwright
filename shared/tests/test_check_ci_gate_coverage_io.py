"""I/O-layer + live-repo tests for the CI gate-coverage guard.

Split from ``test_check_ci_gate_coverage.py`` (which holds the pure
classification/policy tests) to keep each test file within the 300-LOC cap.
Covers ``lib/ci_gate_scan.py`` (workflow parsing round-trip + test-dir
discovery) and the assertion that the LIVE workflows pass the guard.
"""

from __future__ import annotations

from pathlib import Path

from lib.ci_gate_allowlist import LOOSE_GATE_ALLOWLIST
from tools.check_ci_gate_coverage import (
    discover_test_dirs,
    is_loose,
    parse_workflows,
    run_all,
    stale_allowlist_entries,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Boundary probe / round-trip (touches_io_boundary: yaml.safe_load)
# --------------------------------------------------------------------------- #
class TestWorkflowParsingRoundTrip:
    def _write(self, root: Path, name: str, body: str) -> None:
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / name).write_text(body, encoding="utf-8")

    def test_parse_captures_continue_on_error_and_run(self, tmp_path):
        self._write(tmp_path, "x.yml", (
            "name: X\n"
            "on:\n  push:\n    branches: [main]\n"
            "jobs:\n"
            "  checks:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Loose lint\n"
            "        run: ruff check . || true\n"
            "        continue-on-error: true\n"
        ))
        steps = parse_workflows(tmp_path)
        assert len(steps) == 1
        s = steps[0]
        assert s.workflow == "x.yml"
        assert s.name == "Loose lint"
        assert s.continue_on_error is True
        assert "|| true" in s.run
        assert is_loose(s)

    def test_malformed_yaml_is_skipped_not_crash(self, tmp_path):
        self._write(tmp_path, "bad.yml", "jobs: [unclosed\n")
        assert parse_workflows(tmp_path) == []


class TestDiscoverTestDirs:
    def test_discovers_roots_and_excludes_fixtures(self, tmp_path):
        (tmp_path / "plugins" / "p1").mkdir(parents=True, exist_ok=True)
        (tmp_path / "plugins" / "p1" / "pyproject.toml").write_text(
            "[project]\nname = 'p1'\n", encoding="utf-8"
        )
        for rel in (
            "plugins/p1/tests/test_a.py",
            "shared/tests/test_b.py",
            "shared/sub/tests/test_c.py",
            "integration-tests/test_d.py",
            "shared/x/fixtures/tests/test_excluded.py",
            "plugins/p1/tests/fixtures/repo/tests/test_nested.py",
        ):
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        found = discover_test_dirs(tmp_path)
        assert found == [
            "integration-tests",
            "plugins/p1/tests",
            "shared/sub/tests",
            "shared/tests",
        ]

    def test_plugin_tests_without_pyproject_not_discovered(self, tmp_path):
        # CI's plugin loop gates on `[ -f pyproject.toml ]`, so a plugin tests
        # dir without one is skipped by CI — discovery must agree.
        p = tmp_path / "plugins" / "p2" / "tests" / "test_z.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("def test_z():\n    assert True\n", encoding="utf-8")
        assert "plugins/p2/tests" not in discover_test_dirs(tmp_path)


# --------------------------------------------------------------------------- #
# AC6 — the LIVE repo passes the guard (no green-while-broken)
# --------------------------------------------------------------------------- #
class TestRealRepo:
    def test_live_workflows_pass_the_guard(self):
        result = run_all(REPO_ROOT)
        assert result["uncovered_dirs"] == [], (
            f"uncovered test dirs: {result['uncovered_dirs']}"
        )
        assert result["loose_gates"] == [], (
            f"non-allowlisted loose gates: "
            f"{[(s.workflow, s.name) for s in result['loose_gates']]}"
        )
        assert result["security_problems"] == [], result["security_problems"]

    def test_live_allowlist_has_no_stale_entries(self):
        steps = parse_workflows(REPO_ROOT)
        stale = stale_allowlist_entries(steps, LOOSE_GATE_ALLOWLIST)
        assert stale == [], f"stale allowlist entries: {[(e.workflow, e.step) for e in stale]}"

    def test_live_repo_discovers_the_known_test_roots(self):
        found = set(discover_test_dirs(REPO_ROOT))
        for expected in ("shared/tests", "shared/scripts/tests",
                         "shared/scripts/tools/tests", "integration-tests"):
            assert expected in found, f"{expected} not discovered: {sorted(found)}"
