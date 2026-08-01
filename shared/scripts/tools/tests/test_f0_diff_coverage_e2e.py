"""F0 diff-coverage gate, end to end against the REAL pinned diff-cover.

`test_suite_coverage.py` proves the decisions; this proves the chain: real
coverage data -> the real `combine_coverage.py` remap -> the real
`uvx diff-cover@<pin>`. Without it the gate is only asserted against fakes, and
the failure this whole change exists to prevent is exactly "a gate that looked
wired and measured nothing".

The load-bearing assertion is the plugin **remap**. A plugin unit runs
`cd plugins/<name>` and records `scripts/m.py`, while git calls the same file
`plugins/<name>/scripts/m.py`. If the remap were dropped, diff-cover would find
no coverage information for that file, silently EXCLUDE it from the denominator,
and report a comfortable pass over whatever was left. That is a false green, not
a failure, so nothing else in the suite would notice.

Skipped locally when git/uv are unavailable; HARD-FAILS in CI (silent-skip
CI-discipline rule), because an empirical proof that quietly stops running is
worth less than no proof at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_SHARED))

from scripts.tools.suite_coverage import (
    COVERAGE_XML,
    DATA_DIR,
    GATE_FAILED,
    GATE_PASSED,
    run_gate,
)
from scripts.tools.suite_units import UV_RUN

_HAS_GIT = shutil.which("git") is not None
_HAS_UV = shutil.which("uv") is not None
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}
#: The four modules `combine_coverage.py` needs to run standalone in a synthetic
#: repo. Copied rather than stubbed: the point is to exercise the REAL combiner.
_COMBINER_FILES = (
    "scripts/lib/atomic_write.py",
    "scripts/lib/diff_coverage_gate.py",
    "scripts/tools/measure_diff_coverage.py",
    "scripts/tools/combine_coverage.py",
)
_PLUGIN = "p1"


def _require_real_tools() -> None:
    if _HAS_GIT and _HAS_UV:
        return
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("git/uv unavailable in CI — the F0 diff-coverage gate cannot "
                    "be proven to bite; fix the runner image, do not skip this.")
    pytest.skip("git or uv unavailable")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), env=_GIT_ENV,
                   capture_output=True, text=True, check=True)


def _uv(cwd: Path, code: str, env: dict) -> None:
    subprocess.run([*UV_RUN, "--with", "coverage", "python", "-c", code],
                   cwd=str(cwd), env=env, capture_output=True, text=True, check=True)


def _expected(root: Path) -> list[str]:
    """The data files `_measure` was told to write — what `run_suite` hands the gate."""
    return [str(root / DATA_DIR / f".coverage.{label}") for label in (_PLUGIN, "shared")]


def _cov_env(root: Path, label: str) -> dict:
    return {**_GIT_ENV,
            "COVERAGE_FILE": str(root / DATA_DIR / f".coverage.{label}"),
            "COVERAGE_RCFILE": str(root / ".coveragerc")}


def _measure(root: Path, *, call_b: bool) -> None:
    """Produce the per-tier data files the way F0 does — BOTH tiers, because they
    behave differently at combine time and getting either wrong is equally silent:

    * a plugin unit runs from `plugins/<name>` and records `scripts/...`, which the
      combiner must REMAP onto `plugins/<name>/scripts/...`;
    * the shared tier runs from the repo root and already records `shared/...`,
      which the combiner must leave ALONE.
    """
    shutil.rmtree(root / DATA_DIR, ignore_errors=True)
    (root / DATA_DIR).mkdir(exist_ok=True)
    calls = "m.a();" + ("m.b();" if call_b else "")
    _uv(root / "plugins" / _PLUGIN,
        "import coverage,sys;c=coverage.Coverage(source=['scripts']);c.start();"
        f"sys.path.insert(0,'scripts');import m;{calls}c.stop();c.save()",
        _cov_env(root, _PLUGIN))
    _uv(root,
        "import coverage,sys;c=coverage.Coverage(source=['shared']);c.start();"
        "sys.path.insert(0,'shared');import s;s.hello();c.stop();c.save()",
        _cov_env(root, "shared"))


def _synth_repo(root: Path) -> None:
    """A repo with a REAL `origin/main` remote-tracking ref (bare remote -> push
    -> fetch). diff-cover diffs `origin/main...HEAD`, so a base that only exists
    as a local branch would not exercise the same code path the gate uses."""
    src = root / "plugins" / _PLUGIN / "scripts"
    src.mkdir(parents=True)
    (root / ".coveragerc").write_text(
        "[run]\nrelative_files = true\n", encoding="utf-8")
    for rel in _COMBINER_FILES:
        dst = root / "shared" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SHARED / rel, dst)
    (src / "m.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    # The shared tier: recorded repo-relative already, so it must survive combine
    # UNCHANGED. Unmodified by the diff below, so it never affects the verdict —
    # it is here to prove the non-remapped half of the rule, not to move the number.
    (root / "shared" / "s.py").write_text(
        "def hello():\n    return 'hi'\n", encoding="utf-8")

    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")

    bare = root.parent / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)],
                   env=_GIT_ENV, capture_output=True, check=True)
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-q", "origin", "main")
    _git(root, "fetch", "-q", "origin", "main")

    # The change under test: `b()` is new, and whether it is covered is the
    # variable the two tests below flip.
    (src / "m.py").write_text(
        "def a():\n    return 1\n\n\ndef b():\n    return 2\n", encoding="utf-8")
    _git(root, "checkout", "-q", "-b", "feature")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "add b")


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    """Built ONCE: the git setup is ~10 subprocesses and this module sits on F0's
    critical path in a test root that is deliberately not xdist-allowlisted. Safe to
    share because `_measure` clears `.cov-data` and `run_gate` rewrites
    `coverage.xml`, so no test inherits another's measurement."""
    _require_real_tools()
    root = tmp_path_factory.mktemp("e2e") / "repo"
    root.mkdir()
    _synth_repo(root)
    return root


def test_an_uncovered_changed_line_fails_the_gate(repo, capsys):
    """AC-8, fail half. `b()` is added and never executed: its changed lines are
    measured at 0%, which is below the threshold."""
    _measure(repo, call_b=False)
    res = run_gate(repo, expected=_expected(repo), suite_green=True,
                   branch="origin/main")
    assert res.exit_code == GATE_FAILED, "\n".join(res.lines)
    assert any("FAILED" in line for line in res.lines)


def test_covering_the_changed_line_passes_the_gate(repo):
    """AC-8, pass half. Same diff, same command — only the coverage differs, which
    is what makes the fail above attributable to coverage and not to setup."""
    _measure(repo, call_b=True)
    res = run_gate(repo, expected=_expected(repo), suite_green=True,
                   branch="origin/main")
    assert res.exit_code == GATE_PASSED, "\n".join(res.lines)


def test_the_combined_xml_is_repo_relative_so_diff_cover_can_match_it(repo):
    """AC-1 / O4. Assert the ARTIFACT, not the flags: the plugin's CWD-relative
    `scripts/m.py` must come back as `plugins/p1/scripts/m.py`. A bare
    `scripts/m.py` here would mean diff-cover silently measures nothing for every
    plugin — a false green no other test would catch."""
    _measure(repo, call_b=False)
    run_gate(repo, expected=_expected(repo), suite_green=True, branch="origin/main")
    xml = (repo / COVERAGE_XML).read_text(encoding="utf-8")
    assert f'filename="plugins/{_PLUGIN}/scripts/m.py"' in xml, xml[:900]
    # ...and the tier that must NOT be remapped survives in the same combined XML,
    # which also proves the two tiers were unioned rather than one overwriting the
    # other (AC-6). Asserted separately because a combiner that remapped everything
    # and one that remapped nothing would each satisfy only one of these.
    assert 'filename="shared/s.py"' in xml, xml[:900]


def test_a_missing_compare_ref_fails_closed_rather_than_crashing(tmp_path):
    """AC-4d: an unresolvable base must STOP with an actionable message, never pass
    and never raise. Takes no repo — it refuses before touching git at all, and
    building one would only slow F0 down."""
    res = run_gate(tmp_path, expected=["x"], suite_green=True, branch=None)
    assert res.exit_code == GATE_FAILED
    assert any("git fetch" in line for line in res.lines)
