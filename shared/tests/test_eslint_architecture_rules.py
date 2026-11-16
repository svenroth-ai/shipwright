"""AC36: the build verifier reports lost architecture-rule ESLint blocks (fixtures: verbatim create-next-app configs)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # APPEND: shared/tests has its own tools/ dir
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import eslint_architecture_rules as ear  # noqa: E402
from _eslint_config_splice import array_bounds, live_in_array  # noqa: E402
from _eslint_rules_fixtures import IDS, NEXT15, NEXT16, ROOT, TEMPLATE, _project, _rules, _statuses  # noqa: E402
from tools.verifiers import build_checks  # noqa: E402
from tools.verifiers.eslint_rules_check import check_eslint_architecture_rules  # noqa: E402


@pytest.mark.covers("FR-01.01/AC36")
@pytest.mark.parametrize("config", [NEXT16, NEXT15], ids=["next16", "next15"])
def test_replaced_config_without_the_blocks_is_an_error_naming_every_rule_and_the_repair(tmp_path, config):
    _project(tmp_path, config)
    res = check_eslint_architecture_rules(tmp_path)
    assert res.is_failure and res.severity == "error"
    assert all(rule_id in res.detail for rule_id in IDS)
    assert "check_eslint_architecture_rules.py" in res.detail and "--apply" in res.detail


@pytest.mark.covers("FR-01.01/AC36")
def test_verifier_passes_once_the_rules_are_back(tmp_path):
    _project(tmp_path, NEXT16)
    assert check_eslint_architecture_rules(tmp_path).is_failure
    assert ear.apply(tmp_path, _rules(tmp_path)).status == "applied"
    assert check_eslint_architecture_rules(tmp_path).ok is True


@pytest.mark.covers("FR-01.01/AC36")
def test_config_that_already_carries_the_blocks_passes(tmp_path):
    _project(tmp_path, TEMPLATE.read_text(encoding="utf-8"))
    assert check_eslint_architecture_rules(tmp_path).ok is True


@pytest.mark.covers("FR-01.01/AC36")
def test_no_config_at_all_is_an_error_once_the_app_exists_and_a_warning_before(tmp_path):
    _project(tmp_path)
    assert check_eslint_architecture_rules(tmp_path).severity == "error"
    (tmp_path / "package.json").unlink()
    res = check_eslint_architecture_rules(tmp_path)
    assert res.is_failure and res.severity == "warning"


@pytest.mark.covers("FR-01.01/AC36")
def test_legacy_eslintrc_only_is_a_warning_not_a_permanent_error(tmp_path):
    _project(tmp_path)
    (tmp_path / ".eslintrc.json").write_text("{}", encoding="utf-8")
    res = check_eslint_architecture_rules(tmp_path)
    assert res.is_failure and res.severity == "warning"


@pytest.mark.covers("FR-01.01/AC36")
def test_a_hand_folded_block_is_only_a_warning(tmp_path):
    """Step 7 (3c) folds an existing option into the appended block, so it differs from the profile on purpose."""
    text = TEMPLATE.read_text(encoding="utf-8").replace('"error",\n        {\n          "name": "fetch"',
                                                        '"warn",\n        {\n          "name": "fetch"')
    assert text != TEMPLATE.read_text(encoding="utf-8")
    _project(tmp_path, text)
    assert _statuses(tmp_path)["no-fetch-in-components"] == "stale"
    res = check_eslint_architecture_rules(tmp_path)
    assert res.is_failure and res.severity == "warning"


@pytest.mark.covers("FR-01.01/AC36")
def test_damaged_markers_are_an_error(tmp_path):
    _project(tmp_path, TEMPLATE.read_text(encoding="utf-8").replace("  // END architecture-rule: no-fetch-in-components\n", ""))
    assert _statuses(tmp_path)["no-fetch-in-components"] == "unpaired"
    assert check_eslint_architecture_rules(tmp_path).severity == "error"


@pytest.mark.covers("FR-01.01/AC36")
@pytest.mark.parametrize("how", ["after-array", "earlier-const"])
def test_a_block_that_is_not_live_in_the_exported_array_is_an_error(tmp_path, how):
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("  // BEGIN architecture-rule: supabase-client-through-helpers")
    stop = text.index("  // END architecture-rule: supabase-client-through-helpers\n") + len("  // END architecture-rule: supabase-client-through-helpers\n")
    block, rest = text[start:stop], text[:start] + text[stop:]
    if how == "after-array":
        moved = rest + block
    else:
        moved = rest.replace("export default [", "const old = [\n" + block + "];\nexport default [")
    _project(tmp_path, moved)
    assert _statuses(tmp_path)["supabase-client-through-helpers"] == "outside"
    assert check_eslint_architecture_rules(tmp_path).severity == "error"


@pytest.mark.covers("FR-01.01/AC36")
def test_a_commented_out_block_is_not_live():
    text = "export default [\n/*\n// BEGIN architecture-rule: a\n{},\n// END architecture-rule: a\n*/\n];\n"
    bounds, _ = array_bounds(text)
    assert not live_in_array(text, bounds, text.index("// BEGIN"), text.index("*/"))


@pytest.mark.covers("FR-01.01/AC36")
def test_code_after_the_last_block_is_reported_as_shadowing(tmp_path):
    text = TEMPLATE.read_text(encoding="utf-8").replace("\n];", '\n  { rules: { "no-restricted-imports": "off" } },\n];')
    _project(tmp_path, text)
    assert "shadowed" in _statuses(tmp_path).values()


@pytest.mark.covers("FR-01.01/AC36")
def test_profile_without_eslint_rules_is_skipped_and_the_check_runs_in_the_build_suite(tmp_path):
    _project(tmp_path, NEXT16, profile="claude-plugin")
    assert check_eslint_architecture_rules(tmp_path).is_skipped
    _project(tmp_path, NEXT16)
    names = [r.name for r in build_checks.run_build_checks(tmp_path)]
    assert "eslint_architecture_rules_present" in names


@pytest.mark.covers("FR-01.01/AC36")
def test_docs_no_longer_call_this_an_open_follow_up_and_name_the_check():
    guide = (ROOT / "docs" / "building-skills-plugins-agents.md").read_text(encoding="utf-8")
    assert "open follow-up" not in guide and "check_eslint_architecture_rules.py" in guide
    hooks = (ROOT / "docs" / "hooks-and-pipeline.md").read_text(encoding="utf-8")
    assert "eslint_architecture_rules_present" in hooks


@pytest.mark.covers("FR-01.01/AC36")
def test_missing_dev_dependencies_and_an_unreadable_config_are_warnings_never_a_clean_pass_or_a_crash(tmp_path):
    _project(tmp_path, TEMPLATE.read_text(encoding="utf-8"))
    (tmp_path / "package.json").write_text('{"devDependencies": {}}', encoding="utf-8")
    res = check_eslint_architecture_rules(tmp_path)
    assert res.is_failure and res.severity == "warning" and "devDependencies" in res.detail
    (tmp_path / "eslint.config.mjs").write_bytes(b"// caf\xe9\nexport default [];\n")  # not UTF-8
    res = check_eslint_architecture_rules(tmp_path)
    assert res.is_failure and res.severity == "warning" and "cannot read" in res.detail
