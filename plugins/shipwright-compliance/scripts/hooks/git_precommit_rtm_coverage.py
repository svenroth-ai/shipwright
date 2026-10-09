#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Git ``pre-commit`` step: the requirement-coverage gate, run by git at the real commit.

The Claude Code hook (``check_rtm_coverage``) decides from the Bash command text, so every
shell shape its reader cannot parse is a commit it never sees. This step fires inside
``git commit`` itself -- whatever wrapper, quoting or redirection led there -- and
measures the manifest AS STAGED FOR THIS COMMIT: git hands a hook the real index
(``GIT_INDEX_FILE``), including the temporary one for ``commit -a`` / ``commit <pathspec>``,
so the PreToolUse hook's "ordering limit" does not exist here. Same measurement
(``rtm_gate_support``), same threshold/baseline, same logged override
(``compliance_override``, hook name ``check_rtm_coverage``).

Exit codes: 0 = allow (also: nothing measurable, or this step itself failed -- a visible
WARN on stderr, never a block), :data:`BLOCK` (3) = the deliberate block. Any other
non-zero exit (uv or the interpreter failing) is NOT a block: ``scripts/hooks/pre-commit``
reports it as a WARN and allows.

**Hand-off.** A command the PreToolUse hook already released through a logged override
leaves a short-lived token (``lib/git_side_release``); this step takes it instead of
demanding a second override for the same commit.

Installed for contributors of this monorepo by ``scripts/install-hooks.sh``
(``core.hooksPath``) via ``scripts/hooks/pre-commit``; ``--no-verify`` skips it, as it
skips every git hook (the PreToolUse hook and CI remain).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HOOK = "check_rtm_coverage"  # one override name for both enforcement points
BLOCK = 3  # distinct from a crash (1) or uv/interpreter failure, which must fail open


def _on_path() -> None:
    here = Path(__file__).resolve().parent
    for entry in (here, here.parent / "lib"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))


def _warn(text: str) -> None:
    print(f"WARN ({HOOK}, git pre-commit): {text}", file=sys.stderr)


def _toplevel() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                         text=True, timeout=10, check=True).stdout.strip()
    return Path(out)


def _project_root(top: Path) -> str:
    """The managed project in the repo being committed to (never the session's env)."""
    shared = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    try:
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared))
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return str(resolve_project_root(allow_env=False, cwd=top))
    except Exception:  # noqa: BLE001 - root resolution failing must not disable the gate
        return str(top)


def check() -> int:
    _on_path()
    import compliance_override as override  # noqa: PLC0415
    import git_side_release  # noqa: PLC0415
    import rtm_gate_support as lib  # noqa: PLC0415

    index = os.environ.get("GIT_INDEX_FILE")
    if index and not os.path.isabs(index):  # git hands hooks a path relative to the toplevel
        os.environ["GIT_INDEX_FILE"] = os.path.abspath(index)
    root = _project_root(_toplevel())
    # taken FIRST, on every run (unmeasurable manifest and errors included): never lingers
    released_by_handoff, handoff_why = git_side_release.claim(root, HOOK)
    measure, warnings = lib.measure(root)
    threshold, config_warnings, _baseline = lib.read_threshold(root)
    warnings += config_warnings
    if measure is None:
        if warnings:
            _warn("; ".join(warnings))
        return 0
    threshold_pct = lib.pct_text(threshold)
    if lib.meets(measure, threshold):
        print(f"{HOOK}: {lib.describe(measure)} >= {threshold_pct}% threshold")
        if warnings:
            _warn("; ".join(warnings))
        return 0
    reason = f"{lib.describe(measure)} < {threshold_pct}% threshold"
    if released_by_handoff:  # the PreToolUse hook released this very command
        _warn(f"{reason}; released by the logged override the Claude Code hook already used")
        return 0
    released, why_not = override.try_release(root, HOOK)
    if released is not None:
        print(override.notice(HOOK, released, reason), file=sys.stderr)
        return 0
    if measure["kind"] == "requirements":
        uncovered = measure["coverage"]["uncovered_requirements"]
        listing = f"uncovered requirements: {', '.join(map(str, uncovered[:15]))}" if uncovered else ""
    else:
        listing = ""
    advice = "\n".join(filter(None, [handoff_why, why_not, override.instruction(root, HOOK)]))
    print("\n".join(filter(None, [
        f"BLOCKED ({HOOK}, git pre-commit): {reason}", listing,
        "Measured on the manifest staged for THIS commit. Stage the corrected manifest, "
        "or follow the override below.", advice,
        *(["WARN: " + "; ".join(warnings)] if warnings else [])])), file=sys.stderr)
    return BLOCK


def main() -> int:
    """Fail-open: a crash in this step is a WARN, never a blocked commit."""
    for stream in (sys.stdout, sys.stderr):  # a cp1252 pipe must not turn a block into a crash
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    try:
        return check()
    except Exception as exc:  # noqa: BLE001 - a broken gate must say so, then allow
        _warn(f"coverage measurement failed ({type(exc).__name__}: {str(exc)[:160]}); "
              "the commit gate is NOT evaluating")
        return 0


if __name__ == "__main__":
    sys.exit(main())
