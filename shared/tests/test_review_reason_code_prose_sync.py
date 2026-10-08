"""Prose sync: every shipped command that closes a review ``not_run`` /
``not_applicable`` names its ``--reason-code``.

F11's ``check_review_record`` refuses a skipped row without a closed-vocabulary
code at every complexity (``review_record_closure.py``). An instruction that
still tells an agent to write a codeless row is therefore an instruction to red
its own run, and ``record --force`` REBUILDS the row, so a forced rewrite drops
whatever code the earlier writer stored. This test greps the runtime prose
(``plugins/**/*.md``, ``shared/prompts/*.md``) for ``record`` / ``close-missing``
commands, follows each one over its continuation lines, and fails when a command
that can write a skipped status carries no ``--reason-code``.

A line documenting the OLD behaviour (a "before" example) may opt out with the
inline marker ``codeless-ok`` anywhere in the command.

Scope limits: only command-shaped text is scanned. A prose table cell or a
sentence that says "record it ``not_run``" without a ``record`` / ``…`` command
start is NOT seen, and neither is a command whose status comes from a shell
variable; those stay a review responsibility.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ALLOW = "codeless-ok"

#: Where a command starts: the CLI's own subcommands, or the `…` prefix the
#: references use for "the record invocation prefix".
_START = re.compile(r"record_review_pass\.py\"?\s+(record|close-missing)\b|(^|\s)…\s+(record\b|--)")
#: A status argument that can write a skipped row: a literal, or a `{a | b}` template.
_SKIPPED = re.compile(r"--status\s+\"?(\{[^}]*\b(not_run|not_applicable)\b[^}]*\}|not_run\b|not_applicable\b)")


def _docs() -> list[Path]:
    found = sorted((REPO / "plugins").glob("**/*.md")) + sorted((REPO / "shared" / "prompts").glob("*.md"))
    # Filter on the REPO-RELATIVE parts: this clone may itself sit under a `.worktrees/` dir.
    return [p for p in found if not {".worktrees", "node_modules"} & set(p.relative_to(REPO).parts)]


def _open(text: str) -> bool:
    """A line leaves the command open on a trailing ``\\`` or an unbalanced quote / backtick."""
    return text.rstrip().endswith("\\") or text.count('"') % 2 == 1 or text.count("`") % 2 == 1


def _commands(lines: list[str]):
    """Yield ``(line_no, command_text)`` for each command start plus its continuation lines."""
    i = 0
    while i < len(lines):
        if not _START.search(lines[i]):
            i += 1
            continue
        start, chunk = i, lines[i]
        while _open(chunk) and i + 1 < len(lines) and not _START.search(lines[i + 1]):
            i += 1
            chunk += "\n" + lines[i]
        yield start + 1, chunk
        i += 1


def codeless(text: str) -> list[tuple[int, str]]:
    """The commands in ``text`` that can write a skipped row and name no code."""
    return [(n, cmd) for n, cmd in _commands(text.splitlines())
            if _SKIPPED.search(cmd) and "--reason-code" not in cmd and ALLOW not in cmd]


@pytest.mark.covers("FR-01.11")
def test_every_skipped_record_command_names_its_reason_code():
    hits = [f"{path.relative_to(REPO).as_posix()}:{n}: {cmd.strip()[:160]}"
            for path in _docs() for n, cmd in codeless(path.read_text(encoding="utf-8"))]
    why = "write a skipped review row without --reason-code; F11 refuses it and --force drops any earlier code"
    assert not hits, f"these commands {why}:\n" + "\n".join(hits)


@pytest.mark.covers("FR-01.11")
def test_the_scan_sees_the_known_command_shapes():
    """Guard the guard: the scan must find the shapes it exists to police, or a
    regex drift would turn the sync test into a vacuous pass."""
    cmds = [cmd for path in _docs() for _, cmd in _commands(path.read_text(encoding="utf-8").splitlines())]
    assert len(cmds) >= 10, f"only {len(cmds)} record commands found — the start pattern has drifted"
    skipped = sum(1 for cmd in cmds if _SKIPPED.search(cmd))
    assert skipped >= 8, f"only {skipped} skipped-status commands found — the status pattern has drifted"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("text", "flagged"), [
    ('… record --review-type doubt --status not_applicable --force \\\n    --disposition "x"', True),
    ('… record --review-type doubt --status not_applicable --force \\\n    --reason-code diff-below-threshold', False),
    ('uv run "x/record_review_pass.py" record \\\n  --status "{completed | not_run}" \\\n  --provider null', True),
    ('`record_review_pass.py record\n  --status not_run\n  --disposition "y"`', True),
    ('… --review-type spec --status completed --from spec-reviewer', False),
    ('… record --status not_run --disposition "old shape"  # codeless-ok', False),
])
def test_scan_classifies_command_shapes(text: str, flagged: bool):
    assert bool(codeless("intro\n" + text + "\noutro\n")) is flagged, text
