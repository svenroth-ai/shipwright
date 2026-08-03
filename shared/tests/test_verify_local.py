"""`scripts/verify_local.py` — the wrapper's own behaviour.

The ci.yml drift contract (does the registry still describe the real merge gates?) is
the other half, split into `test_verify_local_ci_drift.py` to keep both under the
300-line budget.

Two properties matter here and neither is obvious from reading the code:

1. **Every gate runs even when an earlier one fails.** Short-circuiting would turn one
   red CI run into three sequential local runs, which is the round-trip tail this tool
   exists to remove.
2. **The gates are driven as subprocesses, never imported.**
   `check_ci_gate_coverage.py` mutates `sys.path` and does an eager
   `from lib.ci_gate_allowlist import ...` at module scope. Importing it into this
   process — eagerly OR lazily — binds `lib` for the whole interpreter and resolves
   differently under the plugin-vs-shared root split: green at F0, red in CI.
   `test_verify_local_imports_only_the_standard_library` is what keeps it that way.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERIFY_LOCAL = _REPO_ROOT / "scripts" / "verify_local.py"


def _load_subject(name: str = "_verify_local_probe"):
    """Load the subject by path, never via `sys.path` (ADR-045).

    A `sys.path` entry binds `scripts/`'s top-level names for the whole pytest process.
    This module's entire subject is "do not bind repo modules by path", so doing it here
    would be the one place its practice diverges from its doctrine. Same loader
    `verify_contract_surface.py` and `test_checks_that_gate.py` use.
    """
    spec = importlib.util.spec_from_file_location(name, _VERIFY_LOCAL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # register BEFORE exec — ADR-045
    spec.loader.exec_module(module)
    return module


verify_local = _load_subject()


# --------------------------------------------------------------------------- #
# ADR-045: the gates are driven, never imported
# --------------------------------------------------------------------------- #
def test_verify_local_imports_only_the_standard_library() -> None:
    """Eagerly or lazily importing a checker is equally unsafe.

    Deferring the import into a function only defers WHICH `lib` binds; it does not make
    it safe. `ast.walk` covers nested scopes on purpose, so a function-local import
    fails this too.

    Tested against the real stdlib set, not a hand-listed one: an enumeration of today's
    imports would fail on a future `import json` while blaming ADR-045, sending the next
    maintainer after a violation that is not there.

    Scope, stated so it is not over-read: this proves no *static, absolute* non-stdlib
    import. A relative import (`level > 0`) or a dynamic `importlib.import_module("lib.x")`
    would slip past. Neither is reachable from `scripts/`, which is not a package, and
    the module is a hundred-odd lines of plainly-subprocess code — so the gap is
    recorded rather than closed.
    """
    tree = ast.parse(_VERIFY_LOCAL.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    foreign = imported - sys.stdlib_module_names - {"__future__"}
    assert not foreign, (
        f"scripts/verify_local.py imports {sorted(foreign)}. The three checkers must be "
        f"driven as subprocesses, never imported (ADR-045)."
    )


# --------------------------------------------------------------------------- #
# Aggregation behaviour
# --------------------------------------------------------------------------- #
def _fake(**codes: int):
    """A runner returning a canned exit code per script stem, keyed off the real Gate.

    Matched against `LOCAL_GATES` rather than a magic argv index: if `Gate.command` ever
    grows a prefix, this raises at the seam instead of quietly reporting every gate as
    passing.
    """
    calls: list[str] = []

    def runner(command: list[str], root: Path) -> tuple[int, str]:
        gate = next((g for g in verify_local.LOCAL_GATES if g.command == command), None)
        if gate is None:
            raise AssertionError(f"unrecognised gate command {command!r} — the runner "
                                 f"seam no longer matches Gate.command")
        stem = Path(gate.script).stem
        calls.append(stem)
        return codes.get(stem, 0), f"output of {stem}"

    return runner, calls


def test_every_gate_runs_even_when_an_earlier_one_fails(capsys) -> None:
    """One push should fix everything CI would reject, not the first thing only."""
    runner, calls = _fake(check_ci_gate_coverage=1)
    verify_local.verify(runner=runner)
    capsys.readouterr()
    assert calls == [Path(g.script).stem for g in verify_local.LOCAL_GATES], (
        f"only {calls} ran — a failing gate aborted the rest"
    )


def test_exit_code_is_zero_when_every_gate_passes(capsys) -> None:
    runner, _ = _fake()
    assert verify_local.verify(runner=runner) == 0
    assert "PASS — all 3 mirrored gates green." in capsys.readouterr().out


def test_exit_code_is_nonzero_when_any_gate_fails(capsys) -> None:
    runner, _ = _fake(verify_sweep_delivery_surface=1)
    assert verify_local.verify(runner=runner) != 0
    capsys.readouterr()


def test_the_failing_gate_is_named_and_its_output_shown(capsys) -> None:
    """A verdict without the child's output sends the operator back to re-run it by
    hand — the summary must be enough to start diagnosing."""
    runner, _ = _fake(verify_sweep_delivery_surface=1)
    verify_local.verify(runner=runner)

    text = capsys.readouterr().out
    assert "FAIL  Sweep delivery surface (gate)" in text
    assert "output of verify_sweep_delivery_surface" in text
    assert "PASS  Contract surface (gate)" in text, "passing gates are not reported either"
    assert "CI remains the authority" in text, "the non-substitution note is missing"


def test_the_run_names_the_tree_it_vetted(capsys) -> None:
    """The gates read the working tree; CI reads the pushed commit.

    Without the header, a fix left unstaged is vetted here, never pushed, and CI fails
    on the very gate the operator watched go green. Naming the subject is what makes
    that divergence visible.
    """
    runner, _ = _fake()
    verify_local.verify(runner=runner)
    assert "Verifying:" in capsys.readouterr().out


def test_the_header_distinguishes_a_clean_tree_from_a_dirty_one(tmp_path) -> None:
    """Built on a throwaway repo, never on the repo under test.

    Asserting against `_REPO_ROOT` would pass while developing (tree dirty) and fail in
    CI (clean checkout) — a test whose verdict depends on who is running it. Both
    branches are exercised here on a tree this test owns.
    """
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True,
                       check=False)

    git("init", "-b", "main")
    git("config", "user.email", "probe@test.invalid")
    git("config", "user.name", "Probe")
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "seed")

    clean = verify_local.describe_tree(tmp_path)
    assert "clean" in clean and "uncommitted" not in clean, clean

    (tmp_path / "seed.txt").write_text("changed\n", encoding="utf-8")
    dirty = verify_local.describe_tree(tmp_path)
    assert "1 uncommitted change(s)" in dirty, dirty
    assert "WORKING TREE" in dirty, "the dirty branch must say what CI reads instead"


# --------------------------------------------------------------------------- #
# The real runner — the one piece the injected-runner tests never exercise
# --------------------------------------------------------------------------- #
def test_the_real_runner_is_the_one_verify_uses_by_default() -> None:
    """The seam decomposition leaves open.

    Every other behaviour test injects a fake runner, and the real runner is exercised
    only in isolation. If `verify`'s default were ever rebound to a stub, all of them
    would still pass while the entry point ran nothing. Nothing else pins the join.
    """
    default = inspect.signature(verify_local.verify).parameters["runner"].default
    assert default is verify_local.run_command, (
        f"verify()'s default runner is {default!r}, not run_command — the entry point "
        f"no longer drives real subprocesses"
    )


def test_children_are_given_a_utf8_environment() -> None:
    """Asserted by reading the child's env, not by round-tripping a character.

    A round-trip passes on CI's UTF-8 Linux whether or not this is set, so it cannot
    falsify the Windows-only defect the setting exists for. Reading `PYTHONUTF8` back
    out of the child is deterministic on every platform.
    """
    code, output = verify_local.run_command(
        [sys.executable, "-c", "import os; print(os.environ.get('PYTHONUTF8'))"],
        _REPO_ROOT,
    )
    assert code == 0 and output.strip() == "1", (
        f"children do not see PYTHONUTF8=1 ({output!r}); on a Windows host a gate that "
        f"decodes its own child with the locale codec can die on valid UTF-8"
    )


def test_the_subprocess_runner_reports_the_child_exit_code_and_output() -> None:
    code, output = verify_local.run_command(
        [sys.executable, "-c", "print('from the child'); raise SystemExit(3)"],
        _REPO_ROOT,
    )
    assert code == 3
    assert "from the child" in output


def test_the_subprocess_runner_round_trips_non_ascii_child_output() -> None:
    """All three checkers emit non-ASCII (the surface verifiers print arrows, the
    CI-gate guard prints em-dashes), and only two reconfigure their own stdio. A child
    writing to a PIPE encodes with the locale codec, so on a Windows cp1252 host those
    characters arrive as bytes a UTF-8 decode renders U+FFFD — mojibake in exactly the
    diagnostic the operator needs. Asserting the ASCII half would pin nothing.
    """
    code, output = verify_local.run_command(
        [sys.executable, "-c", "print('grade.py → schema_version 1 — ok')"],
        _REPO_ROOT,
    )
    assert code == 0
    assert "→" in output and "—" in output, (
        f"non-ASCII did not survive the subprocess round-trip: {output!r}"
    )
