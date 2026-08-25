"""Git-layer and CLI tests for the post-Build risk re-check.

Split from `test_diff_risk_recheck.py` along the same seam as the source
(`diff_change_set` vs `diff_risk_recheck`): everything here parses git porcelain
or drives the CLI.

`_git` is monkeypatched by MODULE OBJECT (ADR-045), on `diff_change_set` — the
module that actually calls it. `diff_risk_recheck` re-exports the name, but
`collect_change_set` resolves it from its own globals, so patching the re-export
would leave real git running.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import diff_change_set as dcs  # noqa: E402
import diff_risk_recheck as drr  # noqa: E402

HOOK = "plugins/shipwright-iterate/hooks/hooks.json"
WORKFLOW = ".github/workflows/ci.yml"
INERT = "src/components/Button.tsx"


# ---------------------------------------------------------------------------
# numstat parsing — review findings O4 / O7 / G1
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_parse_numstat_counts_added_and_deleted():
    paths, loc = drr.parse_numstat_z("1\t2\tsrc/a.py\0")
    assert paths == ["src/a.py"]
    assert loc == 3


@pytest.mark.covers("FR-01.11")
def test_parse_numstat_binary_files_count_zero():
    """Binary files report `-` rather than a count."""
    paths, loc = drr.parse_numstat_z("-\t-\tassets/logo.png\0")
    assert paths == ["assets/logo.png"]
    assert loc == 0


@pytest.mark.covers("FR-01.11")
def test_parse_numstat_rejects_rename_shaped_records():
    """`--no-renames` is a correctness requirement, and this pins the coupling.

    With rename detection ON, git emits `added TAB deleted TAB NUL old NUL new NUL`
    and reports ONLY the new path — so moving `.github/workflows/security.yml` to
    `security.yml.disabled` raises no CI flag and an autonomous unit could disable
    a security workflow unnoticed. The parser must refuse that shape loudly rather
    than parse it into a half-truth: if someone drops `--no-renames` from
    `collect_change_set`, this fails instead of the gate going quiet.
    """
    with pytest.raises(ValueError, match="rename detection"):
        drr.parse_numstat_z("1\t0\t\0old/x.py\0new/y.py\0")


@pytest.mark.covers("FR-01.11")
def test_parse_numstat_handles_filename_with_newline():
    """-z output is NUL-delimited precisely so a newline in a filename is data,
    not a record separator (review finding O7)."""
    paths, _ = drr.parse_numstat_z("1\t0\tsrc/we\nird.py\0")
    assert paths == ["src/we\nird.py"]


@pytest.mark.covers("FR-01.11")
def test_parse_numstat_empty_input():
    assert drr.parse_numstat_z("") == ([], 0)


@pytest.mark.covers("FR-01.11")
def test_parse_untracked_z():
    assert drr.parse_untracked_z("a.py\0b/c.py\0") == ["a.py", "b/c.py"]
    assert drr.parse_untracked_z("") == []


# ---------------------------------------------------------------------------
# git layer, in-process. Subprocess-only tests measure 0% against the <80%
# diff-coverage gate, so `_git` is monkeypatched by MODULE OBJECT (ADR-045 —
# never the "lib.X" string, which binds whichever copy loaded first).
# ---------------------------------------------------------------------------


def _fake_git(monkeypatch, responses):
    """Route `_git(root, *args)` by its first argument.

    Patched on `diff_change_set`, NOT `diff_risk_recheck` (ADR-045: bind the MODULE
    OBJECT that calls it) — `collect_change_set` resolves `_git` from its own
    globals, so patching the re-export would leave real git running."""
    def fake(root, *args):
        return responses[args[0]]
    monkeypatch.setattr(dcs, "_git", fake)


@pytest.mark.covers("FR-01.11")
def test_collect_change_set_unions_tracked_and_untracked(monkeypatch):
    _fake_git(monkeypatch, {
        "merge-base": (0, "abc123\n"),
        "diff": (0, f"3\t1\t{HOOK}\0"),
        "ls-files": (0, "plugins/x/hooks/new.py\0"),
    })
    paths, loc = drr.collect_change_set(Path("/repo"), "origin/main")
    assert paths == [HOOK, "plugins/x/hooks/new.py"]
    assert loc == 4


@pytest.mark.covers("FR-01.11")
def test_collect_change_set_prefers_merge_base_over_ref_tip(monkeypatch):
    """A moved origin/main must not read as this unit's changes."""
    seen = {}

    def fake(root, *args):
        seen[args[0]] = args
        return {
            "merge-base": (0, "forkpoint\n"),
            "diff": (0, ""),
            "ls-files": (0, ""),
        }[args[0]]

    monkeypatch.setattr(dcs, "_git", fake)
    drr.collect_change_set(Path("/repo"), "origin/main")
    assert "forkpoint" in seen["diff"], "diff must run against the FORK POINT"


@pytest.mark.covers("FR-01.11")
def test_collect_change_set_falls_back_when_no_common_ancestor(monkeypatch):
    _fake_git(monkeypatch, {
        "merge-base": (1, ""),          # unrelated histories
        "rev-parse": (0, "deadbee\n"),
        "diff": (0, ""),
        "ls-files": (0, ""),
    })
    assert drr.collect_change_set(Path("/repo"), "weird") == ([], 0)


@pytest.mark.covers("FR-01.11")
def test_unresolvable_base_ref_raises(monkeypatch):
    _fake_git(monkeypatch, {"merge-base": (1, ""), "rev-parse": (1, "")})
    with pytest.raises(RuntimeError, match="cannot resolve base ref"):
        drr.collect_change_set(Path("/repo"), "nope")


@pytest.mark.covers("FR-01.11")
def test_untracked_failure_raises_instead_of_silently_dropping(monkeypatch):
    """Fail-OPEN here reproduces the defect being fixed: untracked is the leg that
    sees a brand-new hook file."""
    _fake_git(monkeypatch, {
        "merge-base": (0, "abc\n"),
        "diff": (0, ""),
        "ls-files": (128, ""),
    })
    with pytest.raises(RuntimeError, match="ls-files"):
        drr.collect_change_set(Path("/repo"), "origin/main")


@pytest.mark.covers("FR-01.11")
def test_negative_diff_loc_rejected():
    """The result schema requires `minimum: 0`, so a negative value would emit a
    result that cannot be represented in the contract — and would suppress the
    diff-size review trigger on the way. Validated in `recheck()` so direct
    callers are covered, not only the CLI."""
    with pytest.raises(ValueError, match="diff_loc"):
        drr.recheck([INERT], "small", diff_loc=-1)


@pytest.mark.covers("FR-01.11")
def test_untracked_lines_are_counted(tmp_path):
    """numstat cannot see untracked files, so counting only its output reports
    diff_loc=0 when the whole change is NEW files — and 3.5's >100 arm never fires."""
    (tmp_path / "new.py").write_text("a\nb\nc\n", encoding="utf-8")
    assert dcs.untracked_loc(tmp_path, ["new.py"]) == 3


@pytest.mark.covers("FR-01.11")
def test_untracked_binary_and_missing_files_count_zero(tmp_path):
    (tmp_path / "img.png").write_bytes(b"\x89PNG\0\0binary")
    assert dcs.untracked_loc(tmp_path, ["img.png"]) == 0
    assert dcs.untracked_loc(tmp_path, ["gone.py"]) == 0


@pytest.mark.covers("FR-01.11")
def test_untracked_file_without_trailing_newline_counts_its_last_line(tmp_path):
    (tmp_path / "x.py").write_text("one\ntwo", encoding="utf-8")
    assert dcs.untracked_loc(tmp_path, ["x.py"]) == 2


@pytest.mark.covers("FR-01.11")
def test_diff_failure_raises(monkeypatch):
    _fake_git(monkeypatch, {
        "merge-base": (0, "abc\n"), "diff": (128, ""),
    })
    with pytest.raises(RuntimeError, match="git diff"):
        drr.collect_change_set(Path("/repo"), "origin/main")


# ---------------------------------------------------------------------------
# main() — the documented (exit code, stdout JSON) contract
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, capsys, argv_extra):
    monkeypatch.setattr(
        sys, "argv",
        ["diff_risk_recheck.py", "--stage1-complexity", "small", *argv_extra],
    )
    code = drr.main()
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.covers("FR-01.11")
def test_main_exit_0_and_json_when_clean(monkeypatch, capsys):
    code, out = _run_main(monkeypatch, capsys, ["--changed-files", INERT])
    assert code == 0
    assert out["risk_flags"] == []


@pytest.mark.covers("FR-01.11")
def test_main_exit_3_and_json_on_ci_escalation(monkeypatch, capsys):
    code, out = _run_main(monkeypatch, capsys, ["--changed-files", WORKFLOW])
    assert code == 3
    assert out["escalate"]["reason_code"] == "ci_supplychain_requires_operator"


@pytest.mark.covers("FR-01.11")
def test_main_exit_2_still_writes_json(monkeypatch, capsys):
    """Parseable stdout on every exit this module decides."""
    _fake_git(monkeypatch, {"merge-base": (1, ""), "rev-parse": (1, "")})
    code, out = _run_main(monkeypatch, capsys, ["--base-ref", "nope"])
    assert code == 2
    assert "cannot resolve base ref" in out["error"]
    assert out["escalate"]["required"] is False


@pytest.mark.covers("FR-01.11")
def test_main_defaults_base_ref_to_head(monkeypatch, capsys):
    """`base_branch` is NULL for the first stacked sub-iterate; nothing is
    committed until F6, so HEAD is still the branch point."""
    seen = {}

    def fake(root, *args):
        seen.update({args[0]: args})
        return {"merge-base": (0, "abc\n"), "diff": (0, ""), "ls-files": (0, "")}[args[0]]

    monkeypatch.setattr(dcs, "_git", fake)
    code, _ = _run_main(monkeypatch, capsys, [])
    assert code == 0
    assert "HEAD" in seen["merge-base"]


@pytest.mark.covers("FR-01.11")
def test_main_passes_stage1_flags_through(monkeypatch, capsys):
    code, out = _run_main(
        monkeypatch, capsys,
        ["--changed-files", INERT, "--stage1-flags", "touches_auth"],
    )
    assert code == 0
    assert out["plan_review_required"] is True


# ---------------------------------------------------------------------------
# The CI escalation must be exitable, through the CLI (doubt finding D1)
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_main_exit_0_once_an_ack_exists(monkeypatch, capsys, tmp_path):
    ack = drr.ack_path(tmp_path, "iterate-2026-08-05-run-1")
    ack.parent.mkdir(parents=True)
    ack.write_text("{}", encoding="utf-8")
    code, out = _run_main(monkeypatch, capsys, [
        "--changed-files", WORKFLOW,
        "--project-root", str(tmp_path), "--run-id", "iterate-2026-08-05-run-1",
    ])
    assert code == 0
    assert out["ci_ack_recorded"] is True


@pytest.mark.covers("FR-01.11")
def test_main_still_exits_3_when_the_ack_is_for_another_run(monkeypatch, capsys, tmp_path):
    """Run-bound on purpose: a previous run's ack must not license this diff."""
    ack = drr.ack_path(tmp_path, "iterate-2026-08-05-some-other-run")
    ack.parent.mkdir(parents=True)
    ack.write_text("{}", encoding="utf-8")
    code, _ = _run_main(monkeypatch, capsys, [
        "--changed-files", WORKFLOW,
        "--project-root", str(tmp_path), "--run-id", "iterate-2026-08-05-run-1",
    ])
    assert code == 3
