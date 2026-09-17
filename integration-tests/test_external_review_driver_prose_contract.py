"""Drift-protection test: every literal `external_review.py` invocation
example across every plugin includes `--driver`.

`--driver` is a required, no-default CLI flag (shared/scripts/tools/
external_review.py) — an omitted call fails closed at argparse, but only at
RUNTIME. A stale doc that dropped `--driver` from its copy-pasteable example
would only be caught the next time someone actually runs it. This test
catches it at review time instead, by scanning every fenced shell block in
every plugin's markdown for a real invocation (identified by
`external_review.py` co-occurring with `--mode`) and asserting `--driver`
appears in the SAME block. A second, line-level scan covers the two SKILL.md
call sites (`shipwright-iterate`, `shipwright-plan`), which mention the
invocation inline as prose rather than in a fenced block — a Stage-1
spec-reviewer catch: the fenced-block scanner alone left exactly those two
AC-named sites covered by prose-trust only, the gap AC-8 says must not exist.

Deliberately NOT scoped to a hardcoded file list — a future ninth call site
must satisfy this contract automatically, the same way
`test_review_routing_contract.py` pins existing sites without pre-declaring
where the next one will be. Historical `.shipwright/planning/` documents are
excluded: those are frozen records of past iterates, not live prose an agent
follows today.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"

_FENCED_BLOCK_RE = re.compile(r"```[^\r\n`]*\r?\n(.*?)```", re.DOTALL)
_INVOCATION_RE = re.compile(r"external_review\.py")
_MODE_FLAG_RE = re.compile(r"--mode\b")


def _fenced_shell_blocks() -> list[tuple[Path, str]]:
    blocks: list[tuple[Path, str]] = []
    for md_file in PLUGINS_ROOT.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        for block in _FENCED_BLOCK_RE.findall(text):
            if _INVOCATION_RE.search(block) and _MODE_FLAG_RE.search(block):
                blocks.append((md_file, block))
    return blocks


def _inline_prose_mentions() -> list[tuple[Path, str]]:
    """Non-fenced invocation mentions — a single prose/blockquote line
    naming `external_review.py` and `--mode` directly, the shape both
    SKILL.md call sites use instead of a fenced example. Lines inside a
    fenced block are skipped — a multi-line shell command continued with
    `\\` puts `--mode` on one line and `--driver` on the next, which this
    line-level scan cannot see; the fenced-block test above already covers
    that case correctly at block granularity."""
    lines: list[tuple[Path, str]] = []
    for md_file in PLUGINS_ROOT.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        in_fence = False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if _INVOCATION_RE.search(line) and _MODE_FLAG_RE.search(line):
                lines.append((md_file, line))
    return lines


def test_every_external_review_invocation_block_passes_driver():
    blocks = _fenced_shell_blocks()
    assert blocks, "expected at least one external_review.py invocation block under plugins/"

    missing = [
        f"{path.relative_to(REPO_ROOT)}: {block.strip()!r}"
        for path, block in blocks
        if "--driver" not in block
    ]
    assert not missing, (
        "the following external_review.py invocation examples are missing "
        "--driver (required, no default):\n" + "\n".join(missing)
    )


def test_every_inline_prose_mention_passes_driver():
    lines = _inline_prose_mentions()
    assert lines, "expected at least one inline external_review.py mention under plugins/"

    missing = [
        f"{path.relative_to(REPO_ROOT)}: {line.strip()!r}"
        for path, line in lines
        if "--driver" not in line
    ]
    assert not missing, (
        "the following inline external_review.py mentions are missing "
        "--driver (required, no default):\n" + "\n".join(missing)
    )


def test_sub_iterate_runner_hardcodes_a_concrete_driver_not_a_placeholder():
    """sub-iterate-runner.md is spawned exclusively as a Claude Code subagent
    (the Agent tool has no Codex-CLI equivalent yet — trg-a27ab4d9 tracks
    real Codex-driven campaign wiring as separate future work), so `claude`
    is the only value that can reach this file today. An unresolved
    `{driver}` placeholder here — unlike in iteration-planning.md /
    iteration-reviews.md, whose caller genuinely varies — has no caller to
    substitute it, and fails closed at argparse on every real run."""
    path = (
        PLUGINS_ROOT / "shipwright-iterate" / "agents" / "sub-iterate-runner.md"
    )
    blocks = [block for p, block in _fenced_shell_blocks() if p == path]
    assert len(blocks) == 2, f"expected 2 external_review.py blocks in {path}, found {len(blocks)}"
    for block in blocks:
        assert '--driver "claude"' in block, (
            f"sub-iterate-runner.md must pass a concrete --driver \"claude\", "
            f"never an unresolved {{driver}} placeholder:\n{block.strip()!r}"
        )
        assert "{driver}" not in block


def test_known_call_sites_are_still_present():
    """A sanity floor: if every one of these files stopped matching the
    scanner (e.g. a rename, or the fence style changed), the test above would
    pass vacuously on zero blocks from them. Pins the count so that silent
    loss is caught here, not by the (must-never-fire) assertion above."""
    known_fenced_files = {
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "references" / "iteration-planning.md",
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "references" / "iteration-reviews.md",
        PLUGINS_ROOT / "shipwright-iterate" / "agents" / "sub-iterate-runner.md",
        PLUGINS_ROOT / "shipwright-plan" / "skills" / "plan" / "references" / "step-5-external-review.md",
        PLUGINS_ROOT / "shipwright-plan" / "skills" / "plan" / "references" / "external-review.md",
        PLUGINS_ROOT / "shipwright-build" / "skills" / "build" / "references" / "code-review.md",
    }
    known_inline_files = {
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md",
        PLUGINS_ROOT / "shipwright-plan" / "skills" / "plan" / "SKILL.md",
    }
    seen_fenced = {path for path, _block in _fenced_shell_blocks()}
    seen_inline = {path for path, _line in _inline_prose_mentions()}
    missing = (known_fenced_files - seen_fenced) | (known_inline_files - seen_inline)
    assert not missing, f"expected invocation coverage in: {sorted(str(p) for p in missing)}"
