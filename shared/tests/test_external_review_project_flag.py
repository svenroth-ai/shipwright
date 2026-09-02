"""Regression test: every documented `uv run .../external_review.py`
invocation must pass `--project <plan_plugin_root>`, and the
`plan_plugin_root` value that requires must be a real, threaded parameter
rather than an unresolved placeholder.

`external_review.py` lives under `shared/scripts/tools/` with no
`pyproject.toml` of its own -- the `openai` dependency it imports is
declared only in `plugins/shipwright-plan/pyproject.toml`. `uv run`
resolves project context from the *current working directory*, not from
the invoked script's path, so a call site with no `--project` silently
degrades to whatever (if any) pyproject.toml happens to be nearest cwd.

This repo's OWN root `pyproject.toml` happens to declare `openai` too, so
plain `uv run` resolves fine *inside this monorepo* -- which is exactly
why the bug shipped unnoticed. A consumer project (no root
pyproject.toml at all) has no such luck: the import throws and the
review cascade silently falls back to internal-only reviewers. See
iterate-2026-08-18-external-review-project-flag.

Deliberately a static/textual assertion over the call sites, not a
`uv run` execution -- exercising the real import would pass in this repo
today regardless of whether `--project` is present, proving nothing about
the actual (consumer-project) failure mode.

Scans the whole *live instruction* tree (`plugins/`, `shared/`) rather
than a fixed file allowlist, so a new call site added anywhere is caught
automatically. `.shipwright/` (historical planning and decision records)
and `docs/` are excluded on purpose -- grep confirms neither contains a real
`uv run ... external_review.py` invocation block, only prose mentions of
the script's name; scanning them would require allowlisting ~15 archived
files that are never read as live instructions.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ["plugins", "shared"]

# Directories never worth scanning: dep/venv noise. `plugins/shipwright-plan`
# grows a `.venv` the first time `uv run --project` targets it (as this
# very iterate's own probes did) -- an unpruned rglob would then walk
# vendored `openai`/etc. package markdown (READMEs, api.md) under
# site-packages, which is not this repo's live instruction tree at all.
# Same idiom as shared/tests/test_decision_drop_ssot.py.
_SCAN_EXCLUDE_DIRNAMES = {".git", ".venv", "node_modules", ".worktrees", "__pycache__"}

# Known-good total as of this iterate -- a sanity floor/ceiling so a scan
# that silently finds nothing (e.g. a fence-style change breaking the
# regex) fails loudly instead of passing vacuously, and so a newly added
# call site is deliberately accounted for here, not just auto-absorbed.
# Counts individual `uv run` COMMANDS, not enclosing fences -- a fence
# holding two invocations must count (and be checked) as two.
EXPECTED_TOTAL_COMMANDS = 9

# `--project` must be the token immediately after `uv run`, quoted --
# anchored via `.match()` so a `--project` placed later in the command
# (e.g. AFTER the script path, where uv reads it as an argument to the
# *script* instead of to itself, and it does nothing) fails to match at
# all, rather than matching at some later offset that then needs a
# separate position check. Quotes are required, not optional: a bare
# `{plugin_root}` breaks on an installed plugin-cache path containing a
# space -- all 9 targeted sites (including shipwright-plan's own 3,
# pre-existing before this iterate) are quoted now, closing that gap
# rather than leaving it for a deferred repo-wide sweep, since these are
# exactly the invocations this fix already touches (external LLM review
# findings, both providers, independently).
_UV_RUN_PROJECT = re.compile(r'^\s*uv run\s+--project\s+"(\{\w+\})"')

# Fences may be indented under a numbered list item.
_BASH_FENCE = re.compile(r"^[ \t]*```bash\n(.*?)\n[ \t]*```", re.DOTALL | re.MULTILINE)

# Splits a fence into one chunk per `uv run` command, each running from its
# own `uv run` up to (not including) the next one -- so two invocations in
# one fence are checked independently rather than as a single blob where
# the first command's --project can cover for the second's missing one.
_UV_RUN_CMD_START = re.compile(r"^[ \t]*uv run\b", re.MULTILINE)

# The real invocation, not just a prose mention of the script name (e.g.
# "--payload-file \"{external_review.py stdout}\"" has no script path).
_SCRIPT_PATH = "scripts/tools/external_review.py"

# shipwright-plan owns the `openai` dependency, so its own call sites'
# pre-existing `--project {plugin_root}` is already correct (self-
# referential). Every other plugin needs the cross-plugin
# `{plan_plugin_root}` value -- `{plugin_root}` there points at the
# WRONG plugin's root and would resolve the wrong (or no) pyproject.toml.
_PLAN_OWNED_PREFIX = "plugins/shipwright-plan/"


def _split_uv_run_commands(block: str) -> list[str]:
    starts = [m.start() for m in _UV_RUN_CMD_START.finditer(block)]
    bounds = starts + [len(block)]
    return [block[bounds[i] : bounds[i + 1]] for i in range(len(starts))]


def _external_review_commands(text: str) -> list[str]:
    commands = []
    for fence_match in _BASH_FENCE.finditer(text):
        for cmd in _split_uv_run_commands(fence_match.group(1)):
            if _SCRIPT_PATH in cmd:
                commands.append(cmd)
    return commands


def _iter_scanned_markdown_files():
    for root_name in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT / root_name):
            dirnames[:] = [d for d in dirnames if d not in _SCAN_EXCLUDE_DIRNAMES]
            for filename in filenames:
                if filename.endswith(".md"):
                    yield Path(dirpath) / filename


def _find_all_invocations() -> list[tuple[Path, str]]:
    found = []
    for path in _iter_scanned_markdown_files():
        text = path.read_text(encoding="utf-8")
        for cmd in _external_review_commands(text):
            found.append((path.relative_to(REPO_ROOT), cmd))
    return found


def _invocation_defect(rel_path: Path, command: str) -> str | None:
    """None if this single `uv run --project <value> ... external_review.py`
    command's shape is correct; else a one-line description of what's
    wrong. `command` is everything from its own `uv run` up to (not
    including) the next `uv run` in the same fence, if any."""
    match = _UV_RUN_PROJECT.match(command)
    if not match:
        return (
            "no `uv run --project <value>` immediately preceding the script "
            "path -- either --project is missing, or it's placed AFTER the "
            "script path where uv reads it as an argument to the script, "
            "not to itself, and it does nothing"
        )
    value = match.group(1)
    allowed = (
        {"{plugin_root}"}
        if str(rel_path).replace("\\", "/").startswith(_PLAN_OWNED_PREFIX)
        else {"{plan_plugin_root}"}
    )
    if value not in allowed:
        return f"--project value is {value!r}, expected one of {sorted(allowed)}"
    return None


def test_external_review_calls_pass_project_flag():
    invocations = _find_all_invocations()
    assert len(invocations) == EXPECTED_TOTAL_COMMANDS, (
        f"Expected {EXPECTED_TOTAL_COMMANDS} `uv run ... external_review.py` "
        f"command(s) under {SCAN_ROOTS}, found {len(invocations)}: "
        f"{[str(p) for p, _ in invocations]}. If a call site was "
        f"added/removed, update EXPECTED_TOTAL_COMMANDS after confirming the "
        f"new/changed one also carries a correctly-placed --project."
    )
    defects = [
        f"{rel_path}: {reason}\n{command}"
        for rel_path, command in invocations
        if (reason := _invocation_defect(rel_path, command)) is not None
    ]
    assert not defects, (
        "The following `uv run .../external_review.py` invocations don't "
        "correctly pass --project <plan_plugin_root>. Without it (or with "
        "it misplaced/wrong-valued), uv resolves the openai/glm "
        "dependency from whatever pyproject.toml is nearest cwd, not from "
        "shipwright-plan (which declares it) -- silently degrading external "
        "review to the internal-only reviewer cascade in any consumer "
        "project.\n\n" + "\n\n".join(defects)
    )


def test_sub_iterate_runner_declares_plan_plugin_root_input():
    """The consumer side of the new contract: the runner must declare
    `plan_plugin_root` as an Input it expects, not assume it's ambient --
    this subagent has no env vars of its own (unlike a standalone iterate
    session, which does)."""
    text = (
        REPO_ROOT / "plugins/shipwright-iterate/agents/sub-iterate-runner.md"
    ).read_text(encoding="utf-8")
    input_section = text.split("## Input", 1)[1].split("## Workflow", 1)[0]
    assert "plan_plugin_root" in input_section, (
        "sub-iterate-runner.md's Input section no longer declares "
        "plan_plugin_root -- its two external_review.py call sites need it "
        "for --project, and this subagent has no ambient env vars to fall "
        "back on."
    )


def test_canonical_failure_handling_note_exists():
    """A `uv run --project` failure is new with this iterate (the
    placeholder used to be inert for these modes) -- the canonical note
    defining "not a completed review, record as not_run" must exist, and
    every other site must be able to point at it."""
    text = (
        REPO_ROOT
        / "plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md"
    ).read_text(encoding="utf-8")
    assert "resolution and `uv run` failure" in text
    assert "the pass did NOT run" in text


def test_external_review_docstring_shows_project_flag():
    """`external_review.py`'s own module docstring is a 10th, undiffed usage
    mention -- outside the *.md scan above (it's a .py file, and its example
    uses prose `<...>` placeholders, not a `{plan_plugin_root}` token) but
    just as capable of teaching a reader the wrong invocation shape."""
    text = (REPO_ROOT / "shared/scripts/tools/external_review.py").read_text(encoding="utf-8")
    assert "uv run --project <shipwright-plan plugin root>" in text, (
        "external_review.py's module docstring no longer shows `uv run "
        "--project` in its usage example -- this is the script's own "
        "self-documentation, not covered by the markdown scan above."
    )


def test_campaign_to_runner_plan_plugin_root_chain_composes():
    """category:integration -- campaign-mode.md is FRAMEWORK cross-component
    machinery (campaign_*/campaign-mode.md, per SKILL.md's Risk Taxonomy);
    the two producer/consumer unit checks above each verify one HALF of the
    plan_plugin_root contract in isolation. This proves the full chain
    actually composes: the orchestrator (campaign-mode.md) supplies the
    value at spawn -> the runner (sub-iterate-runner.md) declares it as an
    expected Input -> the runner's OWN call sites consume the identical
    `{plan_plugin_root}` token, not a different or stale placeholder."""
    campaign_text = (
        REPO_ROOT
        / "plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md"
    ).read_text(encoding="utf-8")
    runner_text = (
        REPO_ROOT / "plugins/shipwright-iterate/agents/sub-iterate-runner.md"
    ).read_text(encoding="utf-8")

    spawn_section = campaign_text.split("Spawn sub-iterate-runner subagent:", 1)[1][:600]
    assert "plan_plugin_root" in spawn_section, "producer hop broken (see unit test above)"

    input_section = runner_text.split("## Input", 1)[1].split("## Workflow", 1)[0]
    assert "plan_plugin_root" in input_section, "consumer declaration hop broken"

    consuming_commands = [
        cmd for cmd in _external_review_commands(runner_text) if "{plan_plugin_root}" in cmd
    ]
    assert len(consuming_commands) == 2, (
        f"expected both of sub-iterate-runner.md's external_review.py call "
        f"sites to consume the literal {{plan_plugin_root}} token supplied "
        f"by campaign-mode.md's spawn, found {len(consuming_commands)} -- "
        f"the declared Input is not actually wired to the invocations that "
        f"need it, breaking the producer->consumer chain end to end."
    )


def test_campaign_mode_threads_plan_plugin_root_into_runner_spawn():
    """The producer side: the orchestrator must actually pass
    plan_plugin_root when it spawns the runner, or the consumer-side
    Input declaration is documentation for a value nobody supplies."""
    text = (
        REPO_ROOT
        / "plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md"
    ).read_text(encoding="utf-8")
    spawn_section = text.split("Spawn sub-iterate-runner subagent:", 1)[1][:600]
    assert "plan_plugin_root" in spawn_section, (
        "campaign-mode.md's sub-iterate-runner spawn (step 3c) no longer "
        "names plan_plugin_root in the brief -- the runner's Input "
        "declaration would document a parameter nothing actually supplies."
    )
