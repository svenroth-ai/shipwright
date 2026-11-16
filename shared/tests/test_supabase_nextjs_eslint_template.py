"""The supabase-nextjs ESLint template (U3b): drift against the profile's fragments, and a REAL ESLint run.

Always on (no Node): the template carries each lint fragment of the profile unchanged, parser block first,
fragments last, and the project skill's scaffold step names it without a shell command.
Needs Node and npm (``eslint_run`` installs ESLint into a temp folder; skips without them, except under CI,
where a missing Node fails): the shipped template as it is, the fixture tree of the templates' examples and one
seeded violation per rule through real ESLint. The versions are floating majors, so a red run without a code change can be an upstream release.
The whole run is ONE test, so parallel workers never each install ESLint. ``SHIPWRIGHT_ESLINT_EVIDENCE=<file>`` writes a report of that run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_hygiene import is_ci

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_architecture_rules as par  # noqa: E402

pytestmark = [pytest.mark.covers("FR-01.01/AC19", "FR-01.01/AC21", "FR-01.01/AC22")]

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "shared" / "templates"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "supabase_nextjs_scaffold"
PROFILE = ROOT / "shared" / "profiles" / "supabase-nextjs.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _mechanical() -> list:
    rules = par.load_rules(json.loads(PROFILE.read_text(encoding="utf-8"))["architecture_rules"])
    return [r for r in rules.rules if r.lint]


SEEDED_VIOLATIONS = [
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
]

COMPLIANT_OR_EXEMPT = [
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
]

ESLINT_REQUIREMENTS = ["eslint@10", "typescript-eslint@8", "typescript@5"]  # no ^: cmd.exe eats it on Windows
TEMPLATE = TEMPLATES / "eslint" / "eslint.config.mjs.template"
STEP7 = ROOT / "plugins" / "shipwright-project" / "skills" / "project" / "references" / "step-7-scaffolding.md"


def _case_path(rel: str, i: int) -> str:
    """Unique file per case: a numbered folder under the original one (the scopes are path globs,
    so the file name itself stays untouched)."""
    head, _, name = rel.rpartition("/")
    return f"{head}/case{i}/{name}"


def _eslint_run(tmp_path):
    """One REAL ESLint run over the template, the fixture tree and every seeded case.

    Skips without Node/npm or when the install cannot reach npm. Under CI either fails instead: a skipped
    run would leave the fragments exercised by nothing."""
    node, npm = shutil.which("node"), shutil.which("npm")
    if not (node and npm):
        msg = "node/npm not available for the real ESLint run"
        if is_ci():
            pytest.fail(msg, pytrace=False)
        pytest.skip(msg)
    work = tmp_path
    (work / "package.json").write_text('{"name": "scaffold", "private": true, "type": "module"}', encoding="utf-8")
    shutil.copytree(FIXTURE, work, dirs_exist_ok=True)
    shutil.copy(TEMPLATE, work / "eslint.config.mjs")
    install = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--save-dev", *ESLINT_REQUIREMENTS],
                             cwd=work, capture_output=True, text=True, timeout=600)
    if install.returncode != 0:
        msg = f"npm install of ESLint failed: {install.stderr[-500:]}"
        if is_ci():
            pytest.fail(msg, pytrace=False)
        pytest.skip(msg)  # offline or registry down on a developer machine
    cases = {}
    for i, (rel, source, rule_id) in enumerate(SEEDED_VIOLATIONS):
        cases[_case_path(rel, i)] = ("flagged", rule_id)
        (work / _case_path(rel, i)).parent.mkdir(parents=True, exist_ok=True)
        (work / _case_path(rel, i)).write_text(source, encoding="utf-8")
    for i, (rel, source) in enumerate(COMPLIANT_OR_EXEMPT, start=100):
        cases[_case_path(rel, i)] = ("clean", None)
        (work / _case_path(rel, i)).parent.mkdir(parents=True, exist_ok=True)
        (work / _case_path(rel, i)).write_text(source, encoding="utf-8")
    cli = str(work / "node_modules" / "eslint" / "bin" / "eslint.js")
    run = subprocess.run([node, cli, "--format", "json", "."], cwd=work, capture_output=True, text=True, timeout=600)
    assert run.returncode in (0, 1), run.stderr  # 2 = the config or the run itself failed
    report = {Path(r["filePath"]).relative_to(work).as_posix(): r["messages"] for r in json.loads(run.stdout)}
    evidence = os.environ.get("SHIPWRIGHT_ESLINT_EVIDENCE")
    if evidence:
        version = subprocess.run([node, cli, "--version"], capture_output=True, text=True).stdout.strip()
        node_version = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip()
        lines = [f"eslint {version}, node {node_version}",
                 f"installed: {' '.join(ESLINT_REQUIREMENTS)}; config: shared/templates/eslint/eslint.config.mjs.template, unchanged",
                 f"exit status {run.returncode} (1 = findings, as seeded)", ""]
        for rel in sorted(report):
            kind = cases.get(rel, ("fixture", None))[0]
            found = ", ".join(sorted({str(m.get("ruleId")) for m in report[rel]})) or "no finding"
            lines.append(f"{kind:8} {rel}: {found}")
        Path(evidence).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report, cases


def test_real_eslint_run_over_template_fixture_and_seeded_cases(tmp_path):
    """One test, one npm install: the four assertions share a single run (xdist would otherwise build the
    run once per worker)."""
    report, cases = _eslint_run(tmp_path)
    broken = [m for msgs in report.values() for m in msgs if m.get("fatal") or m.get("ruleId") is None]
    assert broken == [], "the template did not load or a file did not parse"
    fixture = {p.relative_to(FIXTURE).as_posix() for p in FIXTURE.rglob("*") if p.is_file()}
    assert fixture <= set(report)  # every fixture file was linted (the tree is TS/JS only), so clean is not skipped
    assert {rel: m for rel, m in report.items() if rel in fixture and m} == {}
    expected = {"supabase-client-through-helpers": {"no-restricted-imports"},
                "no-fetch-in-components": {"no-restricted-globals", "no-restricted-properties"}}
    for rel, (kind, rule_id) in cases.items():
        assert rel in report, f"{rel} was not linted (ESLint ignored the file: no config block covers it)"
        ids = {m["ruleId"] for m in report[rel]}
        if kind == "flagged":
            assert ids & expected[rule_id], f"{rel} was not flagged by {rule_id}: {ids}"
        else:
            assert not ids, f"{rel} is compliant or exempt but was flagged: {ids}"


# ---- the template itself (always runs, no Node) ------------------------------------------

def _marked_blocks(text: str) -> dict:
    pattern = r"^  // BEGIN architecture-rule: (?P<id>[a-z0-9-]+)\n(?P<body>.*?),\n  // END architecture-rule: (?P=id)$"
    return {m.group("id"): json.loads(m.group("body")) for m in re.finditer(pattern, text, re.S | re.M)}


def test_each_lint_fragment_of_the_profile_is_in_the_template_unchanged():
    blocks = _marked_blocks(_read(TEMPLATE))
    mechanical = _mechanical()
    assert mechanical and set(blocks) == {r.id for r in mechanical}
    for rule in mechanical:
        assert rule.lint["tool"] == "eslint" and rule.lint["target"] == "eslint.config.mjs"
        assert blocks[rule.id] == rule.lint["block"], f"{rule.id}: template block differs from the profile fragment"


def test_no_two_fragments_set_the_same_rule():
    keys = [k for r in _mechanical() for k in r.lint["block"]["rules"]]
    assert len(keys) == len(set(keys)), "flat config: a later block setting the same rule replaces the earlier one"


def test_template_puts_parser_first_and_fragments_last():
    text = _read(TEMPLATE)
    assert 'import tseslint from "typescript-eslint"' in text
    parser = re.search(r'files: \["(?P<glob>[^"]+)"\],\s*languageOptions: \{ parser: tseslint\.parser \}', text)
    assert parser, "no block gives the covered files the typescript-eslint parser (allowTypeImports needs it)"
    assert parser.start() < text.index("// BEGIN architecture-rule:")
    last_end = text.rindex("// END architecture-rule:")
    assert text[last_end:].split("\n", 1)[1].strip() == "];"  # nothing after the last fragment can override it
    covered = set(re.search(r"\{(.*)\}", parser.group("glob")).group(1).split(","))
    for rule in _mechanical():
        for pattern in rule.lint["block"]["files"]:
            assert set(re.search(r"\{(.*)\}", pattern).group(1).split(",")) <= covered, (rule.id, pattern)


def test_scaffold_step_writes_the_template_without_a_shell_command():
    text = _read(STEP7)
    section = text[text.index("## ESLint config (supabase-nextjs profile only)"):text.index("## GitHub Repo Hygiene")]
    assert "shared/templates/eslint/eslint.config.mjs.template" in section
    assert "typescript-eslint" in section and "LAST" in section
    assert "```" not in section  # no command block
    assert not re.search(r'"[^"\n]*\{[a-z_]+\}[^"\n]*"', section), "a placeholder sits inside double quotes"
    assert "eslint.config" in text[text.index("**Checkpoint:**"):]
