"""Tests for combine_coverage.py — the Phase-2 monorepo coverage-combine tool.

The crux test runs REAL ``coverage`` on a synthetic 2-plugin + shared fixture
(faithfully reproducing the ``cd plugins/<name> && --cov`` recording that makes
plugin data files plugin-CWD-relative) and asserts the combined ``coverage.xml``
carries **repo-relative** filenames — the property a single global ``[paths]``
mapping cannot produce.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.combine_coverage as mod
from scripts.tools.combine_coverage import (
    combine_to_xml,
    discover_data_files,
    label_of,
    paths_alias_for,
)

_MOD_TEMPLATE = (
    "def f(x):\n"
    "    if x > 0:\n"
    "        return {up!r}\n"
    "    return {down!r}\n"
    "\n"
    "f(1)\n"  # executes the truthy branch only -> the falsy return stays uncovered
)


def _coverage_available() -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "coverage", "--version"],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run_coverage_on(file_rel: str, cwd: Path, data_file: Path) -> None:
    """Run ``coverage run <file_rel>`` from ``cwd`` with relative_files on,
    writing the data to ``data_file`` (mirrors a real per-plugin measurement)."""
    rc = cwd / ".rc_measure"
    rc.write_text("[run]\nrelative_files = true\n", encoding="utf-8")
    env = {**_os_environ(), "COVERAGE_FILE": str(data_file),
           "COVERAGE_RCFILE": str(rc)}
    subprocess.run([sys.executable, "-m", "coverage", "run", file_rel],
                   cwd=str(cwd), env=env, capture_output=True, text=True,
                   timeout=120, check=True)


def _os_environ() -> dict:
    import os
    return dict(os.environ)


def _build_fixture(root: Path) -> Path:
    """A synthetic repo: plugins/pa/scripts, plugins/pb/scripts, shared/. Each
    'plugin' is measured from its OWN dir (plugin-CWD-relative data); shared is
    measured from the repo root (already repo-relative). Returns the data dir."""
    (root / "plugins/pa/scripts").mkdir(parents=True)
    (root / "plugins/pb/scripts").mkdir(parents=True)
    (root / "shared").mkdir(parents=True)
    (root / "plugins/pa/scripts/mod_a.py").write_text(
        _MOD_TEMPLATE.format(up="pos", down="neg"), encoding="utf-8")
    (root / "plugins/pb/scripts/mod_b.py").write_text(
        _MOD_TEMPLATE.format(up="POS", down="NEG"), encoding="utf-8")
    (root / "shared/mod_s.py").write_text(
        _MOD_TEMPLATE.format(up="S", down="s"), encoding="utf-8")

    data = root / ".cov-data"
    data.mkdir()
    # Plugins: run FROM the plugin dir so coverage records `scripts/mod_x.py`.
    _run_coverage_on("scripts/mod_a.py", root / "plugins/pa", data / ".coverage.pa")
    _run_coverage_on("scripts/mod_b.py", root / "plugins/pb", data / ".coverage.pb")
    # Shared: run from the repo root -> records `shared/mod_s.py` (repo-relative).
    _run_coverage_on("shared/mod_s.py", root, data / ".coverage.shared")
    return data


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
class TestDiscovery:
    def test_finds_labelled_files_ignores_bare(self, tmp_path):
        (tmp_path / ".coverage").write_text("x", encoding="utf-8")
        (tmp_path / ".coverage.shared").write_text("x", encoding="utf-8")
        (tmp_path / ".coverage.shipwright-build").write_text("x", encoding="utf-8")
        (tmp_path / ".coverage.combined").write_text("x", encoding="utf-8")
        (tmp_path / "unrelated.txt").write_text("x", encoding="utf-8")
        names = [p.name for p in discover_data_files(tmp_path)]
        assert names == [".coverage.shared", ".coverage.shipwright-build"]

    def test_missing_dir_is_empty(self, tmp_path):
        assert discover_data_files(tmp_path / "nope") == []

    def test_label_of(self):
        assert label_of(Path(".coverage.shipwright-build")) == "shipwright-build"
        assert label_of(Path("/a/b/.coverage.shared")) == "shared"

    def test_paths_alias_only_for_real_plugin_scripts(self, tmp_path):
        (tmp_path / "plugins/pa/scripts").mkdir(parents=True)
        assert paths_alias_for("pa", tmp_path) == "plugins/pa/scripts/"
        # shared / integration / unknown -> no remap (already repo-relative)
        assert paths_alias_for("shared", tmp_path) is None
        assert paths_alias_for("integration", tmp_path) is None
        assert paths_alias_for("pb", tmp_path) is None  # no plugins/pb/scripts dir

    def test_resolve_worker_suffixed_label(self, tmp_path):
        # pytest-cov parallel/xdist appends .<host>.<pid>.<rand> to COVERAGE_FILE;
        # a suffixed label must still resolve to the plugin (else silent drop).
        (tmp_path / "plugins/shipwright-test/scripts").mkdir(parents=True)
        (tmp_path / "plugins/shipwright-test-extra/scripts").mkdir(parents=True)
        from scripts.tools.combine_coverage import resolve_plugin_label
        assert resolve_plugin_label("shipwright-test", tmp_path) == "shipwright-test"
        assert resolve_plugin_label(
            "shipwright-test.host.123.456", tmp_path) == "shipwright-test"
        # dotted delimiter: never matches the wrong sibling plugin
        assert resolve_plugin_label(
            "shipwright-test-extra.gw0", tmp_path) == "shipwright-test-extra"
        assert resolve_plugin_label("shared", tmp_path) is None


# --------------------------------------------------------------------------- #
# Absent-input safety
# --------------------------------------------------------------------------- #
class TestAbsentSafe:
    def test_no_data_dir_is_na_no_xml(self, tmp_path):
        out = tmp_path / "coverage.xml"
        result = combine_to_xml(tmp_path, tmp_path / "empty", out)
        assert result["status"] == "n-a"
        assert result["combined"] == 0
        assert not out.exists()

    def test_main_exits_zero_when_absent(self, tmp_path):
        rc = mod.main(["--project-root", str(tmp_path),
                       "--data-dir", str(tmp_path / "empty")])
        assert rc == 0


# --------------------------------------------------------------------------- #
# THE CRUX — real coverage over a synthetic monorepo fixture
# --------------------------------------------------------------------------- #
class TestCombineRealFixture:
    def _skip_if_no_coverage(self):
        if not _coverage_available():
            import os
            if os.environ.get("CI", "").lower() in ("true", "1"):
                import pytest
                pytest.fail("coverage missing in CI — provision `uv run --with "
                            "pytest-cov` (see ci.yml 'Run shared tests').")
            import pytest
            pytest.skip("coverage not installed (local); run via `uv run --with "
                        "pytest-cov`.")

    def test_combined_xml_is_repo_relative(self, tmp_path):
        self._skip_if_no_coverage()
        data = _build_fixture(tmp_path)
        out = tmp_path / "coverage.xml"
        result = combine_to_xml(tmp_path, data, out)
        assert result["status"] == "ok", result
        assert result["combined"] == 3
        assert out.exists()
        xml = out.read_text(encoding="utf-8")
        # Every source is attributed to its REPO-RELATIVE path — the property a
        # single global [paths] mapping cannot produce (plugin identity is lost
        # in the plugin-CWD-relative data files).
        assert 'filename="plugins/pa/scripts/mod_a.py"' in xml, xml
        assert 'filename="plugins/pb/scripts/mod_b.py"' in xml, xml
        assert 'filename="shared/mod_s.py"' in xml, xml
        # No un-remapped bare `scripts/...` entry survived.
        assert 'filename="scripts/mod_a.py"' not in xml
        # Blended line-rate is a real fraction in (0, 1): each mod has one
        # uncovered branch, so it is neither 0% nor 100%.
        assert result["total"] is not None
        assert 0.0 < result["total"] < 100.0

    def test_total_matches_line_rate_attr(self, tmp_path):
        self._skip_if_no_coverage()
        data = _build_fixture(tmp_path)
        out = tmp_path / "coverage.xml"
        result = combine_to_xml(tmp_path, data, out)
        # 3 modules x (say) N lines each, one uncovered return per module.
        # Just assert the recorder's total equals the xml's own line-rate.
        from scripts.tools.measure_diff_coverage import line_rate_percent
        assert result["total"] == line_rate_percent(out)

    def test_idempotent_rerun_keeps_data(self, tmp_path):
        # --keep means the data dir is untouched, so a second run reproduces.
        self._skip_if_no_coverage()
        data = _build_fixture(tmp_path)
        out = tmp_path / "coverage.xml"
        first = combine_to_xml(tmp_path, data, out)
        second = combine_to_xml(tmp_path, data, out)
        assert first["total"] == second["total"]
        assert {p.name for p in discover_data_files(data)} == {
            ".coverage.pa", ".coverage.pb", ".coverage.shared"}

    def test_two_worker_files_per_plugin_both_contribute(self, tmp_path):
        # Regression (external review): pytest-cov parallel/xdist writes
        # `.coverage.<plugin>.<worker>` files. Both must remap to the plugin and
        # their coverage must MERGE — not be silently dropped as repo-relative.
        self._skip_if_no_coverage()
        (tmp_path / "plugins/pa/scripts").mkdir(parents=True)
        (tmp_path / "plugins/pa/scripts/mod_two.py").write_text(
            "def f1():\n    return 'one'\n"
            "def f2():\n    return 'two'\n"
            "import os\n"
            "if os.environ.get('PICK') == '1':\n    f1()\nelse:\n    f2()\n",
            encoding="utf-8")
        data = tmp_path / ".cov-data"
        data.mkdir()

        def _run(pick: str, out_name: str):
            rc = tmp_path / "plugins/pa" / ".rc"
            rc.write_text("[run]\nrelative_files = true\n", encoding="utf-8")
            env = {**_os_environ(), "PICK": pick,
                   "COVERAGE_FILE": str(data / out_name),
                   "COVERAGE_RCFILE": str(rc)}
            subprocess.run([sys.executable, "-m", "coverage", "run",
                            "scripts/mod_two.py"],
                           cwd=str(tmp_path / "plugins/pa"), env=env,
                           capture_output=True, text=True, timeout=120, check=True)

        _run("1", ".coverage.pa.gw0")  # covers f1 + the if-branch
        _run("2", ".coverage.pa.gw1")  # covers f2 + the else-branch

        both = combine_to_xml(tmp_path, data, tmp_path / "both.xml")
        assert both["status"] == "ok"
        assert 'filename="plugins/pa/scripts/mod_two.py"' in (
            tmp_path / "both.xml").read_text(encoding="utf-8")
        # Union of the two workers covers every line -> 100%.
        assert both["total"] == 100.0

        # Sanity: a single worker alone is < 100% (so the merge really happened).
        (data / ".coverage.pa.gw1").unlink()
        one = combine_to_xml(tmp_path, data, tmp_path / "one.xml")
        assert one["total"] < 100.0


class TestPartialCombine:
    """Review finding #1: a PARTIAL combine (some tiers fail to fold in) must NOT
    masquerade as a repo-wide total — else record_coverage_total.py commits a
    subset baseline. It is flagged non-ok + main() exits non-zero."""

    def _skip_if_no_coverage(self):
        if not _coverage_available():
            import pytest
            pytest.skip("coverage not installed (local)")

    def test_partial_is_flagged_not_ok(self, tmp_path, monkeypatch):
        self._skip_if_no_coverage()
        data = _build_fixture(tmp_path)  # pa, pb, shared — all valid
        real = mod._run_coverage

        def flaky(args, **kw):
            # Force the combine of the pb tier to fail; everything else real.
            if args[:1] == ["combine"] and any(".coverage.pb" in a for a in args):
                return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
            return real(args, **kw)

        monkeypatch.setattr(mod, "_run_coverage", flaky)
        result = combine_to_xml(tmp_path, data, tmp_path / "cov.xml")
        assert result["status"] == "partial", result
        assert result["discovered"] == 3 and result["combined"] == 2
        assert "pb" in result["failed"]

    def test_partial_main_exits_nonzero(self, tmp_path, monkeypatch):
        self._skip_if_no_coverage()
        data = _build_fixture(tmp_path)
        real = mod._run_coverage

        def flaky(args, **kw):
            if args[:1] == ["combine"] and any(".coverage.pb" in a for a in args):
                return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
            return real(args, **kw)

        monkeypatch.setattr(mod, "_run_coverage", flaky)
        rc = mod.main(["--project-root", str(tmp_path),
                       "--data-dir", str(data), "--output", str(tmp_path / "c.xml")])
        assert rc == 1
