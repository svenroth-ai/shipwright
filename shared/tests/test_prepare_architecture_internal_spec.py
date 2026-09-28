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


def _run(tmp_path: Path, spec_text: str) -> int:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(spec_text, encoding="utf-8")
    return pais.main([
        "--project-root", str(tmp_path),
        "--run-id", "test-run",
        "--spec-file", str(spec_path),
    ])


def test_writes_a_sanitized_copy_stripped_of_the_prior_review_section(tmp_path: Path, capsys) -> None:
    rc = _run(tmp_path, _SPEC_WITH_PRIOR_REVIEW)
    assert rc == 0

    out_path = tmp_path / ".shipwright" / "runs" / "test-run" / "architecture-internal-spec.md"
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
    assert (tmp_path / ".shipwright" / "runs" / "test-run").is_dir()


def test_a_clean_spec_with_no_prior_review_section_passes_through_unchanged(tmp_path: Path) -> None:
    clean = "# Some Spec\n\n## Acceptance Criteria\n- AC1: it works.\n"
    rc = _run(tmp_path, clean)
    assert rc == 0
    out_path = tmp_path / ".shipwright" / "runs" / "test-run" / "architecture-internal-spec.md"
    assert out_path.read_text(encoding="utf-8") == clean
