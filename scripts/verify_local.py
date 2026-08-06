#!/usr/bin/env python3
"""Run the merge gates that exist only in CI — before you push.

SHIPWRIGHT_MIRRORED_MERGE_GATES — identity marker, load-bearing. F0's step greps
for this token instead of testing that a file exists at this path; see below.

    uv run scripts/verify_local.py

`ci.yml`'s required job runs three bespoke guards that nothing runs locally: the
CI-gate guard, and the two surface verifiers. They fail for real — 2 of 22 CI failures
sampled over 3.4 days were `Sweep delivery surface (gate)`. The cost of learning that
from CI is not the runtime; it is that the failure lands *after* the iterate reports
done, so the PR hangs and someone re-enters the next day to diagnose, fix and re-push.

**This does not replace CI, and a pass here is not a pass there** (FR-01.17). CI checks
a clean checkout with a pinned interpreter, and one of its gates materialises its
checker from the PR's *base* revision — none of which a branch can do to itself. This
is a pre-flight that removes the common, boring reasons a push comes back red.

Exit 0 = every mirrored gate passed. Non-zero = CI would reject this push, and the
gate that would reject it is named.

**F0 runs this** — `plugins/shipwright-iterate/skills/iterate/references/F0.md`, right
after the leak-guard and before the test suite. That step greps this docstring for the
marker token ``SHIPWRIGHT_MIRRORED_MERGE_GATES`` rather than merely testing that a file
exists at this path, because `scripts/verify_local.py` is not a distinctive name and a
consumer project carrying one must not have it executed under STOP semantics. **Do not
remove that token**; without it the step silently stops running here.

It covers the F0→push window only as far as F0 can see: eight phases write tracked
artifacts after it (F0.5/F3/F3a/F4/F5/F5a/F5b/F5c), and F11's `ensure_current` merges
`origin/main` before the push, so the commit CI judges is not the tree these gates
read. That residue is real and tracked; F0 is the cheap early catch, not a proof.
That placement was the operator's decision on trg-486cb11c;
a blocking pre-push hook was rejected because these gates read the WORKING TREE, and
F0 is the one moment the tree is what becomes the commit (see `describe_tree`). Typing
it yourself stays valid and is still the way to check a tree outside an iterate run.

**The gates are driven as subprocesses, never imported.** `check_ci_gate_coverage.py`
mutates `sys.path` and does an eager `from lib.ci_gate_allowlist import ...` at module
scope; importing it here would bind `lib` for this whole interpreter, and under the
plugin-vs-shared root split that name resolves to a different directory depending on
what loaded first — green locally, red in CI (ADR-045). Deferring the import into a
function only defers *which* `lib` binds; it does not make it safe. Driving each gate
the way `ci.yml` drives it is both the safe shape and the faithful one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

#: Outer bound, not a performance budget. `verify_contract_surface.py` alone allows its
#: two children 900 s + 600 s, so anything tighter would cut off a legitimately slow
#: gate. It bounds `uv`, not `uv`'s descendants — see `run_command` for what that does
#: and does not guarantee.
_TIMEOUT_SECONDS = 1800

#: ``(command, root) -> (exit_code, combined output)``. Injected by the tests so they can
#: assert the aggregation contract without paying for three real gates.
Runner = Callable[[list[str], Path], "tuple[int, str]"]


@dataclass(frozen=True)
class Gate:
    """One `ci.yml` guard step, mirrored locally.

    ``step`` is the ci.yml step name verbatim — it is the join key the drift tests use
    to prove this registry still describes the real merge gate.
    """

    step: str
    script: str
    args: tuple[str, ...] = ()

    @property
    def command(self) -> list[str]:
        return ["uv", "run", self.script, *self.args]


#: Mirrored locally. Each command must appear in `ci.yml` as a whole line, not merely as
#: a substring of one: the per-gate forward-drift test in
#: `shared/tests/test_verify_local_ci_drift.py` compares against the step's executable lines, so
#: CI growing a flag this wrapper does not pass fails there instead of silently letting
#: this report PASS on a push CI rejects.
LOCAL_GATES = (
    Gate("Run CI-gate guard", "shared/scripts/tools/check_ci_gate_coverage.py",
         ("--project-root", ".")),
    Gate("Contract surface (gate)", "scripts/verify_contract_surface.py"),
    Gate("Sweep delivery surface (gate)", "scripts/verify_sweep_delivery_surface.py"),
)

#: NOT mirrored, with the reason. Recorded rather than dropped so this tool cannot
#: quietly claim more coverage than it has — a silently incomplete pre-flight is worse
#: than none, because it is trusted. The reverse-drift test fails on the next ci.yml
#: guard that lands in neither registry (`shared/tests/test_verify_local_ci_drift.py`).
CI_ONLY_GATES = {
    "Repair-PR safety (gate)": (
        "Materialises the checker from the PR's BASE revision, not the head, precisely "
        "so a branch cannot vouch for itself. Whether a branch weakened the checker is "
        "unanswerable from inside that branch — this one is structural, not a to-do."
    ),
    "Diff coverage (gate)": (
        "DEFERRED, not structural — tracked as trg-392dc923. Needs a cobertura run per "
        "test root, combined, then diff-cover against the merge-base, which belongs in "
        "the F0 suite runner that already produces coverage rather than in this "
        "wrapper. Cited by triage id on purpose: a reason that names a card no one can "
        "look up reads as accountable without being so."
    ),
}


def describe_tree(root: Path) -> str:
    """One line naming what is actually being vetted.

    The gates read the **working tree**; CI reads the commit you **push**. That is the
    divergence this tool most plausibly hides: fix `ci.yml`, watch the gate go green,
    then commit only some paths, and the fix never leaves the machine while CI fails on
    exactly the gate you just watched pass. The inverse costs credibility too — an
    untracked scratch test dir reddens the CI-gate guard locally while CI is green.
    Naming the subject turns a silent divergence into a visible one.
    """
    def git(*args: str) -> str:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False,
            )
        except OSError:  # pragma: no cover - git absent
            return ""
        return done.stdout.strip() if done.returncode == 0 else ""

    head = git("rev-parse", "--short=12", "HEAD") or "unknown"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    dirty = len([ln for ln in git("status", "--porcelain").splitlines() if ln.strip()])
    if dirty:
        return (f"{branch} @ {head} — {dirty} uncommitted change(s). These gates read "
                f"the WORKING TREE; CI reads what you PUSH.")
    return f"{branch} @ {head} — clean"


def run_command(command: list[str], root: Path) -> tuple[int, str]:
    """Run one gate and return ``(exit_code, combined output)``.

    ``PYTHONUTF8`` is forced rather than trusted. A child writing to a *pipe* encodes
    with the locale codec, so on a Windows cp1252 host the em-dashes in
    `check_ci_gate_coverage.py`'s failure text arrive as bytes this UTF-8 decode renders
    U+FFFD. ``PYTHONIOENCODING`` alone would not be enough: it rebinds only the std
    streams, while `verify_contract_surface.py` decodes *its* children with
    ``subprocess.run(..., text=True)`` and no ``encoding=``, which follows
    ``locale.getpreferredencoding()`` — that path raises UnicodeDecodeError on the
    undefined cp1252 slots and kills the gate for a reason that is not a defect, green
    on CI's UTF-8 Linux the whole time. ``PYTHONUTF8=1`` covers the std streams,
    ``open()`` defaults and the locale for the entire subtree, so a Windows run matches
    CI rather than merely being readable. It is a no-op on CI, whose locale is already
    UTF-8.

    ``CI`` is deliberately NOT set. Some gates branch on it —
    `verify_sweep_delivery_surface.py` strips it from its own child because
    `sweep_outbox_to_branch` refuses to auto-commit under CI — and forcing it here would
    make this wrapper's environment lie to every future gate about where it is running.

    The timeout bounds `uv` itself, not its descendants: on Windows `subprocess.run`
    kills only the direct child and then waits on pipes the grandchildren still hold, so
    a gate hung *below* `uv` can still wait indefinitely. It is an outer bound against
    the common case, not a guarantee.
    """
    try:
        done = subprocess.run(
            command, cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return 1, (
            f"TIMEOUT after {_TIMEOUT_SECONDS}s. Output is buffered until a gate "
            f"finishes, so this cannot tell you where it stopped — run it directly:\n"
            f"    {' '.join(command)}"
        )
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def verify(root: Path = _ROOT, gates: tuple[Gate, ...] = LOCAL_GATES,
           runner: Runner = run_command) -> int:
    """Run every gate, report each, return the process exit code.

    Every gate runs even when an earlier one fails. Short-circuiting would turn one red
    CI run into three sequential local runs, which is the round-trip tail this exists to
    remove: the operator should get ONE list of what CI would reject.
    """
    print(f"Verifying: {describe_tree(root)}")
    failed: list[Gate] = []
    for gate in gates:
        print(f"\n=== {gate.step} ===")
        print(f"    $ {' '.join(gate.command)}")
        code, output = runner(gate.command, root)
        if output.strip():
            print(output.rstrip())
        if code == 0:
            print(f"PASS  {gate.step}")
        else:
            failed.append(gate)
            print(f"FAIL  {gate.step} (exit {code})")

    print("\n" + "=" * 72)
    if failed:
        print(f"FAIL — {len(failed)} of {len(gates)} mirrored gates would block this push:")
        for gate in failed:
            print(f"  - {gate.step}")
    else:
        print(f"PASS — all {len(gates)} mirrored gates green.")
    if CI_ONLY_GATES:
        print(f"NOTE  {len(CI_ONLY_GATES)} CI gate(s) not mirrored here "
              f"({', '.join(sorted(CI_ONLY_GATES))}); CI remains the authority.")
    print("=" * 72)
    return 1 if failed else 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - defensive
                pass
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
