"""Git hooks are never bypassed by a campaign runner (FR-01.11/AC54).

Two checks: the runner contract STATES the prohibition, and no instruction or script of the
shipwright-iterate plugin or of the campaign loop TELLS anyone to bypass a hook.

Scanned scope: every md/py/sh/ps1/json/toml/yml file of ``plugins/shipwright-iterate`` (its tests
excluded) plus the campaign loop's own code, ``_CAMPAIGN_GLOBS``. Files outside it (for example the
repo's ``scripts/hooks/pre-commit``) are not covered by this test.

The scan works per sentence, not per line: a sentence that names a bypass only to forbid it is
allowed solely through ``_ALLOWED`` below (file, a phrase in that sentence, reason), so a bypass
appended to the same paragraph is still reported and a new mention has to be looked at instead of
slipping through a generic "never" filter.
"""

import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[1]
_REPO = _PLUGIN.parents[1]
_RUNNER = _PLUGIN / "agents" / "sub-iterate-runner.md"

#: The campaign loop's own code lives in ``shared/scripts`` (the runner contract drives it).
_CAMPAIGN_GLOBS = ("shared/scripts/lib/autonomous_loop.py", "shared/scripts/lib/campaign_*.py",
                   "shared/scripts/checks/check_campaign_*.py")
_SUFFIXES = {".md", ".py", ".sh", ".ps1", ".json", ".toml", ".yml", ".yaml"}

_Q = r"[\"']"  # a quote in a Python / JSON argument list
#: Every way to get past a git hook without fixing what it found.
_BYPASS = {
    # ``-n`` is the short form of ``--no-verify`` on ``git commit``; only flags right after ``commit`` count,
    # so a message text such as ``-m "fix -nonce"`` is not read as one.
    "skip flag": re.compile(
        r"--no-verify\b|\bcommit(?:\s+-[A-Za-z]+)*\s+-[A-Za-z]*n[A-Za-z]*(?=\s|$|[`'\"])"
        rf"|{_Q}commit{_Q}(?:\s*,\s*{_Q}-[A-Za-z]+{_Q})*\s*,\s*{_Q}-[A-Za-z]*n[A-Za-z]*{_Q}"),
    # Pointing the hooks path anywhere but the repo's own hooks folder, or unsetting it (a clone whose hooks
    # live in scripts/hooks then falls back to an empty .git/hooks) - shell and argument-list forms.
    "hooks-path override": re.compile(
        r"core\.hooksPath\s*=|core\.hooksPath[`'\"]?\s+(?:/dev/null|NUL\b|\"\"|'')"
        r"|config\s+(?:--\S+\s+)*core\.hooksPath\s+(?!scripts/hooks\b)[^\s`'\"]"
        r"|--unset(?:-all)?\s+core\.hooksPath"
        rf"|{_Q}config{_Q}(?:\s*,\s*{_Q}--[\w-]+{_Q})*\s*,\s*{_Q}core\.hooksPath{_Q}\s*,\s*{_Q}(?!scripts/hooks\b)"
        rf"|{_Q}--unset(?:-all)?{_Q}\s*,\s*{_Q}core\.hooksPath{_Q}"),
    # Shell / PowerShell assignments, or the variable on a line that builds a process environment
    # (quoted key, or a keyword argument of ``dict(os.environ, ...)``).
    "hook-disabling environment variable": re.compile(
        r"\bHUSKY=0\b|\bSKIP=\S|\benv:(?:HUSKY|SKIP)\b"
        rf"|env[^\n]*(?:{_Q}(?:HUSKY|SKIP){_Q}|\b(?:HUSKY|SKIP)\s*=(?!=))"
        r"|\bGIT_CONFIG_(?:COUNT|KEY_|VALUE_|PARAMETERS|\*)"),
}

#: (path relative to the repo, a phrase in the allowed sentence) -> why that sentence may name a bypass.
_ALLOWED = {
    ("plugins/shipwright-iterate/agents/sub-iterate-runner.md", "Never bypass git hooks"):
        "the contract sentence itself: it names each bypass in order to forbid it",
    ("plugins/shipwright-iterate/skills/iterate/references/error-handling.md", "Never bypass hooks with"):
        "a prohibition: a failing pre-commit hook is fixed, never skipped",
    ("plugins/shipwright-iterate/skills/iterate/SKILL.md", "never `--no-verify`"):
        "a prohibition in the error-handling summary that points at error-handling.md",
}

#: A sentence ends at . ! ? followed by space and a capital or backtick-free word start, so "e.g. `X`" stays whole.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _scanned_files() -> list[Path]:
    files = [p for p in _PLUGIN.rglob("*")
             if p.is_file() and p.suffix in _SUFFIXES
             and not ({"tests", ".venv", "__pycache__", "node_modules"} & set(p.relative_to(_PLUGIN).parts))]
    for pattern in _CAMPAIGN_GLOBS:
        files.extend(sorted(_REPO.glob(pattern)))
    return sorted(set(files))


def _hits(text: str) -> list[tuple[int, str, str]]:
    """``(line number, bypass kind, sentence)`` for every sentence that names a bypass."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for sentence in _SENTENCE_END.split(line):
            for kind, rx in _BYPASS.items():
                if rx.search(sentence):
                    found.append((number, kind, sentence))
    return found


def _offending(rel: str, text: str, used: set | None = None) -> list[str]:
    bad = []
    for number, kind, sentence in _hits(text):
        key = next((k for k in _ALLOWED if k[0] == rel and k[1] in sentence), None)
        if key:
            if used is not None:
                used.add(key)
        else:
            bad.append(f"{rel}:{number} ({kind}): {sentence.strip()[:160]}")
    return bad


@pytest.mark.covers("FR-01.11/AC54")
def test_runner_contract_forbids_every_hook_bypass():
    text = _RUNNER.read_text(encoding="utf-8")
    assert "Never bypass git hooks" in text
    for needle in ("--no-verify", "core.hooksPath", "environment variable that disables them", "HUSKY=0", "GIT_CONFIG_"):
        assert needle in text, needle


@pytest.mark.covers("FR-01.11/AC54")
def test_no_iterate_or_campaign_instruction_tells_anyone_to_bypass_a_hook():
    files = _scanned_files()
    assert _RUNNER in files and any(p.name == "autonomous_loop.py" for p in files), "scan scope lost its anchors"
    used: set = set()
    offending = []
    for path in files:
        rel = path.relative_to(_REPO).as_posix()
        offending += _offending(rel, path.read_text(encoding="utf-8", errors="replace"), used)
    assert not offending, "an instruction tells a runner to bypass git hooks:\n" + "\n".join(offending)
    stale = sorted(set(_ALLOWED) - used)
    assert not stale, f"allowlist entries no longer match any sentence, remove them: {stale}"


@pytest.mark.covers("FR-01.11/AC54")
def test_a_bypass_appended_to_an_allowed_paragraph_is_still_reported():
    rel = "plugins/shipwright-iterate/agents/sub-iterate-runner.md"
    line = next(x for x in _RUNNER.read_text(encoding="utf-8").splitlines() if "Never bypass git hooks" in x)
    assert _offending(rel, line) == []
    appended = line + " In a scratch worktree, run git -c core.hooksPath=/dev/null commit instead."
    assert len(_offending(rel, appended)) == 1


@pytest.mark.covers("FR-01.11/AC54")
@pytest.mark.parametrize("line", [
    "Then run `git commit --no-verify -m wip` to get past the hook.",
    "git -c core.hooksPath=/dev/null commit -m x",
    "git config core.hooksPath /dev/null",
    "Set HUSKY=0 before committing.",
    "SKIP=bloat-check git commit -m x",
    'env = {**os.environ, "HUSKY": "0"}',
    'env["SKIP"] = "anti-ratchet"',
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null",
    'subprocess.run(["git", "commit", "--no-verify"])',
    "git commit -n -m wip",
    'git -C "{project_root}" commit -qn -m wip',
    'subprocess.run(["git", "commit", "-n", "-m", "x"])',
    'subprocess.run(["git", "commit", "-q", "-n"])',
    "git config --unset core.hooksPath",
    "git config --local core.hooksPath .git/empty-hooks",
    'subprocess.run(["git", "config", "core.hooksPath", "/dev/null"])',
    'subprocess.run(["git", "config", "--local", "core.hooksPath", ".git/empty"])',
    'subprocess.run(["git", "config", "--unset", "core.hooksPath"])',
    'subprocess.run(cmd, env=dict(os.environ, HUSKY="0"))',
    'hook_env = {"SKIP": "anti-ratchet"}',
    '$env:HUSKY = "0"',
])
def test_the_scan_catches_each_way_of_instructing_a_bypass(line):
    assert _hits(line), line


@pytest.mark.covers("FR-01.11/AC54")
@pytest.mark.parametrize("line", [
    "bash scripts/install-hooks.sh sets the hooks path to scripts/hooks",
    "warn={t['WARN']} skip={t['SKIP']})",
    "git -C wt commit -m message",
    "GIT_CONFIG_GLOBAL points the test at an empty config file",
    'SKIP = "skip"',
    "if SKIP == verdict:",
    'VERDICTS = ("PASS", "SKIP", "FAIL")',
    'counts = {"PASS": 0, "SKIP": 0}',
    "git config --local core.hooksPath scripts/hooks",
    'subprocess.run(["git", "config", "core.hooksPath", "scripts/hooks"])',
    'git commit -m "fix -nonce handling"',
    "git -C wt commit -q -m message",
    "the environment of the run is printed",
])
def test_the_scan_leaves_ordinary_lines_alone(line):
    assert not _hits(line), line
