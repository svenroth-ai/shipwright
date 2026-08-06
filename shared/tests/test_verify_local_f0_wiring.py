"""`scripts/verify_local.py` must be RUN by F0, not merely recommended in prose.

@FR-01.17

The gap this closes (P2.27 / `trg-486cb11c`): the script mirrored `ci.yml`'s three
bespoke merge guards, was fully tested, and was invoked by nothing — no hook, no skill
step, no F-phase, no workflow. `CLAUDE.md` said "run it before pushing", and agents
execute STEPS rather than CLAUDE.md prose, so the round-trip it was built to remove
survived intact.

F0 is the placement because it is where a failure is cheapest — before the commit
exists, so the fix is an edit rather than an amend plus a retracted push.

It does NOT close the gap the script documents about itself ("these gates read the
WORKING TREE; CI reads what you PUSH"). Eight phases write tracked artifacts after
F0, and F11's `ensure_current` merges `origin/<default>` before the push, so the
commit CI judges is not the tree these gates read. An earlier version of this
docstring claimed the divergence "closes" at F0; it does not, and the honest
statement is that F0 catches the common cases early while the F0→push window
remains.

Sibling files: `test_verify_local.py` (the wrapper's own behaviour) and
`test_verify_local_ci_drift.py` (the registry vs `ci.yml`). This one guards the WIRING,
and it is the half that regresses silently — the script keeps passing its own tests
while nothing calls it.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE_SKILL = _REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
_F0 = _ITERATE_SKILL / "references" / "F0.md"
_SKILL_MD = _ITERATE_SKILL / "SKILL.md"
_VERIFY_LOCAL = _REPO_ROOT / "scripts" / "verify_local.py"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_HOOKS_DOC = _REPO_ROOT / "docs" / "hooks-and-pipeline.md"

#: A fenced block, with its info string. F0.md uses ```bash throughout.
_FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)

#: The identity marker the real script declares in its docstring. F0's guard greps
#: for THIS rather than testing that a path exists, because `scripts/verify_local.py`
#: is not a distinctive name: a consumer project carrying one would otherwise have an
#: arbitrary local script executed by an agent under "non-zero = STOP" semantics.
MARKER = "SHIPWRIGHT_MIRRORED_MERGE_GATES"

#: A guard in any shell this repo uses. It has to live in the EXECUTABLE snippet, not
#: in the sentence next to it: an agent that follows only the code block would
#: otherwise run a file a consumer project does not have.
_FILE_GUARD = re.compile(
    r"(if\s+\[\s+-f\s|if\s+\[\[\s+-f\s|test\s+-f\s|Test-Path\s|grep\s|Select-String\s)"
)


def _f0_text() -> str:
    return _F0.read_text(encoding="utf-8")


def _blocks_mentioning_verify_local(text: str) -> list[str]:
    return [b for b in _FENCE.findall(text) if "verify_local.py" in b]


def test_f0_runs_verify_local() -> None:
    """The wiring itself. Without this the script is documentation, not a gate."""
    blocks = _blocks_mentioning_verify_local(_f0_text())
    assert blocks, (
        "F0.md never runs scripts/verify_local.py. That script mirrors ci.yml's three "
        "bespoke merge guards and nothing else invokes it, so removing this step "
        "returns the repo to learning about those failures from a red CI run AFTER the "
        "iterate reported done (P2.27 / trg-486cb11c)."
    )


def test_the_f0_step_guards_on_the_file_existing() -> None:
    """AC-2, and the correction the external plan review forced.

    The guard must be IN the snippet. A prose sentence saying "if the project has it"
    beside an unconditional command is not a guard: `verify_local.py` is monorepo-only
    (it mirrors THIS repo's ci.yml by hardcoded step name), while F0.md ships to every
    consumer project, where the command would fail for a reason that is not a defect.
    """
    blocks = _blocks_mentioning_verify_local(_f0_text())
    # Non-vacuity: with no such block every assertion below is skipped and this test
    # would report green on the exact regression `test_f0_runs_verify_local` catches.
    assert blocks, "no F0 block runs verify_local.py — nothing to guard (see AC-1)"
    for block in blocks:
        assert _FILE_GUARD.search(block), (
            "the F0 block running verify_local.py is unconditional:\n"
            f"{block}\n"
            "Guard it inside the snippet (`if [ -f ... ]`) so it no-ops where the file "
            "is absent. F0.md already branches on project shape for the suite runner; "
            "an agent following only the code block must not run a missing file."
        )


def test_the_step_is_runnable_on_the_platform_this_repo_is_developed_on() -> None:
    """A bash-only snippet is a step that does not run for half the people who reach it.

    This monorepo is developed on Windows, where the primary shell is PowerShell and
    `if [ -f ... ]; then ... fi` is a syntax error. Since the entire point of the card
    is "it runs by itself now", a spelling that cannot execute on the primary
    development platform would leave the card open while looking closed. The repo
    already ships `install-hooks.sh` beside `install-hooks.ps1` for this reason.
    """
    text = _f0_text()
    blocks = {
        info: body
        for info, body in re.findall(r"```([a-zA-Z]*)\n(.*?)```", text, re.DOTALL)
        if "verify_local.py" in body
    }
    assert "powershell" in blocks, (
        "F0's verify_local step has no PowerShell spelling. On Windows the bash "
        f"guard is a syntax error, so the step silently would not run. Found: "
        f"{sorted(blocks)}"
    )
    assert "bash" in blocks, "the POSIX spelling disappeared"


def test_the_powershell_spelling_can_actually_stop_the_run() -> None:
    """Three details, each of which silently breaks equivalence with the bash form.

    A missing `uv` must STOP, deterministically. In bash it does: the subshell
    exits 127 and the `if` carries that status. PowerShell has no equivalent —
    `CommandNotFoundException` is *statement-terminating*, so it abandons the rest
    of the `try` body and a `$LASTEXITCODE` comparison placed after the call is
    never reached. Seeding that variable first does not rescue it in any value,
    because the line that would read it does not run; whether the uncaught error
    yields a non-zero process exit is then host- and `$ErrorActionPreference`-
    dependent. Only asking whether `uv` exists BEFORE calling it is deterministic,
    which is why this asserts the precondition rather than the comparison.

    `try`/`finally` matters for the same reason the bash form uses a subshell: a
    terminating error between `Push-Location` and `Pop-Location` — including the
    throws — would strand the shell in `{project_root}`, and every later F-phase
    command using a relative path would resolve against the wrong directory.
    """
    blocks = {
        info: body
        for info, body in re.findall(r"```([a-zA-Z]*)\n(.*?)```", _f0_text(), re.DOTALL)
        if "verify_local.py" in body
    }
    ps = blocks.get("powershell", "")
    assert ps, "no PowerShell block to check"

    assert "Get-Command uv" in ps or "catch" in ps, (
        "the PowerShell block has no deterministic handling for a missing `uv`. A "
        "$LASTEXITCODE comparison does NOT cover it — CommandNotFoundException is "
        "statement-terminating, so that line never executes. Use a `Get-Command uv` "
        "precondition (or a `catch`), which is the only form a test can hold."
    )
    assert "finally" in ps and "Pop-Location" in ps, (
        "Pop-Location is not in a finally block — a throw between push and pop "
        "strands the shell in {project_root} for every later F-phase."
    )
    assert "throw" in ps, "a non-zero exit must STOP the run, not just print"

    bash = blocks.get("bash", "")
    assert "( cd " in bash, (
        "the bash block no longer uses a subshell, so it too can now leak a "
        "directory change into the rest of the phase"
    )


def test_both_snippets_actually_invoke_the_script() -> None:
    """Presence of the filename is not evidence that the script is RUN.

    Every other assertion in this file is satisfied by a block containing the
    string `verify_local.py` — `echo scripts/verify_local.py` would pass the
    wiring test, the guard test, the ordering test and the PowerShell-presence
    test while running nothing at all, which is precisely the failure this whole
    change exists to end.
    """
    for shell, body in re.findall(r"```([a-zA-Z]*)\n(.*?)```", _f0_text(), re.DOTALL):
        if "verify_local.py" not in body:
            continue
        assert "uv run scripts/verify_local.py" in body, (
            f"the {shell} block names verify_local.py but never invokes it:\n{body}"
        )


def test_the_step_precedes_the_suite() -> None:
    """Ordering is the whole point of putting an 8-second gate next to a 7-minute one.

    These guards usually fail for structural reasons an operator fixes in seconds.
    Learning that at 0:08 instead of after the full suite is the round-trip tail the
    card exists to remove. Correctness does not depend on the order — the gates read
    the working tree, which the suite does not mutate (its artefacts are gitignored) —
    so this pins the intent, which is the part that would silently erode.
    """
    text = _f0_text()
    step = text.index("verify_local.py")
    suite = text.index("## Which command")
    assert step < suite, (
        "F0 runs verify_local.py AFTER the test suite. It is ~8s against the suite's "
        "minutes, and it fails for cheap structural reasons — run it first."
    )


def test_skill_md_f0_summary_does_not_contradict_the_reference() -> None:
    """SKILL.md's inline F0 one-liner is normative too, and readers stop there.

    Leaving it at "leak-guard, then full test suite" makes the summary and the
    reference disagree about what F0 is, and the summary is the one loaded every run.
    """
    f0_line = next(
        (ln for ln in _SKILL_MD.read_text(encoding="utf-8").splitlines()
         if ln.startswith("See [F0](references/F0.md)")),
        None,
    )
    assert f0_line is not None, "SKILL.md lost its F0 one-liner — the anchor moved"
    assert "verify_local" in f0_line or "mirrored" in f0_line, (
        f"SKILL.md's F0 summary still describes F0 as leak-guard + suite only:\n"
        f"  {f0_line}\n"
        f"It now also runs the mirrored ci.yml merge gates; a summary that omits a "
        f"STOP condition is the one readers act on."
    )


def test_no_file_still_claims_verify_local_is_unwired() -> None:
    """AC-5 — the repo must not keep asserting something that is no longer true.

    Both claims were accurate when written and are load-bearing: they are why a reader
    would not go looking for the caller. Left behind, they are worse than silence,
    because they read as current and cite a triage card that is now closed.
    """
    # All THREE homes. The first draft of this test listed two and missed
    # docs/hooks-and-pipeline.md — where the claim also lived, verbatim, citing the
    # very card this change closes. The gate and the defect were the same omission,
    # which is exactly how a documentation-honesty test goes green while lying.
    stale = {
        _VERIFY_LOCAL: "Nothing invokes this for you",
        _CLAUDE_MD: "Nothing runs it for you",
        _HOOKS_DOC: "nothing invokes it for you",
    }
    for path, claim in stale.items():
        assert claim not in path.read_text(encoding="utf-8"), (
            f"{path.relative_to(_REPO_ROOT)} still says {claim!r}, but F0 now runs it. "
            f"Correct the sentence in the same change that makes it false."
        )
