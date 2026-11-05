"""Build, autonomous run (e2e run 22): explicit brief value, hard requirement over a visible
extra, declared dev tooling -- decided by rule and recorded, not asked."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.05/AC05")

ROOT = Path(__file__).resolve().parent.parent


def _flat(rel):
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


def test_skill_decides_the_three_build_conflicts_by_rule():
    s = _flat("skills/build/SKILL.md")
    assert "Autonomous run, two more rules — decide, do not ask:" in s
    assert "--kind brief-wins|hard-constraint" in s and "known-differences.md" in s
    assert "--kind dev-tooling --phase Build" in s and "or an interactive run: ask" in s
    assert "a manifest changed since the section started" in s


def test_spec_reviewer_settles_by_rule_only_in_an_autonomous_run():
    r = _flat("agents/spec-reviewer.md")
    assert "Autonomous run: settle by rule, never escalate what a rule decides." in r
    assert "an interactive run keeps items 3 and 5 as written" in r
    assert "REJECTS as `unfaithful` (never `contradiction`), citing the brief line as the winner" in r
    assert "a tooltip-only placement does not satisfy it" in r
    assert "A hard requirement (no layout shift, no height change" in r
    assert "Only when no ranking is possible (both hard, or both extras) is it REJECT `contradiction`" in r


def test_writeback_reference_documents_both_rules():
    w = _flat("skills/build/references/requirement-writeback.md")
    assert "Explicit brief value and hard requirements (autonomous runs)." in w
    assert "--kind hard-constraint" in w and "NNN px" in w


def _setup_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_build_setup_inproc", ROOT / "scripts" / "checks" / "setup_implementation_session.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_section_setup_records_the_phase_start_baseline_dev_tooling_compares_with(tmp_path, monkeypatch):
    import subprocess
    import sys
    setup = _setup_module()
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-a")
    assert setup.record_boundary_baseline(tmp_path, "01-auth") == "not_written"  # not a git repo
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    assert setup.record_boundary_baseline(tmp_path, "01-auth") == "written"
    assert (tmp_path / ".shipwright" / "build-boundary-baseline-01-auth.json").is_file()
    assert setup.record_boundary_baseline(tmp_path, "01-auth") == "kept"  # a resume never re-snapshots
    monkeypatch.setitem(sys.modules, "shared_lib_loader", None)  # an install without the shared module
    assert setup.record_boundary_baseline(tmp_path, "02-x") == "not_written"


def test_dev_tooling_rule_is_hardened_where_build_reads_it():
    s = _flat("skills/build/SKILL.md")
    assert '--scope "{section_name}"' in s
    assert "an autonomous run always adds `--ignore-scripts` to every npm/pnpm/yarn install" in s
