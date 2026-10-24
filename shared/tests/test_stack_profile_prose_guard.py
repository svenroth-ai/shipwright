"""Prose guard (campaign stack-profile-resolver S4): no markdown / hooks.json
file builds a bundled stack-profile path by hand.

Skill prose is runtime code: a hand-built ``shared/profiles/{profile}.json``
bypasses the resolver (project > user > bundled lookup, validation, the
shadow warning). Prose goes through ``resolve_profile.py`` or passes the
profile NAME to a loader. The ``*.py`` half of the guard belongs to S5.

Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.06")

REPO = Path(__file__).resolve().parents[2]

# A hand-built path into the bundled profile directory: ``shared/profiles``,
# ``{shared_root}/profiles`` or ``${X}/../../shared/profiles`` -- except the
# deploy profiles and the reducibility idiom map, which are not stack profiles.
_BUNDLED = re.compile(
    r"(?:<?\{?shared(?:_root)?\}?>?)[\\/]+(?:[^\s`\"']*[\\/])?profiles\b"
    r"(?![\\/]+(?:deploy[\\/-]|reducibility-idioms\.json|deploy-profile))",
    re.IGNORECASE,
)

# (path prefix or exact path, why it may name the bundled directory). Every
# entry must still match something (reverse test), so a stale entry fails.
ALLOWLIST: dict[str, str] = {
    "docs/": "hand-written docs; S5 reconciles guide.md / hooks-and-pipeline.md",
    "shared/glossary.md": "defines the Profile term",
    ".shipwright/planning/": "historical specs, briefs and ADR records",
    ".shipwright/agent_docs/conventions.md": "convention records describing the resolver itself",
    ".shipwright/agent_docs/decision_log.md": "ADR history",
    "CHANGELOG": "history",
}

# Re-rendered at every finalize from event / card / ADR text, so they copy any
# prose that quotes the bundled directory and drift with unrelated runs. Excused
# from the forward scan and deliberately NOT subject to the reverse test.
GENERATED = (
    ".shipwright/agent_docs/triage_inbox.md",
    ".shipwright/agent_docs/session_handoff.md",
    ".shipwright/agent_docs/build_dashboard.md",
    ".shipwright/agent_docs/decision_log_index.md",
)


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "*.md", "*hooks.json"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout
    return [p for p in out.splitlines() if p]


def _allowed(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in (*ALLOWLIST, *GENERATED))


def scan_text(text: str) -> list[tuple[int, str]]:
    return [(i, line.strip()) for i, line in enumerate(text.splitlines(), 1)
            if _BUNDLED.search(line)]


def _read(rel: str) -> str:
    try:
        return (REPO / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # an unreadable tracked file is a failure, never a skip
        raise AssertionError(f"guard cannot read tracked file {rel}: {exc}") from exc


def findings(files: list[str]) -> list[str]:
    found = []
    for rel in files:
        if _allowed(rel):
            continue
        text = _read(rel)
        found += [f"{rel}:{n}: {line[:100]}" for n, line in scan_text(text)]
    return found


def test_no_prose_builds_a_bundled_stack_profile_path():
    bad = findings(_tracked())
    assert not bad, (
        "prose must use resolve_profile.py / a profile NAME, not a bundled path:\n"
        + "\n".join(bad)
    )


def test_guard_is_red_on_a_planted_path_and_green_on_the_fixed_form(tmp_path):
    planted = 'Load profile from `{plugin_root}/../../shared/profiles/{profile}.json`.'
    assert scan_text(planted)
    assert scan_text('--profile-path "{shared_root}/profiles/{profile}.json"')
    hooks_json = '{"command": "uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/profiles/supabase-nextjs.json"}'
    assert scan_text(hooks_json)
    for planted_form in ("{shared}/profiles/x.json", "{shared_root}/scripts/../profiles/x.json", "SHARED_ROOT/profiles/x.json",
                         "<shared_root>/profiles/x.json", "shared/profiles/deployable-stack.json"):
        assert scan_text(planted_form), planted_form
    assert scan_text(r'{"command": "C:\\x\\shared\\profiles\\vite-hono.json"}')  # JSON-escaped Windows path
    fixed = 'uv run --no-project resolve_profile.py resolve --name {profile} --path-only'
    assert not scan_text(fixed)
    # the non-stack neighbours stay legal
    assert not scan_text("`shared/profiles/deploy/jelastic.json`")
    assert not scan_text("`shared/profiles/reducibility-idioms.json`")
    assert not scan_text("`{shared_root}/profiles/deploy/jelastic.json`")


def test_every_allowlist_entry_still_excuses_a_real_finding():
    """An entry that no longer shields at least one would-be finding is stale."""
    files = _tracked()
    stale = []
    for prefix in ALLOWLIST:
        hits = [f for f in files if f.startswith(prefix)
                and scan_text(_read(f))]
        if not hits:
            stale.append(prefix)
    assert not stale, f"allowlist entries excuse no finding: {stale}"
