"""The Shipwright repository's own project profile: a faithful copy of ``claude-plugin`` plus repo-only rules."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_architecture_rules as par  # noqa: E402
import profile_resolver as pr  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC33")
ROOT = Path(__file__).resolve().parents[2]
NAME, BUNDLED, GENERIC = "shipwright-monorepo", "claude-plugin", "python-plugin-monorepo"
OWN = ("name", "description", "architecture_rules")
REPO_ONLY = {
    "one-pytest-root-per-process",
    "bloat-anti-ratchet-pre-commit",
    "bloat-stop-gate-new-crossings",
    "bloat-no-growth-past-baseline-in-ci",
    "bloat-baseline-discipline",
    "hooks-json-quote-plugin-root",
    "profile-copy-notes-for-this-repo",
}
CONFIGS = ("shipwright_run_config.json", "shipwright_project_config.json", "shipwright_build_config.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _own() -> dict:
    return _load(ROOT / ".shipwright" / "profiles" / f"{NAME}.json")


def _bundled(name: str = BUNDLED) -> dict:
    return _load(ROOT / "shared" / "profiles" / f"{name}.json")


@pytest.mark.parametrize("config", CONFIGS)
def test_every_config_names_the_profile_and_resolves_to_the_project_file(config):
    name = _load(ROOT / config)["profile"]
    assert name == NAME
    res = pr.resolve_profile(name, ROOT)
    assert res.source == "project" and Path(res.path) == ROOT / ".shipwright" / "profiles" / f"{NAME}.json"


def test_copy_equals_the_bundled_profile_on_every_key_but_its_own():
    own, bundled = _own(), _bundled()
    assert own["name"] == NAME != bundled["name"]
    assert set(own) == set(bundled)
    for key in set(bundled) - set(OWN):
        assert own[key] == bundled[key], key


def test_toolchain_data_equals_the_generic_profile_the_repo_used_before():
    own, old = _own(), _bundled(GENERIC)
    for key in ("testing", "linting", "dev_server", "services", "deploy", "required_env_vars", "version"):
        assert own[key] == old[key], key


def test_copy_contains_every_bundled_rule_unchanged_and_adds_repo_only_ones():
    own_rules, bundled_rules = _own()["architecture_rules"], _bundled()["architecture_rules"]
    assert own_rules[: len(bundled_rules)] == bundled_rules
    extra = own_rules[len(bundled_rules):]
    assert {r["id"] for r in extra} == REPO_ONLY
    rs = par.load_rules(own_rules)
    assert rs.errors == [] and rs.warnings == [] and all(r.why and not r.legacy for r in rs.rules)
    assert len({r.id for r in rs.rules}) == len(rs.rules)


def test_repo_only_mechanism_paths_exist_and_validate_against_the_repo_root():
    rs = par.load_rules(_own()["architecture_rules"])
    by_id = {r.id: r for r in rs.rules}
    for rid in sorted(REPO_ONLY):
        if by_id[rid].enforcement.startswith("prompt-only"):
            assert not by_id[rid].mechanism, rid
            continue
        assert by_id[rid].mechanism, rid
        for path in by_id[rid].mechanism:
            assert (ROOT / path).is_file(), path
    assert par.check_paths(rs.rules, ROOT) == []


def test_each_repo_only_mechanism_is_invoked_by_something():
    """A mechanism counts only if something runs it: the hook script, the CI workflow and the guard's own entry point."""
    hook = (ROOT / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert "shared/scripts/hooks/anti_ratchet_check.py" in hook
    wf = (ROOT / ".github" / "workflows" / "bloat-check.yml").read_text(encoding="utf-8")
    assert "anti_ratchet_check.py" in wf and "shipwright_rel_at.py bloat_baseline" in wf and "exit 1" in wf   # R1d: resolved per commit
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "shared/tests" in ci and "pytest" in ci
    hooks = (ROOT / "plugins" / "shipwright-iterate" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "bloat_gate_on_stop.py" in hooks and "check_file_size.py" in hooks
    conftest = (ROOT / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_sessionstart" in conftest and "raise pytest.UsageError" in conftest and "len(roots) > 1" in conftest
    install = (ROOT / "scripts" / "install-hooks.sh").read_text(encoding="utf-8")
    assert "core.hooksPath" in install and 'target_path="scripts/hooks"' in install
    quoting = (ROOT / "shared" / "tests" / "test_hooks_json_quoting.py").read_text(encoding="utf-8")
    assert "def test_hooks_json_quotes_plugin_root_path" in quoting


def test_resolve_cli_validates_the_project_profile_without_rule_errors():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "shared" / "scripts" / "tools" / "resolve_profile.py"), "validate",
         "--project-root", str(ROOT), "--name", NAME, "--json"],
        capture_output=True, check=False)
    data = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 0 and data["valid"] and data["source"] == "project"
    assert data["rules_valid"] and data["rule_errors"] == []


def test_conventions_md_carries_the_current_rendered_block():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "shared" / "scripts" / "tools" / "render_architecture_rules.py"),
         "--project-root", str(ROOT), "--check"],
        capture_output=True, check=False)
    assert proc.returncode == 0, "re-run render_architecture_rules.py --project-root . (a union merge may have duplicated block lines): " + proc.stderr.decode("utf-8", "replace")
    text = (ROOT / ".shipwright" / "agent_docs" / "conventions.md").read_text(encoding="utf-8")
    assert f"generated from stack profile `{NAME}`" in text and "one-pytest-root-per-process" in text
