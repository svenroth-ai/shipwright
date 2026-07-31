"""Who refreshes INDEX.md, and is the committed one current?

The renderer's own rules live in ``test_adr_index.py``. This file covers the
call sites — iterate F3, the release pass, the CLI — and the drift guard that
fails loudly when the committed index has gone stale.

The defect this pins: `aggregate_decisions.aggregate()` called
`rebuild_adr_index()` only from inside its `if rendered and not dry_run:`
branch, so the index was refreshed *only* as a side-effect of folding
decision-drops. An ADR an iterate wrote straight into the folder never reached
the index. Measured in this repo on 2026-07-31: 39 ADR files, 29 listed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.adr_index import (
    ADR_INDEX_FILENAME,
    ADR_SPEC_FOLDER,
    REGEN_COMMAND,
    REGEN_TOOL_RELPATH,
    rebuild_adr_index,
    regen_command_resolved,
    render_adr_index,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _folder(root: Path) -> Path:
    folder = root / ADR_SPEC_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _adr(root: Path, name: str, body: str) -> Path:
    path = _folder(root) / name
    path.write_text(body, encoding="utf-8")
    return path


def _regen_script() -> Path:
    """The regen tool, resolved against THIS repo's shared root.

    `REGEN_COMMAND` keeps `{shared_root}` unresolved on purpose — it is rendered
    into the committed INDEX.md of adopted repos, which have no `shared/`.
    """
    return _REPO_ROOT / "shared" / REGEN_TOOL_RELPATH


# ------------------------------------------------- the release pass (AC2)


def test_aggregate_refreshes_with_zero_drops(tmp_path):
    """Ledger 2 / AC2 — the release pass no longer needs drops to refresh."""
    from tools.aggregate_decisions import aggregate

    _adr(tmp_path, "086-x.md", "# ADR-086: X\n")
    aggregate(tmp_path)
    index = _folder(tmp_path) / ADR_INDEX_FILENAME
    assert index.is_file() and "- [ADR-086 — X]" in index.read_text(encoding="utf-8")


def test_aggregate_dry_run_writes_nothing(tmp_path):
    """Ledger 3 / AC2 — a dry run must not touch disk."""
    from tools.aggregate_decisions import aggregate

    _adr(tmp_path, "087-x.md", "# ADR-087: X\n")
    aggregate(tmp_path, dry_run=True)
    assert not (_folder(tmp_path) / ADR_INDEX_FILENAME).exists()


def test_aggregate_still_folds_drops_and_refreshes(tmp_path):
    """The original path must keep working — refresh is added, not swapped in."""
    from tools.aggregate_decisions import aggregate
    from tools.write_decision_drop import write_decision_drop

    _adr(tmp_path, "093-folded.md", "# ADR-093: Folded\n")
    write_decision_drop(
        tmp_path, run_id="iterate-2026-07-31-z", section="Iterate — change: z",
        title="T", context="c", decision="d", consequences="q",
    )
    result = aggregate(tmp_path)
    assert result["aggregated"] == 1
    index = _folder(tmp_path) / ADR_INDEX_FILENAME
    assert "- [ADR-093 — Folded]" in index.read_text(encoding="utf-8")


def test_rebuild_is_importable_from_aggregate_decisions():
    """Ledger 12 / AC8 — consumer repos already import it from there."""
    from tools.aggregate_decisions import rebuild_adr_index as re_exported

    assert re_exported is rebuild_adr_index


# ---------------------------------------------------------- iterate F3 (AC1)


def _run_drop(root: Path, run_id: str, spec_ref: str) -> int:
    from tools import write_decision_drop as wdd

    return wdd.main([
        "--project-root", str(root), "--run-id", run_id,
        "--section", "Iterate — change: x", "--title", "T",
        "--context", "c", "--decision", "d", "--consequences", "q",
        "--spec-ref", spec_ref,
    ])


def test_f3_drop_write_refreshes_the_index(tmp_path):
    """Ledger 1 / AC1 — the index moves with the ADR file at F3."""
    _adr(tmp_path, "088-new-adr.md", "# ADR-088: Brand new\n")
    assert _run_drop(tmp_path, "iterate-2026-07-31-x", f"{ADR_SPEC_FOLDER}/088-new-adr.md") == 0
    index = _folder(tmp_path) / ADR_INDEX_FILENAME
    assert "- [ADR-088 — Brand new](088-new-adr.md)" in index.read_text(encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    # encoding="utf-8" explicitly: `text=True` decodes with the locale codec,
    # which is cp1252 on Windows and mangles the em-dash in every index row.
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_index_row_ships_in_the_same_commit_as_the_adr(tmp_path):
    """Ledger 24 / AC1 / R6 — the claim is *committed*, not merely written.

    Asserting the working tree would pass even if nothing ever staged the
    regenerated index — the exact false-green R6 was raised about. So this
    stages the way F6 does (an explicit per-path add of the ADR folder),
    commits, and reads the row back out of the commit with `git show`.
    """
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _adr(tmp_path, "094-shipped.md", "# ADR-094: Shipped together\n")

    assert _run_drop(tmp_path, "iterate-2026-07-31-c", f"{ADR_SPEC_FOLDER}/094-shipped.md") == 0
    # Stage using the path READ OUT OF F6.md, not a restatement of it — otherwise
    # narrowing F6's add could break AC1 while this test stayed green.
    _git(tmp_path, "add", _f6_adr_add_path())
    _git(tmp_path, "commit", "-q", "-m", "feat: adr")

    committed = _git(tmp_path, "show", f"HEAD:{ADR_SPEC_FOLDER}/{ADR_INDEX_FILENAME}")
    assert "- [ADR-094 — Shipped together](094-shipped.md)" in committed
    names = _git(tmp_path, "show", "--name-only", "--format=", "HEAD").split()
    assert f"{ADR_SPEC_FOLDER}/094-shipped.md" in names
    assert f"{ADR_SPEC_FOLDER}/{ADR_INDEX_FILENAME}" in names, (
        "the index row must ship in the SAME commit as the ADR it points at"
    )


_F6 = "plugins/shipwright-iterate/skills/iterate/references/F6.md"


def _f6_adr_add_path() -> str:
    """The ADR path F6.md actually tells the agent to stage.

    Read rather than restated, so the commit test above exercises F6's real
    instruction. Raises if F6 no longer stages the ADR folder at all.
    """
    for line in (_REPO_ROOT / _F6).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("git add {project_root}/.shipwright/planning/adr"):
            path = stripped.split()[2].replace("{project_root}/", "")
            return path.rstrip("/") or ADR_SPEC_FOLDER
    raise AssertionError(
        f"{_F6} no longer stages .shipwright/planning/adr/ — a regenerated "
        "INDEX.md would never ship, and the drift guard would red CI on the next run"
    )


def test_f6_add_list_names_the_adr_folder():
    """R6 — the obligation has to live where staging actually happens.

    Documenting it in F3.md is not enough: F6.md holds the explicit per-path
    list the agent works through at staging time, and it never uses `git add -A`.
    """
    assert _f6_adr_add_path() == ADR_SPEC_FOLDER


def test_f3_refresh_is_best_effort_and_warns(tmp_path, monkeypatch, capsys):
    """Ledger 14+15 / R5 — a failed refresh must not fail the drop, but must be LOUD.

    A silently swallowed failure hands the developer a green local run and a red
    CI drift guard with no clue what to do.
    """
    _adr(tmp_path, "089-x.md", "# ADR-089: X\n")

    def boom(_root):
        raise OSError("read-only file system")

    from lib import adr_index

    monkeypatch.setattr(adr_index, "rebuild_adr_index", boom)
    assert _run_drop(tmp_path, "iterate-2026-07-31-y", "") == 0
    err = capsys.readouterr().err
    assert "read-only file system" in err
    assert regen_command_resolved() in err, "the warning must name the regeneration command"


def test_f3_refresh_survives_a_lock_timeout(tmp_path, monkeypatch, capsys):
    """LockTimeout is a RuntimeError, NOT an OSError.

    Contention with a concurrent release pass is the exact case the index lock
    exists for. Catching only OSError let it escape `main()` and fail the whole
    finalize bundle AFTER the drop had already been written.
    """
    from lib import adr_index
    from lib.file_lock import LockTimeout

    _adr(tmp_path, "096-x.md", "# ADR-096: X\n")

    def boom(_root):
        raise LockTimeout("index busy")

    monkeypatch.setattr(adr_index, "rebuild_adr_index", boom)
    assert _run_drop(tmp_path, "iterate-2026-07-31-lock", "") == 0
    assert "index busy" in capsys.readouterr().err


# ------------------------------------------------------------- drift guard


def test_spec_folder_constant_agrees_with_write_decision_log():
    """Registry-driven SSoT meta-test: one folder path, two modules."""
    from tools.write_decision_log import ADR_SPEC_FOLDER as TOOLS_FOLDER

    assert TOOLS_FOLDER == ADR_SPEC_FOLDER


def test_committed_index_is_not_stale():
    """Ledger 9 / AC5+AC8 — the drift guard.

    Compared in LF-space: `read_text()` normalises the CRLF working tree that
    `core.autocrlf=true` produces, and `render_adr_index` emits LF.
    """
    folder = _REPO_ROOT / ADR_SPEC_FOLDER
    if not folder.is_dir():
        pytest.skip("no ADR spec folder in this checkout")
    index = folder / ADR_INDEX_FILENAME
    assert index.is_file(), f"{ADR_SPEC_FOLDER}/{ADR_INDEX_FILENAME} is missing"
    assert index.read_text(encoding="utf-8") == render_adr_index(folder), (
        f"{ADR_SPEC_FOLDER}/{ADR_INDEX_FILENAME} is stale. Regenerate:\n  {REGEN_COMMAND}"
    )


def test_drift_guard_actually_fails_on_a_stale_index(tmp_path):
    """Ledger 8 / AC5 — prove the guard above can fail, not just pass.

    A guard nobody has watched fail is not evidence.
    """
    _adr(tmp_path, "091-x.md", "# ADR-091: X\n")
    rebuild_adr_index(tmp_path)
    folder = _folder(tmp_path)
    _adr(tmp_path, "092-added-later.md", "# ADR-092: Added later\n")
    assert (folder / ADR_INDEX_FILENAME).read_text(encoding="utf-8") != render_adr_index(folder)


def test_every_adr_file_in_this_repo_is_listed():
    """AC8 — the count check, independent of byte-equality."""
    folder = _REPO_ROOT / ADR_SPEC_FOLDER
    if not folder.is_dir():
        pytest.skip("no ADR spec folder in this checkout")
    text = (folder / ADR_INDEX_FILENAME).read_text(encoding="utf-8")
    expected = [
        md.name for md in folder.iterdir()
        if md.is_file() and md.suffix == ".md"
        and md.name != ADR_INDEX_FILENAME and not md.name.startswith("_")
    ]
    missing = [name for name in expected if f"]({name})" not in text]
    assert not missing, f"{len(missing)} ADR file(s) unlisted in INDEX.md: {missing}"
