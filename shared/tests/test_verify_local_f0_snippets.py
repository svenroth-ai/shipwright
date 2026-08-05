"""F0's mirrored-merge-gate snippet is EXECUTED here, not pattern-matched.

@FR-01.17

Split from `test_verify_local_f0_wiring.py`, which asserts what `F0.md` *says*
(anchor drift, ordering, the honesty of the surrounding claims). This file
asserts what it *does*. The split is not only about the 300-line budget: an
external reviewer pointed out that every content assertion in the sibling file is
satisfied by a block containing the string `verify_local.py`, so
`echo scripts/verify_local.py` would have passed all of them while running
nothing — which is the exact failure the whole change exists to end. Text
assertions cannot close that; running the snippet can.

Only the POSIX spelling is executed. `bash` is present on the `ubuntu-latest`
runner CI uses and via Git-Bash locally, so the coverage is real; the PowerShell
spelling's equivalence is pinned structurally in the sibling file instead. Both
guards follow the repo's silent-skip CI rule: hard-fail under CI, skip locally
with an actionable hint.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_F0 = (
    _REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "F0.md"
)

#: The identity marker F0's guard greps for. A stub gate must carry it or the
#: guard correctly declines to run it — which is itself worth testing.
MARKER = "SHIPWRIGHT_MIRRORED_MERGE_GATES"


def _bash_snippet() -> str:
    """The POSIX block from F0.md, ready to execute."""
    for shell, body in re.findall(
        r"```([a-zA-Z]*)\n(.*?)```", _F0.read_text(encoding="utf-8"), re.DOTALL
    ):
        if shell == "bash" and "verify_local.py" in body:
            return body
    raise AssertionError("no bash block in F0.md runs verify_local.py")


def _require(binary: str) -> None:
    if shutil.which(binary) is not None:
        return
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail(
            f"`{binary}` is required in CI to execute F0's POSIX snippet "
            f"(ubuntu-latest ships it; this is a provisioning fault, not a skip)."
        )
    pytest.skip(f"`{binary}` not on PATH — run this suite from Git-Bash to cover it")


def _run_snippet(project: Path) -> subprocess.CompletedProcess:
    snippet = _bash_snippet().replace("{project_root}", str(project).replace("\\", "/"))
    return subprocess.run(
        ["bash", "-c", snippet], capture_output=True, timeout=300, check=False,
    )


def _stub_gate(project: Path, *, exit_code: int, marker: bool = True) -> None:
    scripts = project / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    head = f'"""{MARKER} — stub."""\n' if marker else '"""stub."""\n'
    (scripts / "verify_local.py").write_text(
        f"{head}import sys\nsys.exit({exit_code})\n", encoding="utf-8"
    )


def test_it_no_ops_where_there_is_no_gate(tmp_path) -> None:
    """AC-2, executed rather than pattern-matched — the consumer-project case."""
    _require("bash")
    done = _run_snippet(tmp_path)
    assert done.returncode == 0, (
        f"the guarded block failed in a project without the script: "
        f"{done.stderr.decode('utf-8', 'replace')}"
    )


def test_it_declines_a_foreign_script_at_the_same_path(tmp_path) -> None:
    """The guard is on IDENTITY, not on a path.

    `scripts/verify_local.py` is not a distinctive name. Guarding on existence
    alone would let a consumer project's own file be executed by an agent, from a
    prompt Shipwright ships, under "non-zero = STOP" — halting the user's run on a
    foreign script's exit code. Here the stub deliberately omits the marker and
    exits non-zero: the step must not run it, so the block must still succeed.
    """
    _require("bash")
    _stub_gate(tmp_path, exit_code=9, marker=False)
    done = _run_snippet(tmp_path)
    assert done.returncode == 0, (
        "a script at the right path but WITHOUT the Shipwright marker was "
        "executed, and its exit code would now stop an unrelated project's run"
    )


def test_it_propagates_a_failing_gate(tmp_path) -> None:
    """AC-1's "non-zero = STOP", executed.

    A block that runs the script but swallows its exit code would report the
    mirrored merge gates as passing on a push CI rejects — the same lie as not
    running them, arriving with more confidence.
    """
    _require("bash")
    _require("uv")
    _stub_gate(tmp_path, exit_code=3)
    done = _run_snippet(tmp_path)
    # The EXACT code, not merely non-zero: `uv` failing to start would also be
    # non-zero, so a loose assertion would pass without the gate ever running —
    # the same false green this file exists to rule out. 3 can only come from the
    # stub.
    assert done.returncode == 3, (
        f"expected the stub gate's exit 3 to reach the caller, got "
        f"{done.returncode}. If the snippet swallows it, F0 continues to F1 on a "
        f"tree CI is going to reject.\n"
        f"stderr: {done.stderr.decode('utf-8', 'replace')}"
    )


def test_it_runs_a_passing_gate(tmp_path) -> None:
    """Non-vacuity for the two above: the marker path really does execute."""
    _require("bash")
    _require("uv")
    _stub_gate(tmp_path, exit_code=0)
    done = _run_snippet(tmp_path)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
