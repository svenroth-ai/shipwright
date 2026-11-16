"""supabase-nextjs architecture rules vs the shipped template examples (drift test).

A committed fixture tree (``fixtures/supabase_nextjs_scaffold/``) holds every code example of
the Supabase/Next.js templates as a file. Three things are pinned:

1. the fixture equals the template example (an edited example must be re-committed),
2. every TypeScript example in the templates is mapped (a new example cannot escape the check),
3. the fixture tree passes every mechanical (lint) rule of the profile.

Step 3 (the fixture tree and seeded violations through REAL ESLint, plus the ESLint template's own drift
tests) lives in ``test_supabase_nextjs_eslint_template.py``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_architecture_rules as par  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC18", "FR-01.01/AC19", "FR-01.01/AC20")

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "shared" / "templates"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "supabase_nextjs_scaffold"
PROFILE = ROOT / "shared" / "profiles" / "supabase-nextjs.json"

# (template, ordinal of the fenced block in that file) -> fixture path
BLOCKS = {
    ("agent-docs/conventions.md.template", 1): "src/components/project-list.tsx",
    ("agent-docs/conventions.md.template", 2): "src/app/api/projects/route.ts",
    ("agent-docs/conventions.md.template", 3): "src/lib/supabase/projects.ts",
    ("agent-docs/conventions.md.template", 4): "src/lib/stores/ui-store.ts",
    ("rules/api.md.template", 0): "src/app/api/profile/route.ts",
    ("rules/api.md.template", 1): "src/lib/supabase/profiles.ts",
    ("rules/api.md.template", 2): "src/components/sign-out-example.tsx",
    ("rules/components.md.template", 0): "src/components/user-profile.tsx",
    ("rules/components.md.template", 1): "src/components/theme-toggle.tsx",
    ("rules/components.md.template", 2): "src/components/item-list.tsx",
    ("rules/components.md.template", 3): "src/components/search-bar.tsx",
    ("rules/config.md.template", 0): "src/lib/config.ts",
    ("rules/tests.md.template", 0): "src/lib/users.test.ts",
    ("rules/tests.md.template", 1): "tests/integration/courses.integration.test.ts",
    ("rules/integration-tests.md.template", 0): "tests/integration/entity.integration.test.ts",
}
WHOLE_FILES = {"integration-helpers-supabase.ts.template": "tests/integration/helpers/supabase-clients.ts"}
def _scanned() -> list:
    """The templates of the profile's own `rules` list plus the conventions template."""
    names = json.loads(PROFILE.read_text(encoding="utf-8"))["rules"]
    return sorted({"agent-docs/conventions.md.template"} | {f"rules/{n}.md.template" for n in names})


SCANNED = _scanned()
CODE_LANGS = {"ts", "tsx", "typescript", "js", "jsx", "javascript"}
_FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.S | re.M)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _blocks(template: str) -> list:
    return [((m.group(1).split() or [""])[0], m.group(2)) for m in _FENCE.finditer(_read(TEMPLATES / template))]


def _rules() -> par.RuleSet:
    return par.load_rules(json.loads(PROFILE.read_text(encoding="utf-8"))["architecture_rules"])


# ---- tests ------------------------------------------------------------------------------

def _mechanical() -> list:
    return [r for r in _rules().rules if r.lint]


def test_profile_declares_six_rules_each_with_a_why():
    rs = _rules()
    assert rs.errors == [] and rs.warnings == []
    assert [r.id for r in rs.rules] == [
        "no-cross-feature-imports", "supabase-client-through-helpers", "no-fetch-in-components",
        "server-components-by-default", "no-business-logic-in-api-routes", "db-changes-via-migrations"]
    assert all(r.why and not r.legacy for r in rs.rules)


def test_only_the_two_import_and_fetch_rules_are_mechanical():
    assert [r.id for r in _mechanical()] == ["supabase-client-through-helpers", "no-fetch-in-components"]
    assert all(r.enforcement == "validator" and r.lint["tool"] == "eslint" for r in _mechanical())
    by_id = {r.id: r for r in _rules().rules}
    assert by_id["no-cross-feature-imports"].enforcement == "prompt-only (mechanisable)"
    assert by_id["server-components-by-default"].enforcement == "prompt-only (judgement)"
    assert by_id["no-business-logic-in-api-routes"].enforcement == "prompt-only (judgement)"


@pytest.mark.parametrize("template", SCANNED)
def test_every_code_example_is_in_the_fixture_tree(template):
    for ordinal, (lang, _body) in enumerate(_blocks(template)):
        if lang in CODE_LANGS:
            assert (template, ordinal) in BLOCKS, f"{template} block {ordinal} is not mapped to a fixture file"


@pytest.mark.parametrize(("key", "rel"), sorted(BLOCKS.items()))
def test_fixture_equals_the_template_example(key, rel):
    template, ordinal = key
    assert _read(FIXTURE / rel) == _blocks(template)[ordinal][1]


@pytest.mark.parametrize(("template", "rel"), sorted(WHOLE_FILES.items()))
def test_fixture_equals_the_template_file(template, rel):
    assert _read(FIXTURE / rel) == _read(TEMPLATES / template)


def test_fixture_tree_has_exactly_the_mapped_files():
    files = [p for p in FIXTURE.rglob("*") if p.is_file()]
    assert len(files) == len(BLOCKS) + len(WHOLE_FILES)


def test_duplicated_prose_is_gone_from_the_templates():
    conventions = _read(TEMPLATES / "agent-docs/conventions.md.template")
    assert "Server Components by default" not in conventions
    assert "- All Supabase calls through" not in conventions and "No `fetch()` directly" not in conventions
    assert "Server Components by default" not in _read(TEMPLATES / "rules/components.md.template")
    assert "{ARCHITECTURE_RULES}" in conventions  # the rules are rendered once, from the profile


def test_every_mapped_template_is_scanned():
    assert {t for t, _ in BLOCKS} <= set(SCANNED)


def test_render_lists_all_six_rules_with_their_class_and_the_validator_caveat(tmp_path):
    sys.path.append(str(ROOT / "shared" / "scripts" / "tools"))
    import render_architecture_rules as rar
    template = _read(TEMPLATES / "agent-docs/conventions.md.template")
    assert "## Architecture Rules" in template and "{ARCHITECTURE_RULES}" in template
    conv = tmp_path / ".shipwright" / "agent_docs" / "conventions.md"
    conv.parent.mkdir(parents=True)
    conv.write_text(template.replace("{PROJECT_NAME}", "demo").replace("{PROFILE_NAME}", "supabase-nextjs")
                    .replace("{FOLDER_STRUCTURE}", "src/"), encoding="utf-8")
    assert rar._main(["--project-root", str(tmp_path), "--profile", "supabase-nextjs"]) == 0
    first = conv.read_text(encoding="utf-8")
    assert rar._main(["--project-root", str(tmp_path), "--profile", "supabase-nextjs"]) == 0
    assert conv.read_text(encoding="utf-8") == first  # idempotent
    bullets = {m.group(1): m.group(0) for m in re.finditer(r"^- \*\*([a-z0-9-]+)\*\*.*$", first, re.M)}
    assert list(bullets) == [r.id for r in _rules().rules]
    for rule in _rules().rules:
        if rule.lint:
            assert "linter fragment for `eslint`" in bullets[rule.id] and "checked by the linter" not in bullets[rule.id]
            assert "only for projects whose eslint config carries this fragment" in bullets[rule.id]  # the caveat survives the render
        else:
            assert f"instruction only ({rule.enforcement.split('(')[1]}" in bullets[rule.id]
