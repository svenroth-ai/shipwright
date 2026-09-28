"""Regression test for iterate-2026-09-28-hooks-uv-run-project-pin.

Every `uv run` invocation in a plugin's hooks.json must be pinned with
`--no-project`. Without it, `uv run` resolves its target project by
walking up from the *session's current working directory* — not from
the hook script's own path — so a Claude Code session whose CWD happens
to be an unrelated uv-managed Python project causes every hook to
silently bind to and try to sync/reinstall THAT project. On Windows this
can hard-fail with a file-lock error (os error 32) when that project has
a running process holding an entry-point .exe open, breaking every hook
for the whole session.

A second test enforces exact-prefix consistency across plugins for the
same target script: `codex_hooks_sync.py`'s bundle-merge step
(`codex_hook_merge.py`) deduplicates hook entries shared by more than one
plugin (e.g. every plugin's SessionStart chains the same shared
`run_if_cache_ready.py`) and hard-fails if two plugins register the same
script with a different flag prefix. A flag added to one plugin's copy
of a shared invocation but not another's would both re-introduce this
bug for the un-updated copy AND break the Codex bundle merge.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_GLOB = "plugins/*/hooks*/hooks.json"
_MIN_EXPECTED_FILES = 13  # one hooks.json per plugin, plus shipwright-iterate's hooks-codex sibling


def _collect_command_strings(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_collect_command_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_command_strings(item))
    return found


def _hook_files() -> list[Path]:
    files = sorted(REPO_ROOT.glob(PLUGINS_GLOB))
    assert len(files) >= _MIN_EXPECTED_FILES, (
        f"expected at least {_MIN_EXPECTED_FILES} hooks.json files under "
        f"{PLUGINS_GLOB}, found {len(files)} — fixture is wrong or repo "
        f"layout changed: {files}"
    )
    return files


# Matches each individual `uv run ...` invocation within a command string,
# up to (not including) its first quoted argument — the quoted argument is
# the target script path, everything before it is the flag prefix. A
# single "command" value can chain more than one `uv run` (rare, but the
# pattern must not assume exactly one per string). The opening quote is a
# lookahead, not part of the match, so `match.end()` lands ON that quote —
# `_target_script` below matches starting there. Consuming the quote inside
# the match instead (an earlier version of this pattern did) leaves
# `match.end()` one character too far in, so `_target_script` never finds
# its leading `"` and silently returns None for every call — caught only
# because `test_dependency_carrying_scripts_retain_required_with_flags`
# below asserts the scripts it looks for are actually seen at all; the
# cross-plugin consistency test alone stayed green either way, since an
# always-empty per-script map can never disagree with itself.
_UV_RUN_PREFIX = re.compile(r'uv run((?:(?!uv run)[^"])*)(?=")')


def _uv_run_prefixes(cmd: str) -> list[str]:
    """Return each `uv run <flags>` prefix (flags only, trimmed) found in
    *cmd*, in order."""
    return [m.group(1).strip() for m in _UV_RUN_PREFIX.finditer(cmd)]


def _target_script(cmd: str, prefix_end: int) -> str | None:
    """The first quoted argument immediately following a `uv run <flags>`
    match — the invoked script path, used as the dedup key for the
    cross-plugin prefix-consistency check."""
    rest = cmd[prefix_end:]
    match = re.match(r'"([^"]+)"', rest)
    return match.group(1) if match else None


@pytest.mark.parametrize("hooks_path", _hook_files(), ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_every_uv_run_hook_command_has_no_project(hooks_path: Path) -> None:
    """Every `uv run` invocation in this hooks.json must start with
    `uv run --no-project` (exact prefix, not merely present somewhere in
    the flag list), so hook execution can never depend on, or attempt to
    mutate, whatever uv-managed project happens to be the session's CWD.
    """
    raw = hooks_path.read_text(encoding="utf-8")
    config = json.loads(raw)
    commands = _collect_command_strings(config)
    assert commands, f"{hooks_path} has no hook commands — fixture broken?"

    offenders: list[str] = []
    for cmd in commands:
        for prefix in _uv_run_prefixes(cmd):
            if not (prefix == "--no-project" or prefix.startswith("--no-project ")):
                offenders.append(f"uv run {prefix}".strip())

    assert not offenders, (
        f"{hooks_path.relative_to(REPO_ROOT)}: {len(offenders)} `uv run` "
        f"invocation(s) don't start with `--no-project` immediately after "
        f"`uv run`; uv would resolve its target project from the session's "
        f"CWD instead of running standalone:\n"
        + "\n".join(f"    {c}" for c in offenders)
    )


def test_shared_uv_run_scripts_use_identical_flag_prefix_across_plugins() -> None:
    """A script invoked via `uv run` from more than one hooks.json must use
    the exact same flag prefix everywhere. `codex_hooks_sync.py`'s bundle
    merge (`codex_hook_merge.py`) deduplicates by (event, matcher, command)
    shape and raises on a prefix mismatch for the same script — this test
    catches the same drift locally, before it ever reaches that merge step.
    """
    prefixes_by_script: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))

    for hooks_path in _hook_files():
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        for cmd in _collect_command_strings(config):
            for match in _UV_RUN_PREFIX.finditer(cmd):
                prefix = match.group(1).strip()
                script = _target_script(cmd, match.end())
                if script is None:
                    continue
                prefixes_by_script[script][prefix].append(hooks_path)

    offenders: list[str] = []
    for script, by_prefix in prefixes_by_script.items():
        if len(by_prefix) > 1:
            detail = "; ".join(
                f"{prefix!r} in {[str(p.relative_to(REPO_ROOT)) for p in paths]}"
                for prefix, paths in by_prefix.items()
            )
            offenders.append(f"{script}: {detail}")

    assert not offenders, (
        "the following scripts are invoked with a DIFFERENT `uv run` flag "
        "prefix across plugins — this would break codex_hooks_sync's "
        "bundle merge (which dedups by exact command shape) and means the "
        "fix wasn't applied uniformly:\n" + "\n".join(f"    {o}" for o in offenders)
    )


# Scripts whose sys.executable-propagated subprocess chain needs a
# third-party dependency the session's CWD project used to supply for free
# before --no-project (doubt review, iterate-2026-09-28-hooks-uv-run-project-
# pin) — kept in one place so a rename/removal here fails loudly instead of
# this test's coverage silently shrinking.
_REQUIRED_WITH_FLAGS: dict[str, tuple[str, ...]] = {
    "run_if_cache_ready.py": ("pyyaml", "jsonschema"),
    "audit_compliance_on_stop.py": ("pyyaml", "jsonschema"),
}


def test_dependency_carrying_scripts_retain_required_with_flags() -> None:
    """`run_if_cache_ready.py` and `audit_compliance_on_stop.py` each need
    pyyaml/jsonschema deep in their subprocess chain. Neither the
    `--no-project`-prefix check above nor the cross-plugin consistency check
    inspects flag CONTENT beyond that, so dropping `--with pyyaml --with
    jsonschema` from every plugin's copy at once would pass both of them
    while silently breaking those scripts at runtime."""
    seen_scripts: set[str] = set()
    offenders: list[str] = []

    for hooks_path in _hook_files():
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        for cmd in _collect_command_strings(config):
            for match in _UV_RUN_PREFIX.finditer(cmd):
                prefix = match.group(1).strip()
                script = _target_script(cmd, match.end())
                if script is None:
                    continue
                script_name = Path(script).name
                required = _REQUIRED_WITH_FLAGS.get(script_name)
                if required is None:
                    continue
                seen_scripts.add(script_name)
                missing = [pkg for pkg in required if f"--with {pkg}" not in prefix]
                if missing:
                    offenders.append(
                        f"{hooks_path.relative_to(REPO_ROOT)}: {script_name} is missing "
                        f"--with {{{', '.join(missing)}}} (prefix: 'uv run {prefix}')"
                    )

    assert not offenders, (
        "the following `uv run` invocations dropped a required --with "
        "dependency flag:\n" + "\n".join(f"    {o}" for o in offenders)
    )
    missing_scripts = set(_REQUIRED_WITH_FLAGS) - seen_scripts
    assert not missing_scripts, (
        f"expected to find at least one `uv run` invocation of each of "
        f"{sorted(_REQUIRED_WITH_FLAGS)} across {PLUGINS_GLOB}, but never "
        f"saw {sorted(missing_scripts)} — script renamed/removed, or the "
        f"fixture no longer matches hooks.json's shape"
    )
