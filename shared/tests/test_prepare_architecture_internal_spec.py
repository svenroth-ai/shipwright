"""`prepare_architecture_internal_spec.py` — the agent-input anchoring fix.

`architecture-internal-reviewer` has its own Read/Grep/Glob access, so a
prose "ignore prior-review sections" instruction is not a real defense: it
can simply re-read the original spec. This tool is the code-level backstop
(mirrors `strip_prior_review_sections`'s existing use in
`external_review.py`'s architecture mode) — it writes a SANITIZED COPY the
caller then hands the agent instead of the real spec path.

Calls `main()` in-process rather than via `subprocess.run` — a subprocess
invocation is invisible to the parent process's coverage instrumentation,
which would silently exempt this file's changed lines from the diff-coverage
gate (the same trap `feedback_subprocess_tests_are_invisible_to_diff_coverage`
documents).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SHARED / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import prepare_architecture_internal_spec as pais  # noqa: E402

_SPEC_WITH_PRIOR_REVIEW = """# Some Spec

## Goal
Do the thing.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Summary:** withheld rejection rationale that must never reach the
  architecture-internal-reviewer agent.

## Acceptance Criteria
- AC1: it works.
"""


_RUN_ID = "iterate-2026-01-01-test-run"


def _run(tmp_path: Path, spec_text: str, run_id: str = _RUN_ID) -> int:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(spec_text, encoding="utf-8")
    return pais.main([
        "--project-root", str(tmp_path),
        "--run-id", run_id,
        "--spec-file", str(spec_path),
    ])


def test_writes_a_sanitized_copy_stripped_of_the_prior_review_section(tmp_path: Path, capsys) -> None:
    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert rc == 0

    out_path = tmp_path / ".shipwright" / "runs" / _RUN_ID / "architecture-internal-spec.md"
    assert out_path.is_file()
    assert capsys.readouterr().out.strip() == str(out_path)

    sanitized = out_path.read_text(encoding="utf-8")
    assert "## Internal Plan Review" not in sanitized
    assert "withheld rejection rationale" not in sanitized
    assert "## Acceptance Criteria" in sanitized, "unrelated sections must survive the strip"


def test_output_location_is_the_ephemeral_gitignored_runs_dir(tmp_path: Path) -> None:
    """Same convention `surface_verification.py` uses for per-run scratch
    evidence — this copy carries nothing the committed spec.md doesn't
    already have, so it must never be a candidate for commit."""
    _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert (tmp_path / ".shipwright" / "runs" / _RUN_ID).is_dir()


def test_a_clean_spec_with_no_prior_review_section_passes_through_unchanged(tmp_path: Path) -> None:
    clean = "# Some Spec\n\n## Acceptance Criteria\n- AC1: it works.\n"
    rc = _run(tmp_path, clean)
    assert rc == 0
    out_path = tmp_path / ".shipwright" / "runs" / _RUN_ID / "architecture-internal-spec.md"
    assert out_path.read_text(encoding="utf-8") == clean


def test_a_run_id_with_path_traversal_is_refused(tmp_path: Path) -> None:
    """Stage-3 PR-review BLOCK: --run-id was joined unchecked into a
    filesystem path, so '../../somewhere' could redirect the write outside
    the intended .shipwright/runs directory."""
    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW, run_id="../../escaped")
    assert rc != 0
    assert not (tmp_path / ".shipwright").exists(), (
        "a rejected run-id must never create so much as the .shipwright dir"
    )
    assert not (tmp_path.parent / "escaped").exists(), (
        "the traversal must not have escaped to a sibling directory either"
    )


def test_a_preexisting_symlink_at_the_output_path_is_refused(tmp_path: Path) -> None:
    """Stage-3 PR-review BLOCK: a fixed, predictable output filename plus a
    plain write() follows a pre-existing symlink there, letting repository
    contents redirect the write outside .shipwright/runs. Pre-plant a
    symlink at the exact output path pointing at a victim file elsewhere,
    and confirm the victim is left untouched."""
    victim = tmp_path / "victim.txt"
    victim.write_text("do not touch", encoding="utf-8")

    runs_dir = tmp_path / ".shipwright" / "runs" / _RUN_ID
    runs_dir.mkdir(parents=True)
    try:
        (runs_dir / "architecture-internal-spec.md").symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")

    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert rc != 0
    assert victim.read_text(encoding="utf-8") == "do not touch"


def test_a_symlinked_runs_directory_is_refused(tmp_path: Path) -> None:
    """External code review BLOCK: resolving `.shipwright/runs` before checking
    containment means a symlinked runs directory (or `.shipwright` itself)
    passes the containment check trivially post-resolve — both sides of the
    comparison follow the same symlink. Pre-plant `.shipwright/runs` as a
    symlink to an outside directory and confirm nothing is written there."""
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir()
    shipwright_dir = tmp_path / ".shipwright"
    shipwright_dir.mkdir()
    try:
        (shipwright_dir / "runs").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")

    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert rc != 0
    assert list(outside.iterdir()) == [], "nothing must be written through the symlinked runs dir"


def test_a_symlinked_run_directory_is_refused(tmp_path: Path) -> None:
    """External code review round 4 (medium, `openai`): a symlink at the
    run-id-specific directory itself (`runs/{run_id}`) resolves to somewhere
    UNDER the legitimate runs root either way, so the containment check
    alone never catches it — it would silently overwrite a DIFFERENT run's
    sanitized spec. Pre-plant `runs/{run_id}` as a symlink to another run's
    directory and confirm that other run's file is untouched."""
    runs_root = tmp_path / ".shipwright" / "runs"
    other_run_dir = runs_root / "iterate-2026-01-01-other-run"
    other_run_dir.mkdir(parents=True)
    victim = other_run_dir / "architecture-internal-spec.md"
    victim.write_text("do not touch", encoding="utf-8")

    try:
        (runs_root / _RUN_ID).symlink_to(other_run_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")

    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert rc != 0
    assert victim.read_text(encoding="utf-8") == "do not touch"


def test_a_missing_spec_file_fails_cleanly_not_with_a_traceback(tmp_path: Path, capsys) -> None:
    """External code review round 5 (low, `glm`): an unreadable --spec-file
    (missing, permission error, bad encoding) must report a clean `error:`
    message and exit 1, matching every other failure path in this tool,
    rather than an unhandled traceback."""
    rc = pais.main([
        "--project-root", str(tmp_path),
        "--run-id", _RUN_ID,
        "--spec-file", str(tmp_path / "does-not-exist.md"),
    ])
    assert rc != 0
    assert "error:" in capsys.readouterr().err.lower()


def test_a_file_blocking_the_run_directory_fails_cleanly_not_with_a_traceback(
    tmp_path: Path, capsys
) -> None:
    """External code review round 6 (medium, `openai`): a filesystem failure
    creating the run directory (e.g. a plain FILE already sitting at that
    path) must report a clean `error:` message and exit 1, not an unhandled
    traceback — the iterate skill's degraded-handling path depends on a
    nonzero exit it can act on, not a crash."""
    runs_root = tmp_path / ".shipwright" / "runs"
    runs_root.mkdir(parents=True)
    (runs_root / _RUN_ID).write_text("not a directory", encoding="utf-8")

    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert rc != 0
    assert "error:" in capsys.readouterr().err.lower()


def test_a_spec_hiding_a_real_section_behind_an_unterminated_fence_is_refused(
    tmp_path: Path, capsys
) -> None:
    """External code review round 6 + local PR-review preflight (both
    converged): if strip_prior_review_sections() can't safely tell whether a
    heading behind an unterminated fence is a real prior-review section, the
    CLI must refuse cleanly (exit 1, no output file) rather than silently
    hand the agent a spec that might still carry the rationale."""
    unsafe_spec = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Notes\nAn accidental stray fence marker:\n"
        "```\n"
        "some unrelated prose\n\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y — real rationale\n"
    )
    rc = _run(tmp_path, unsafe_spec)
    assert rc != 0
    assert "error:" in capsys.readouterr().err.lower()
    assert not (tmp_path / ".shipwright" / "runs" / _RUN_ID / "architecture-internal-spec.md").exists()


def test_a_run_id_that_is_not_an_iterate_run_id_is_refused(tmp_path: Path, capsys) -> None:
    """Only /shipwright-iterate calls this tool (iteration-planning.md, step
    0b) with its own run_id, so the strict iterate-YYYY-MM-DD-slug format is
    the whole allowed universe — anything else is refused outright rather
    than merely path-cleaned, closing the class rather than one example."""
    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW, run_id="not-an-iterate-run-id")
    assert rc != 0
    assert "run-id" in capsys.readouterr().err.lower()
    assert not (tmp_path / ".shipwright").exists()
