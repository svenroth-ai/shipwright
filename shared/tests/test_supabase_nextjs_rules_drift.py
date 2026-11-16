"""supabase-nextjs architecture rules vs the shipped template examples (drift test).

A committed fixture tree (``fixtures/supabase_nextjs_scaffold/``) holds every code example of
the Supabase/Next.js templates as a file. Three things are pinned:

1. the fixture equals the template example (an edited example must be re-committed),
2. every TypeScript example in the templates is mapped (a new example cannot escape the check),
3. the fixture tree passes every mechanical (lint) rule of the profile.

Step 3 applies the profile's own ESLint fragments through a small emulation limited to the
rules the fragments use (``no-restricted-imports``, ``no-restricted-globals``,
``no-restricted-properties``); an unknown rule fails the test so the emulation cannot silently
skip a rule. It is NOT evidence that ESLint itself accepts the fragments - that run belongs
to the ESLint template unit, which replaces this emulation with a real ESLint run over the
same fixture tree (the architecture review called a permanent emulator disproportionate; it is
kept only until that unit lands so the mechanical rules are pinned meanwhile).
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


# ---- a deliberately small ESLint emulation ---------------------------------------------

def _glob(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "{":
            j = pattern.index("}", i)
            out, i = out + "(?:" + "|".join(re.escape(a) for a in pattern[i + 1:j].split(",")) + ")", j + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + "$")


def _applies(block: dict, rel: str) -> bool:
    return (any(_glob(p).match(rel) for p in block.get("files", []))
            and not any(_glob(p).match(rel) for p in block.get("ignores", [])))


_IMPORT = re.compile(r"""^\s*(?:import|export)\s+(?P<clause>[^'"]*?)\s*(?:from\s*)?['"](?P<src>[^'"]+)['"]""", re.M)


def _imports(source: str) -> list:
    """[(module, runtime)]: ``runtime`` is False only for a type-only import (``import type ...``,
    ``export type ... from`` or braces holding nothing but ``type X`` specifiers)."""
    found = []
    for m in _IMPORT.finditer(source):
        clause = m.group("clause").strip()
        runtime = not re.match(r"(?:import|export)\s+type\b", m.group(0).strip())
        braces = re.search(r"\{(.*?)\}", clause, re.S)
        specs = [p.strip() for p in braces.group(1).split(",") if p.strip()] if braces else []
        outside = re.sub(r"\{.*?\}", "", clause, flags=re.S).strip().strip(",")
        if specs and not outside and all(re.match(r"type\s", p) for p in specs):
            runtime = False  # braces hold only inline types
        found.append((m.group("src"), runtime))
    return found


def _scan(source: str) -> tuple:
    """(code with string contents blanked, code with strings kept); comments are removed from both.

    A ``//`` inside a string is not a comment, so a URL string cannot hide a later ``fetch``."""
    blank, keep, i, n = [], [], 0, len(source)
    while i < n:
        c = source[i]
        if source.startswith("//", i):
            j = source.find("\n", i)
            i = n if j < 0 else j
        elif source.startswith("/*", i):
            j = source.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "'\"`":
            j = i + 1
            while j < n and source[j] != c:
                j += 2 if source[j] == "\\" else 1
            body = source[i + 1:j]
            blank.append(c + " " * len(body) + c)
            keep.append(c + body + c)
            i = j + 1
        else:
            blank.append(c)
            keep.append(c)
            i += 1
    return "".join(blank), "".join(keep)


def _lint(block: dict, source: str) -> list:
    problems = []
    blank, keep = _scan(source)
    for name, conf in block["rules"].items():
        opts = conf[1:] if isinstance(conf, list) else []
        if name == "no-restricted-imports":
            for opt in opts:
                if set(opt) - {"paths"} or any(set(p) - {"name", "message", "allowTypeImports"} for p in opt.get("paths", [])):
                    raise AssertionError("the drift test emulates only no-restricted-imports paths with allowTypeImports")
                for module, runtime in _imports(source):
                    for path in opt.get("paths", []):
                        if module == path["name"] and not (path.get("allowTypeImports") and not runtime):
                            problems.append(f"import of {module}")
        elif name == "no-restricted-globals":
            for opt in opts:
                if re.search(rf"(?<![\w$.]){re.escape(opt['name'])}\b", blank):
                    problems.append(f"global {opt['name']}")
        elif name == "no-restricted-properties":
            for opt in opts:
                obj, prop = opt["object"], opt["property"]
                dot = rf"\b{obj}\s*\??\.\s*{prop}\b"
                brk = rf"\b{obj}\s*(?:\?\.)?\s*\[\s*['\"`]{prop}['\"`]\s*\]"
                if re.search(dot, blank) or re.search(brk, keep):
                    problems.append(f"{obj}.{prop}")
        else:
            raise AssertionError(f"the drift test cannot emulate ESLint rule {name!r}: add it here before using it in a fragment")
    return problems


def _mechanical() -> list:
    return [r for r in _rules().rules if r.lint]


def _violations(rel: str, source: str) -> list:
    return [(r.id, p) for r in _mechanical() if _applies(r.lint["block"], rel) for p in _lint(r.lint["block"], source)]


# ---- tests ------------------------------------------------------------------------------

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


def test_fixture_tree_passes_every_mechanical_rule():
    files = sorted(p for p in FIXTURE.rglob("*") if p.is_file())
    assert len(files) == len(BLOCKS) + len(WHOLE_FILES)
    found = {p.relative_to(FIXTURE).as_posix(): _violations(p.relative_to(FIXTURE).as_posix(), _read(p)) for p in files}
    assert {rel: v for rel, v in found.items() if v} == {}


@pytest.mark.parametrize(("rel", "source", "rule_id"), [
    ("src/components/a.tsx", "import { createClient } from '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "import { createBrowserClient } from '@supabase/ssr'\n", "supabase-client-through-helpers"),
    ("src/app/page.tsx", "import { createServerClient } from '@supabase/ssr'\n", "supabase-client-through-helpers"),
    ("src/app/page.tsx", "import * as supabase from '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "import { AuthError } from '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "import { type User, AuthError } from '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "import sb from '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "import '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "export { createClient } from '@supabase/supabase-js'\n", "supabase-client-through-helpers"),
    ("src/components/a.tsx", "const r = await fetch('/api/x')\n", "no-fetch-in-components"),
    ("src/components/a.tsx", "const r = await window.fetch('/api/x')\n", "no-fetch-in-components"),
    ("src/components/a.tsx", "const u = 'https://x.test'; const r = await fetch(u)\n", "no-fetch-in-components"),
    ("src/components/a.tsx", "const r = await window['fetch']('/api/x')\n", "no-fetch-in-components"),
    ("src/components/a.tsx", "const r = await window?.fetch('/api/x')\n", "no-fetch-in-components"),
    ("src/components/a.tsx", "const r = await globalThis?.['fetch']('/api/x')\n", "no-fetch-in-components"),
    ("src/app/page.tsx", "const r = await globalThis.fetch('/api/x')\n", "no-fetch-in-components"),
])
def test_a_seeded_violation_is_flagged(rel, source, rule_id):
    assert rule_id in {r for r, _ in _violations(rel, source)}


@pytest.mark.parametrize(("rel", "source"), [
    ("src/lib/supabase/server.ts", "import { createServerClient } from '@supabase/ssr'\n"),   # the helpers themselves
    ("src/lib/supabase/projects.ts", "import type { SupabaseClient } from '@supabase/supabase-js'\n"),
    ("src/components/user-menu.tsx", "import type { User, Session } from '@supabase/supabase-js'\n"),   # type imports stay allowed
    ("src/app/opengraph-image.tsx", "const f = await fetch(new URL('./font.ttf', import.meta.url))\n"),
    ("src/lib/users.test.ts", "import { createClient } from '@supabase/supabase-js'\n"),     # co-located test
    ("tests/unit/users.test.ts", "import { createClient } from '@supabase/supabase-js'\n"),  # outside src
    ("src/components/a.tsx", "import { createServerClient } from '@/lib/supabase/server'\n"),  # a Server Component
    ("src/lib/api/projects.ts", "const r = await fetch('/api/projects')\n"),                  # the API layer
    ("src/app/api/x/route.ts", "const r = await fetch('https://example.com')\n"),             # a route handler, not a component
    ("src/components/a.test.tsx", "const r = await fetch('/api/x')\n"),
    ("src/components/a.tsx", "// fetch() is not allowed here\n"),
    ("src/components/a.tsx", "const s = 'call fetch() later'\n"),
    ("src/components/user-menu.tsx", "import { type User, type Session } from '@supabase/supabase-js'\n"),
    ("src/components/user-menu.tsx", "export type { User } from '@supabase/supabase-js'\n"),
    ("src/components/a.tsx", "import { createClient } from '@/lib/supabase/client'\n"),        # a helper may be called createClient
    ("src/components/ui/button.tsx", "import * as React from 'react'\n"),                       # shadcn-style namespace import
])
def test_a_compliant_or_exempt_file_is_not_flagged(rel, source):
    assert _violations(rel, source) == []


def test_unknown_eslint_rule_in_a_fragment_fails_loudly():
    with pytest.raises(AssertionError):
        _lint({"rules": {"no-eval": "error"}}, "x")


def test_duplicated_prose_is_gone_from_the_templates():
    conventions = _read(TEMPLATES / "agent-docs/conventions.md.template")
    assert "Server Components by default" not in conventions
    assert "- All Supabase calls through" not in conventions and "No `fetch()` directly" not in conventions
    assert "Server Components by default" not in _read(TEMPLATES / "rules/components.md.template")
    assert "{ARCHITECTURE_RULES}" in conventions  # the rules are rendered once, from the profile


def test_every_mapped_template_is_scanned():
    assert {t for t, _ in BLOCKS} <= set(SCANNED)
