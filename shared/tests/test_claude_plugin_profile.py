"""The bundled ``claude-plugin`` profile: valid, Python data equal to the generic profile, rules and mechanisms real."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_architecture_rules as par  # noqa: E402
import profile_resolver as pr  # noqa: E402
from lib.ci_workflow import TEMPLATE_BY_PROFILE  # noqa: E402
from lib.codeql_workflow import CODEQL_LANGUAGES_BY_PROFILE  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC30", "FR-01.01/AC31", "FR-01.01/AC32")
ROOT = Path(__file__).resolve().parents[2]
NAME, GENERIC = "claude-plugin", "python-plugin-monorepo"


def _bundled(name: str) -> dict:
    return json.loads((ROOT / "shared" / "profiles" / f"{name}.json").read_text(encoding="utf-8"))


def test_profile_resolves_as_a_valid_bundled_profile():
    res = pr.resolve_profile(NAME, None, search_dirs=[("bundled", pr.bundled_dir())])
    assert res.name == NAME and res.source == "bundled"


def test_python_stack_testing_and_linting_data_equals_the_generic_profile():
    new, old = _bundled(NAME), _bundled(GENERIC)
    assert new["stack"]["runtime"]["python"] == old["stack"]["runtime"]["python"] == "3.11+"
    assert new["stack"]["frontend"] == old["stack"]["frontend"] == {}
    assert new["stack"]["backend"] == old["stack"]["backend"] == {}
    for key in ("testing", "linting", "dev_server", "services", "deploy", "required_env_vars", "version"):
        assert new[key] == old[key], key
    # the plugin folder layout: every generic entry survives, only the wording of plugins/ is sharper
    assert {k for k in old["folder_structure"]} == {k for k in new["folder_structure"]}
    assert all(k in new["folder_structure"] for k in ("plugins/", "shared/", "docs/"))


def test_descriptions_say_which_profile_is_which():
    assert "Claude Code plugin" in _bundled(NAME)["description"]
    generic = _bundled(GENERIC)["description"]
    assert generic.startswith("Generic Python-project profile") and "claude-plugin" in generic


def test_rules_are_objects_with_a_why_and_load_without_errors():
    rs = par.load_rules(_bundled(NAME)["architecture_rules"])
    assert rs.errors == [] and rs.warnings == [] and rs.declared
    assert not any(r.legacy for r in rs.rules) and all(r.why for r in rs.rules)
    by_id = {r.id: r for r in rs.rules}
    # the skill-authoring checker is a report today, so it is NOT claimed as enforcement
    assert by_id["skill-authoring-limits"].enforcement == "prompt-only (mechanisable)"
    assert "report" in by_id["skill-authoring-limits"].note


def test_every_mechanism_path_exists_under_shared_or_plugins():
    rs = par.load_rules(_bundled(NAME)["architecture_rules"])
    paths = [p for r in rs.rules for p in (r.mechanism or [])]
    assert paths, "the profile names at least one invoked mechanism"
    for path in paths:
        assert path.split("/")[0] in ("shared", "plugins"), path
        assert (ROOT / path).is_file(), path
    assert par.check_paths(rs.rules, ROOT) == []


def _hook_commands(node) -> list[str]:
    if isinstance(node, dict):
        return [v for k, v in node.items() if k == "command" and isinstance(v, str)] + [c for v in node.values() for c in _hook_commands(v)]
    if isinstance(node, list):
        return [c for v in node for c in _hook_commands(v)]
    return []


def test_a_named_hook_mechanism_is_actually_registered():
    """A mechanism counts as enforcement only when something invokes it: a hooks.json command runs the script."""
    rs = par.load_rules(_bundled(NAME)["architecture_rules"])
    hooks = [r for r in rs.rules if r.enforcement == "hook"]
    assert hooks
    for rule in hooks:
        for path in rule.mechanism:
            plugin, rel = Path(path).parts[1], "/".join(Path(path).parts[2:])
            data = json.loads((ROOT / "plugins" / plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
            assert any(c.rstrip('"').endswith("${CLAUDE_PLUGIN_ROOT}/" + rel) for c in _hook_commands(data)), path


def test_ci_and_codeql_defaults_follow_the_generic_python_profile():
    assert TEMPLATE_BY_PROFILE[NAME] == TEMPLATE_BY_PROFILE[GENERIC]
    assert CODEQL_LANGUAGES_BY_PROFILE[NAME] == CODEQL_LANGUAGES_BY_PROFILE[GENERIC] == ["python"]


def test_the_hook_rule_note_states_its_real_coverage_and_the_copy_caveat():
    rs = par.load_rules(_bundled(NAME)["architecture_rules"])
    note = {r.id: r for r in rs.rules}["no-bare-python-stdin"].note
    assert "Bash tool" in note and "PowerShell" in note and "copy of this profile" in note
