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

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


_DRIVER_ARG_RE = re.compile(r'--driver\s+"(.*?)"(?=\s*(?:>|\\|$))', re.MULTILINE)


def test_sub_iterate_runner_resolves_its_own_driver_not_a_placeholder():
    """sub-iterate-runner.md is spawned exclusively as a Claude Code subagent
    (the Agent tool has no Codex-CLI equivalent yet — trg-a27ab4d9 tracks
    real Codex-driven campaign wiring as separate future work), so the
    driving *harness* here is always `claude` — but it is no longer always
    `claude` the *roster* value, since Codextender (CODEXTENDER_ACTIVE) can
    make a Claude-Code-driven session Codex-backed. Unlike
    iteration-planning.md / iteration-reviews.md, this file has no caller to
    substitute a `{driver}` template placeholder for it, so whatever value
    reaches `--driver` must be SELF-RESOLVING inside the block itself — a
    bare `{driver}` placeholder here would fail closed at argparse on every
    real run, same as before Codextender.

    The `--driver` ARGUMENT itself (not just anywhere in the block) is
    extracted and checked — a local PR-review preflight (Codextender
    Part C, F11) found the original `"CODEXTENDER_ACTIVE" in block` check
    would pass even if `--driver` were hardcoded back to `"claude"` and
    `CODEXTENDER_ACTIVE` only appeared elsewhere (a comment, another
    argument) — never proving the variable is wired into the flag it
    exists to control."""
    path = (
        PLUGINS_ROOT / "shipwright-iterate" / "agents" / "sub-iterate-runner.md"
    )
    blocks = [block for p, block in _fenced_shell_blocks() if p == path]
    assert len(blocks) == 2, f"expected 2 external_review.py blocks in {path}, found {len(blocks)}"
    for block in blocks:
        assert "{driver}" not in block, (
            f"sub-iterate-runner.md has no caller to substitute a {{driver}} "
            f"template placeholder — the value must resolve inside the block "
            f"itself (a literal, or a self-contained env-conditional "
            f"expression):\n{block.strip()!r}"
        )
        match = _DRIVER_ARG_RE.search(block)
        assert match, f"could not extract the --driver argument from block:\n{block.strip()!r}"
        driver_value = match.group(1)
        assert driver_value == "claude" or "CODEXTENDER_ACTIVE" in driver_value, (
            f"sub-iterate-runner.md's --driver ARGUMENT must either be the "
            f"concrete literal \"claude\", or itself contain a self-resolving "
            f"CODEXTENDER_ACTIVE conditional (Codextender can make this "
            f"Claude-Code-driven subagent Codex-backed) — the value found was "
            f"{driver_value!r} in block:\n{block.strip()!r}"
        )


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


# Extracted LIVE from each block below, never hand-copied duplicates — a
# local PR-review preflight (F11, Codextender Part C) found the prior version
# of this test executed hardcoded constants instead of the actual markdown
# text, so a typo or regression in the real prose could pass unnoticed.
_DRIVER_VAR_ASSIGN_RE = re.compile(
    r'(DRIVER=claude\r?\n\[[^\r\n]*CODEXTENDER_ACTIVE[^\r\n]*DRIVER=codex)'
)

_BASH = shutil.which("bash")


def _require_bash():
    if _BASH is not None:
        return
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("bash not found on PATH in CI — install bash (present by default "
                    "on ubuntu-latest runners) to verify the CODEXTENDER_ACTIVE shell "
                    "idioms")
    pytest.skip("bash not found on PATH")


def _extract_live_idiom(block: str) -> str | None:
    """The block's own driver-resolution snippet, ready to run under bash --
    None when the block does not self-resolve (e.g. a `{driver}` template
    placeholder substituted by the caller, never runnable in isolation)."""
    var_match = _DRIVER_VAR_ASSIGN_RE.search(block)
    if var_match:
        return var_match.group(1) + '; echo "$DRIVER"'
    arg_match = _DRIVER_ARG_RE.search(block)
    if arg_match and "CODEXTENDER_ACTIVE" in arg_match.group(1):
        return f'echo "{arg_match.group(1)}"'
    return None


def _live_idioms_per_block() -> list[tuple[Path, str]]:
    """One entry PER self-resolving block found, un-deduplicated -- so a
    removed or malformed site shrinks this count directly, rather than being
    absorbed into an already-seen identical idiom string."""
    return [
        (path, idiom)
        for path, block in _fenced_shell_blocks()
        for idiom in [_extract_live_idiom(block)]
        if idiom is not None
    ]


def _live_idioms() -> list[tuple[str, Path]]:
    """Deduplicated (idiom -> one owning path), for the runtime-execution
    test below -- running bash once per DISTINCT idiom is sufficient proof;
    the per-block count is pinned separately by the sanity floor."""
    seen: dict[str, Path] = {}
    for path, idiom in _live_idioms_per_block():
        seen.setdefault(idiom, path)
    return sorted(seen.items(), key=lambda pair: str(pair[1]))


def test_live_idioms_cover_every_self_resolving_site():
    """Sanity floor pinning the exact block count: 2 var-form (external-review.md,
    code-review.md) + 4 inline-form (sub-iterate-runner.md x2,
    step-5-external-review.md x2) = 6. A silently dropped or malformed site
    would shrink this count directly, which >= 2 (a dedup-based floor) could
    not catch (F11 local PR-review preflight comment, round 5)."""
    per_block = _live_idioms_per_block()
    assert len(per_block) == 6, (
        f"expected exactly 6 self-resolving driver-idiom blocks "
        f"(2 var-form + 4 inline-form), found {len(per_block)}: {per_block!r}"
    )
    idioms = _live_idioms()
    assert len(idioms) == 2, (
        f"expected exactly 2 DISTINCT idiom strings (var-form + inline-form), "
        f"found {len(idioms)}: {idioms!r}"
    )


@pytest.mark.parametrize(
    "env_value,expected",
    [(None, "claude"), ("", "claude"), ("1", "codex"), ("0", "codex")],
)
def test_codextender_active_shell_idiom_resolves_correctly(env_value, expected):
    """Every self-resolving driver idiom, extracted LIVE from its own markdown
    block (see `_extract_live_idiom` — not a hand-copied duplicate), must
    resolve `codex` for any non-empty CODEXTENDER_ACTIVE value and `claude`
    when unset/empty. `env_value=None` = unset, `""` = set but empty (docs/
    hooks-and-pipeline.md documents both as inactive)."""
    _require_bash()
    env = {k: v for k, v in os.environ.items() if k != "CODEXTENDER_ACTIVE"}
    if env_value is not None:
        env["CODEXTENDER_ACTIVE"] = env_value

    idioms = _live_idioms()
    assert idioms, "no self-resolving driver idioms were extracted from plugins/"
    for idiom, path in idioms:
        result = subprocess.run([_BASH, "-c", idiom], capture_output=True,
                                 text=True, env=env, timeout=10)
        assert result.stdout.strip() == expected, (
            f"{path.relative_to(REPO_ROOT)}: idiom {idiom!r} produced "
            f"{result.stdout.strip()!r} (expected {expected!r}); stderr: {result.stderr}"
        )


# DRIVER_ROSTERS keys external_review.py's `reviews` dict by each roster
# identity's own name (`{glm, openai}` for --driver claude, `{glm, opus}` for
# --driver codex — shared/scripts/tools/external_review.py, DRIVER_ROSTERS),
# so a consumer that only ever parses `reviews.openai.feedback` silently gets
# nothing back under Codextender (--driver codex), where that key is
# `reviews.opus` instead. A local PR-review preflight (F11, Codextender Part
# C) found exactly this: the driver-selection fix updated 11 --driver call
# sites but missed the downstream consumer prose in two of them. Guards
# against the same class of drift recurring silently.
_OPENAI_FEEDBACK_RE = re.compile(r"reviews\.openai\.feedback")
_OPUS_FEEDBACK_RE = re.compile(r"reviews\.opus\.feedback")

# Proximity window (lines), not file-level: the CI PR-review gate (Tier-3,
# round 5) found a file-level "both mentioned somewhere" check does not prove
# a SPECIFIC openai.feedback occurrence is the one paired with the opus
# alternative, only that some occurrence of each exists anywhere in the file.
# Binding each occurrence to a nearby opus mention ties the check to the
# actual parse SITE, not just the file.
_PARSE_SITE_PROXIMITY_LINES = 15


def _line_numbers(pattern: "re.Pattern[str]", text: str) -> list[int]:
    return [text.count("\n", 0, m.start()) + 1 for m in pattern.finditer(text)]


def test_every_openai_feedback_parse_site_also_names_the_opus_key():
    sites_missing_opus = []
    for md_file in PLUGINS_ROOT.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        openai_lines = _line_numbers(_OPENAI_FEEDBACK_RE, text)
        if not openai_lines:
            continue
        opus_lines = _line_numbers(_OPUS_FEEDBACK_RE, text)
        rel = str(md_file.relative_to(REPO_ROOT))
        for openai_line in openai_lines:
            if not any(abs(openai_line - opus_line) <= _PARSE_SITE_PROXIMITY_LINES
                       for opus_line in opus_lines):
                sites_missing_opus.append(f"{rel}:{openai_line}")
    assert not sites_missing_opus, (
        "the following reviews.openai.feedback occurrences have no "
        "reviews.opus.feedback mention (the key under --driver codex / "
        f"Codextender) within {_PARSE_SITE_PROXIMITY_LINES} lines -- a "
        "driver=codex run's second review would be silently dropped at "
        "that specific parse site:\n"
        + "\n".join(sites_missing_opus)
    )


def test_openai_feedback_parse_sites_are_still_present():
    """Sanity floor pinning the 4 known sites, mirroring
    test_known_call_sites_are_still_present above — if every one stopped
    matching (e.g. a rename), the assertion above would pass vacuously."""
    known_sites = {
        PLUGINS_ROOT / "shipwright-build" / "skills" / "build" / "references" / "code-review.md",
        PLUGINS_ROOT / "shipwright-iterate" / "agents" / "sub-iterate-runner.md",
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "references" / "iteration-planning.md",
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "references" / "iteration-reviews.md",
    }
    seen = {
        md_file for md_file in PLUGINS_ROOT.rglob("*.md")
        if _OPENAI_FEEDBACK_RE.search(md_file.read_text(encoding="utf-8"))
    }
    missing = known_sites - seen
    assert not missing, f"expected a reviews.openai.feedback parse mention in: {sorted(str(p) for p in missing)}"
