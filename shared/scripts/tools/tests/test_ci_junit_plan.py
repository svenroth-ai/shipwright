"""`ci_junit_plan.py` (iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC4).

Covers: `plan` discovers this repo's real test roots and writes a plan.json
whose rel_root strings match what the three ci.yml loops iterate over (a
plugin's `tests/`, each shared dir, `integration-tests`); `lookup` resolves
one root's planned path and fails loud on an unknown one; `verify` catches
a root whose planned JUnit file was never produced.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.ci_junit_plan as mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_plan_discovers_real_repo_roots_and_writes_plan_json(tmp_path):
    out_dir = tmp_path / "ci-junit"
    entries = mod.write_plan(_REPO_ROOT, out_dir)

    rel_roots = {e["rel_root"] for e in entries}
    assert "shared/tests" in rel_roots
    assert "integration-tests" in rel_roots
    assert any(r.startswith("plugins/") and r.endswith("/tests") for r in rel_roots)

    on_disk = json.loads((out_dir / "plan.json").read_text(encoding="utf-8"))
    assert on_disk == entries


def test_plugin_root_base_matches_its_own_plugin_dir(tmp_path):
    entries = mod.write_plan(_REPO_ROOT, tmp_path / "ci-junit")
    plugin_entry = next(e for e in entries if e["rel_root"].startswith("plugins/"))
    plugin_dir = plugin_entry["rel_root"].rsplit("/tests", 1)[0]
    assert plugin_entry["base"] == plugin_dir


def test_shared_and_integration_roots_have_empty_base(tmp_path):
    entries = mod.write_plan(_REPO_ROOT, tmp_path / "ci-junit")
    by_root = {e["rel_root"]: e for e in entries}
    assert by_root["shared/tests"]["base"] == ""
    assert by_root["integration-tests"]["base"] == ""


class TestLookup:
    def test_lookup_prints_the_planned_path(self, tmp_path, capsys):
        out_dir = tmp_path / "ci-junit"
        mod.write_plan(_REPO_ROOT, out_dir)
        code = mod.main([
            "lookup", "--plan", str(out_dir / "plan.json"), "--rel-root", "shared/tests",
        ])
        assert code == 0
        printed = capsys.readouterr().out.strip()
        assert printed == next(
            e["junit_out"] for e in json.loads((out_dir / "plan.json").read_text())
            if e["rel_root"] == "shared/tests"
        )

    def test_lookup_of_an_unknown_root_fails_loud(self, tmp_path, capsys):
        out_dir = tmp_path / "ci-junit"
        mod.write_plan(_REPO_ROOT, out_dir)
        code = mod.main([
            "lookup", "--plan", str(out_dir / "plan.json"), "--rel-root", "no/such/root",
        ])
        assert code == 2
        assert "no/such/root" in capsys.readouterr().err


class TestVerify:
    def test_verify_passes_when_every_planned_file_exists(self, tmp_path, capsys):
        out_dir = tmp_path / "ci-junit"
        entries = mod.write_plan(_REPO_ROOT, out_dir)
        for e in entries:
            Path(e["junit_out"]).parent.mkdir(parents=True, exist_ok=True)
            Path(e["junit_out"]).write_text("<testsuites/>", encoding="utf-8")

        code = mod.main(["verify", "--plan", str(out_dir / "plan.json")])
        assert code == 0
        assert f"verified {len(entries)} test root(s)" in capsys.readouterr().out

    def test_verify_fails_when_one_root_never_produced_its_report(self, tmp_path, capsys):
        out_dir = tmp_path / "ci-junit"
        entries = mod.write_plan(_REPO_ROOT, out_dir)
        for e in entries[1:]:  # leave the first root's report un-produced
            Path(e["junit_out"]).parent.mkdir(parents=True, exist_ok=True)
            Path(e["junit_out"]).write_text("<testsuites/>", encoding="utf-8")

        code = mod.main(["verify", "--plan", str(out_dir / "plan.json")])
        assert code == 2
        err = capsys.readouterr().err
        assert entries[0]["rel_root"] in err


class TestCliSmoke:
    def test_real_subprocess_plan_invocation_imports_and_runs(self, tmp_path):
        """`plan` needs pytest importable (it loads conftest.py, which does
        `import pytest`) — pytest is a dev-only optional dependency, so this
        must pass `--with pytest`, unlike a bare pytest-collected import.
        Guards the same sys.path bug class as the module's own comment:
        `--out` targets a tmp dir OUTSIDE the repo, never mutating it."""
        out_dir = tmp_path / "ci-junit"
        result = subprocess.run(
            ["uv", "run", "--with", "pytest", "shared/scripts/tools/ci_junit_plan.py",
             "plan", "--out", str(out_dir)],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert "ModuleNotFoundError" not in result.stderr
        assert result.returncode == 0
        assert (out_dir / "plan.json").is_file()
