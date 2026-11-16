"""AC37: the repair tool appends the blocks safely, is idempotent and refuses what it cannot edit (default tier, no Node)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # APPEND: shared/tests has its own tools/ dir
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import eslint_architecture_rules as ear  # noqa: E402
from _ts_lexer import lex  # noqa: E402
from _eslint_config_splice import array_bounds  # noqa: E402
from _eslint_rules_fixtures import IDS, NEXT15, NEXT16, TEMPLATE, TOOL, _project, _rules, _statuses  # noqa: E402
from tools.verifiers.eslint_rules_check import check_eslint_architecture_rules  # noqa: E402


@pytest.mark.covers("FR-01.01/AC37")
@pytest.mark.parametrize("config", [NEXT16, NEXT15], ids=["next16", "next15"])
def test_apply_appends_the_blocks_last_keeps_the_rest_and_is_idempotent(tmp_path, config):
    _project(tmp_path, config)
    done = ear.apply(tmp_path, _rules(tmp_path))
    assert done.status == "applied" and not done.report.bad
    new = (tmp_path / "eslint.config.mjs").read_text(encoding="utf-8")
    for line in config.splitlines():
        if line.strip() not in ("]);", "];"):
            assert line in new, f"original line lost: {line!r}"
    assert new.index("// BEGIN architecture-rule") > max(new.rfind("globalIgnores(["), new.rfind("...compat.extends"))
    assert new.rindex("// END architecture-rule") < new.rindex("]")
    assert new.rstrip().endswith("export default eslintConfig;")
    before = (tmp_path / "eslint.config.mjs").read_bytes()
    again = ear.apply(tmp_path, _rules(tmp_path))
    assert again.status == "unchanged" and (tmp_path / "eslint.config.mjs").read_bytes() == before
    assert _statuses(tmp_path) == dict.fromkeys(IDS, "ok")


@pytest.mark.covers("FR-01.01/AC37")
def test_applied_blocks_equal_the_template_fragments_and_the_profile(tmp_path):
    _project(tmp_path, NEXT16)
    ear.apply(tmp_path, _rules(tmp_path))
    new = (tmp_path / "eslint.config.mjs").read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    for rule in _rules(tmp_path):
        frag = ear.render_fragment(rule)
        assert frag in new and frag in template, rule.id


@pytest.mark.covers("FR-01.01/AC37")
@pytest.mark.parametrize("name,config", [
    ("eslint.config.cjs", 'const base = require("x");\nmodule.exports = [\n  ...base,\n  { ignores: ["dist/**"] }\n];\n'),
    ("eslint.config.mjs", 'export default [{ ignores: ["a"] }];\n'),
    ("eslint.config.mjs", 'import { defineConfig } from "eslint/config";\nexport default defineConfig([\n  { ignores: ["a"] }, // keep\n]);\n'),
    ("eslint.config.ts", 'const c: any[] = [{ ignores: ["a"] }];\nexport default c;\n'),
    ("eslint.config.mjs", 'const re = /[\\]\\[]\\//;\nconst t = `${"]"} [`;\nexport default [\n  { ignores: [re.source, t] },\n];\n'),
], ids=["cjs", "inline", "defineConfig-comment", "ts-typed-const", "regex-and-template-brackets"])
def test_apply_handles_the_supported_shapes(tmp_path, name, config):
    _project(tmp_path, config, name=name)
    done = ear.apply(tmp_path, _rules(tmp_path))
    assert done.status == "applied", done.message
    new = (tmp_path / name).read_text(encoding="utf-8")
    assert _statuses(tmp_path) == dict.fromkeys(IDS, "ok") and "ignores" in new
    # the closing bracket still closes the array after the blocks
    assert array_bounds(new)[0] is not None


@pytest.mark.covers("FR-01.01/AC37")
def test_apply_keeps_crlf_line_endings(tmp_path):
    _project(tmp_path, NEXT16.replace("\n", "\r\n"))
    assert ear.apply(tmp_path, _rules(tmp_path)).status == "applied"
    raw = (tmp_path / "eslint.config.mjs").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")


@pytest.mark.covers("FR-01.01/AC37")
@pytest.mark.parametrize("config", [
    "export default someFactory();\n",
    "export default [\n  { ignores: [\"a\"] },\n].concat(more);\n",
    "const a = [];\nconst b = [];\nexport default a;\nexport default b;\n",
    "export default [ { ignores: [`oops ] };\n",
    "export default await build();\n",
    "export default defineConfig([]).concat(more);\n",
], ids=["call", "chained", "two-exports", "unterminated", "await", "wrapped-chained"])
def test_unsafe_shape_is_refused_and_the_file_is_left_alone(tmp_path, config):
    _project(tmp_path, config)
    before = (tmp_path / "eslint.config.mjs").read_bytes()
    done = ear.apply(tmp_path, _rules(tmp_path))
    assert done.status == "cannot" and done.message
    assert (tmp_path / "eslint.config.mjs").read_bytes() == before
    assert check_eslint_architecture_rules(tmp_path).is_failure  # still loud


@pytest.mark.covers("FR-01.01/AC37")
def test_existing_restricted_rule_options_are_not_overridden_silently(tmp_path):
    config = NEXT16.replace("  ...nextTs,\n", '  ...nextTs,\n  { rules: { "no-restricted-imports": ["error", "lodash"] } },\n')
    _project(tmp_path, config)
    before = (tmp_path / "eslint.config.mjs").read_bytes()
    done = ear.apply(tmp_path, _rules(tmp_path))
    assert done.status == "cannot" and "3c" in done.message
    assert (tmp_path / "eslint.config.mjs").read_bytes() == before


@pytest.mark.covers("FR-01.01/AC37")
def test_stale_block_is_replaced_only_on_request_and_unpaired_never(tmp_path):
    text = TEMPLATE.read_text(encoding="utf-8").replace('"allowTypeImports": true', '"allowTypeImports": false')
    _project(tmp_path, text)
    before = (tmp_path / "eslint.config.mjs").read_bytes()
    assert ear.apply(tmp_path, _rules(tmp_path)).status == "unchanged"  # a hand fold is left alone, still reported
    assert (tmp_path / "eslint.config.mjs").read_bytes() == before
    assert ear.apply(tmp_path, _rules(tmp_path), replace_stale=True).status == "applied"
    assert (tmp_path / "eslint.config.mjs").read_text(encoding="utf-8") == TEMPLATE.read_text(encoding="utf-8")
    broken = TEMPLATE.read_text(encoding="utf-8").replace("  // END architecture-rule: no-fetch-in-components\n", "")
    _project(tmp_path, broken)
    assert ear.apply(tmp_path, _rules(tmp_path), replace_stale=True).status == "cannot"
    assert (tmp_path / "eslint.config.mjs").read_text(encoding="utf-8") == broken


@pytest.mark.covers("FR-01.01/AC37")
def test_no_config_gets_the_template_and_a_legacy_only_project_is_reported(tmp_path):
    _project(tmp_path)
    assert ear.apply(tmp_path, _rules(tmp_path)).status == "applied"
    assert (tmp_path / "eslint.config.mjs").read_text(encoding="utf-8") == TEMPLATE.read_text(encoding="utf-8")
    legacy = tmp_path / "other"
    legacy.mkdir()
    _project(legacy)
    (legacy / ".eslintrc.json").write_text("{}", encoding="utf-8")
    done = ear.apply(legacy, _rules(legacy))
    assert done.status == "cannot" and not (legacy / "eslint.config.mjs").exists()


@pytest.mark.covers("FR-01.01/AC37")
def test_cli_reports_repairs_and_exits_with_the_documented_codes(tmp_path):
    _project(tmp_path, NEXT16)

    def run(*args):
        return subprocess.run([sys.executable, str(TOOL), "--project-root", str(tmp_path), *args],
                              capture_output=True, text=True, timeout=120)

    first = run("--json")
    assert first.returncode == 1 and {f["status"] for f in json.loads(first.stdout)["findings"]} == {"missing"}
    assert run("--apply").returncode == 0
    assert run().returncode == 0
    (tmp_path / "eslint.config.mjs").write_text("export default build();\n", encoding="utf-8")
    refused = run("--apply")
    assert refused.returncode == 3 and "REFUSED" in refused.stdout
    assert run("--profile", "no-such-profile-xyz").returncode == 2


# ---- the contract around it ---------------------------------------------------------------

@pytest.mark.covers("FR-01.01/AC37")
def test_package_json_is_never_edited_and_missing_dev_dependencies_are_noted(tmp_path):
    _project(tmp_path, NEXT16)
    (tmp_path / "package.json").write_text('{"devDependencies": {}}', encoding="utf-8")
    ear.apply(tmp_path, _rules(tmp_path))
    assert (tmp_path / "package.json").read_text(encoding="utf-8") == '{"devDependencies": {}}'
    assert any("devDependencies" in n for n in ear.check(tmp_path, _rules(tmp_path)).notes)


@pytest.mark.covers("FR-01.01/AC37")
@pytest.mark.parametrize("text", [NEXT16, NEXT15, "const t = `${'x'} // not a comment [`;\n/* a ] */ export default [ /[\\]]/ ];\n"])
def test_the_lexer_keeps_offsets_because_the_splice_mixes_blanked_and_real_text(text):
    assert len(lex(text).code_only) == len(text)


@pytest.mark.covers("FR-01.01/AC37")
def test_replace_stale_keeps_crlf_and_a_workspace_root_gets_no_template(tmp_path):
    text = TEMPLATE.read_text(encoding="utf-8").replace('"allowTypeImports": true', '"allowTypeImports": false').replace("\n", "\r\n")
    _project(tmp_path, text)
    assert ear.apply(tmp_path, _rules(tmp_path), replace_stale=True).status == "applied"
    raw = (tmp_path / "eslint.config.mjs").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n") and b"allowTypeImports\": true" in raw
    ws = tmp_path / "ws"
    ws.mkdir()
    _project(ws)
    (ws / "package.json").write_text('{"workspaces": ["apps/*"]}', encoding="utf-8")
    assert ear.apply(ws, _rules(ws)).status == "cannot" and not (ws / "eslint.config.mjs").exists()
