"""The catalog's side of the S6/S7 bargain (campaign S7).

Three claims the requirements catalog makes about itself, each asserted against
the file rather than trusted:

1. It names a command a reader can run, and **that command runs**.
2. It no longer promises coverage the event log does not have.
3. It no longer carries the run ids D4 moved out of the requirement text.

Split from ``test_fr_change_history_recovers_compacted_history.py`` (which
compares the QUERY against the recovered history) to keep both modules under the
size limit. Claim 1 is the sole coverage of acceptance criterion 4, and a
scripted de-duplication already deleted it once without reddening anything —
which is why it is executed unconditionally here and may never degrade to a
skip.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

from _fr_history_recovered_history import (  # noqa: E402
    FRS as _FRS,
    NOT_IN_EVENT_LOG,
    RECOVERED_EXACT,
    RECOVERED_UNDER_ADR_ID,
)


def _catalog_text() -> str:
    return (
        _REPO / ".shipwright" / "planning" / "01-adopted" / "spec.md"
    ).read_text(encoding="utf-8")


def test_the_command_the_catalog_tells_a_reader_to_run_actually_runs():
    """The catalog names a command. A named command that no longer resolves is
    the same dead pointer as a stale ``Refined by`` block, just better hidden.

    Runs the DOCUMENTED form — ``uv run <relative path>`` from the repo root —
    rather than ``sys.executable <abs path>``. That is what the catalog tells a
    reader to type and the project's universal invocation convention; a test
    driving a different entry point proves the library imports, not that the
    instruction works.
    """
    text = _catalog_text()

    documented = "shared/scripts/tools/fr_history.py"
    assert documented in text, (
        "the catalog no longer names the change-history command; a reader is "
        "back to 'query the event log' with no way in."
    )
    assert (_REPO / documented).is_file(), (
        f"the catalog tells the reader to run {documented}, which does not exist."
    )

    # UNCONDITIONAL execution first, via the interpreter running this suite.
    # This is the assertion that may never be skipped: it is the only coverage
    # AC-4 has, and the scripted-dedup near-miss already deleted it once. A
    # `pytest.skip` here would be the same silent loss wearing a different hat —
    # a skipped test fails nothing, exactly like a deleted one.
    direct = subprocess.run(
        [sys.executable, str(_REPO / documented), "FR-01.11",
         "--project-root", str(_REPO)],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert direct.returncode == 0, (
        f"the documented script failed (exit {direct.returncode}): {direct.stderr}"
    )
    assert "FR-01.11" in direct.stdout

    # Then the DOCUMENTED form verbatim — `uv run <relative path>` from the repo
    # root, which is what the catalog tells a reader to type. Missing `uv` is a
    # HARD failure, not a skip: `uv run` is the project's universal invocation
    # convention, so its absence means the environment cannot run any Shipwright
    # instruction, which is worth a red rather than a shrug.
    #
    # Timeout is load-bearing: a nested `uv run` can block on the project venv
    # lock, and it may resync `.venv` mid-suite — under the parallel F0 runner
    # that is a realistic hang rather than a theoretical one.
    assert shutil.which("uv"), (
        "uv is not on PATH, so the command the catalog documents cannot be run "
        "as written. Failing rather than skipping: this is the only check that "
        "the documented instruction works."
    )
    documented_run = subprocess.run(
        ["uv", "run", documented, "FR-01.11"],
        cwd=_REPO, capture_output=True, text=True, encoding="utf-8", timeout=600,
    )
    assert documented_run.returncode == 0, (
        f"`uv run {documented} FR-01.11` failed (exit "
        f"{documented_run.returncode}): {documented_run.stderr}"
    )
    assert "FR-01.11" in documented_run.stdout


def test_the_catalog_does_not_promise_coverage_the_log_does_not_have():
    """S6 wrote that *every* completed change records the requirements it
    touched. Measured against this repo's own log that is false — a minority do.

    This asserts the catalog no longer carries the overclaim. It is here rather
    than in a docs lint because the fact it guards is measured by this module.
    """
    text = _catalog_text()
    assert "Every completed change records the requirements" not in text, (
        "the catalog claims complete FR coverage of the event log; the measured "
        "share is a minority of recorded changes."
    )


def test_the_catalog_no_longer_carries_the_run_ids_it_delegated_away():
    """S6's side of the bargain: the prose really is gone.

    Without this, 'the query returns them' would be compatible with the catalog
    still carrying them too — and the compaction would be unproven.
    """
    text = _catalog_text()
    every_expected = {
        run_id
        for table in (RECOVERED_EXACT, RECOVERED_UNDER_ADR_ID, NOT_IN_EVENT_LOG)
        for fr in _FRS
        for run_id in table[fr]
    }
    still_there = sorted(r for r in every_expected if r in text)
    assert not still_there, (
        f"the catalog still names run id(s) {still_there}; D4 moved change "
        f"history out of the requirement text."
    )
