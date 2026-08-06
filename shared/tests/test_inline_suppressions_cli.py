"""The inline-suppression CLI — exit codes and the baseline skeleton.

Exit codes are the contract every other consumer depends on (the live guard,
a contributor's local run, any future CI wiring), so they are pinned rather
than assumed. Mirrors the register's own `test_accepted_risks_cli.py`.

Fixtures build suppression text through an f-string placeholder so this file's
own source is never counted as a suppression site.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import inline_suppressions as isup  # noqa: E402
from tools import inline_suppressions_cli as cli  # noqa: E402

_RULE = "python.lang.security.audit.non-literal-import.non-literal-import"
_REF = "iterate-2026-08-05-inline-suppression-ratchet"
_STATEMENT = "First-party module identifiers only, never untrusted input."


def _repo(tmp_path: Path, *, sources: dict, baseline=...) -> Path:
    for rel, text in sources.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if baseline is not ...:
        (tmp_path / isup.BASELINE_NAME).write_text(
            baseline if isinstance(baseline, str) else json.dumps(baseline),
            encoding="utf-8")
    return tmp_path


def _baseline(count: int) -> dict:
    return {
        "schema": 1,
        "rules": [{
            "rule": _RULE, "max_sites": count,
            "rationale_ref": _REF, "statement": _STATEMENT,
        }],
    }


def test_check_exits_zero_on_a_compliant_tree(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=_baseline(1),
    )
    assert cli.main(["check", "--project-root", str(root)]) == 0


def test_check_exits_one_on_a_ratchet(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_RULE}\n"},
        baseline=_baseline(1),
    )
    assert cli.main(["check", "--project-root", str(root)]) == 1


def test_check_exits_zero_when_the_only_finding_is_advisory(tmp_path, capsys):
    """A shrinking count must not fail the build, and the header must not call
    it 'drift' — a reduction is the outcome the gate exists to encourage."""
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=_baseline(5),
    )
    assert cli.main(["check", "--project-root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "advisory" in out and "drift:" not in out


def test_check_exits_two_on_a_corrupt_baseline(tmp_path):
    """Distinct from 1: the gate could not run at all, versus it ran and
    found drift. Collapsing them would hide a broken governance file behind a
    routine failure."""
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline="{not json")
    assert cli.main(["check", "--project-root", str(root)]) == 2


def test_check_discloses_a_missing_baseline_rather_than_passing_quietly(
    tmp_path, capsys
):
    root = _repo(tmp_path, sources={"a.py": f"# nosemgrep: {_RULE}\n"})
    assert cli.main(["check", "--project-root", str(root)]) == 1
    assert "no shipwright_inline_suppressions.json" in capsys.readouterr().out


def test_the_skeletons_placeholders_are_rejected_by_the_gate(tmp_path, capsys):
    """Caught in self-review, not by a fixture: the skeleton first shipped with
    `rationale_ref="ADR-000"` and a sentence-length TODO statement, and BOTH
    passed validation. Piping `scan --as-baseline` straight into the baseline
    would then have yielded a GREEN gate carrying no real governance — the
    exact laundering this baseline exists to prevent. The skeleton has to stay
    unusable until a human fills it in."""
    root = _repo(tmp_path, sources={"a.py": f"# nosemgrep: {_RULE}\n"})
    assert cli.main(
        ["scan", "--project-root", str(root), "--as-baseline"]) == 0

    skeleton = capsys.readouterr().out
    (root / isup.BASELINE_NAME).write_text(skeleton, encoding="utf-8")
    # Exit 2 = "the baseline is invalid", i.e. the gate refuses the skeleton.
    assert cli.main(["check", "--project-root", str(root)]) == 2


@pytest.mark.parametrize("mutation,which", [
    ({"statement": _STATEMENT}, "the rationale_ref placeholder alone"),
    ({"rationale_ref": _REF}, "the statement placeholder alone"),
])
def test_each_skeleton_placeholder_is_rejected_independently(
    tmp_path, mutation, which
):
    """`_entry_error` returns the FIRST violation and checks `rationale_ref`
    before `statement`, so a single all-TODO fixture would still pass if the
    statement placeholder silently became acceptable. Each is therefore filled
    in turn, leaving exactly one placeholder to do the rejecting (Stage-2 code
    review)."""
    root = _repo(tmp_path, sources={"a.py": f"# nosemgrep: {_RULE}\n"})
    doc = isup.seed_baseline(root, rationale_ref="TODO", statement="TODO")
    doc["rules"][0].update(mutation)
    (root / isup.BASELINE_NAME).write_text(json.dumps(doc), encoding="utf-8")

    assert cli.main(["check", "--project-root", str(root)]) == 2, which


def test_seeding_refuses_a_partial_count(tmp_path, monkeypatch):
    """`seed_baseline` discards `unreadable`, so a skeleton built over an
    unreadable file would freeze numbers that are too low while the docstring
    promises they are exact (Stage-3 doubt review, D11)."""
    root = _repo(tmp_path, sources={"a.py": f"# nosemgrep: {_RULE}\n"})
    real_read = Path.read_bytes

    def boom(self, *args, **kwargs):
        if self.name == "a.py":
            raise PermissionError("denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", boom)
    assert cli.main(
        ["scan", "--project-root", str(root), "--as-baseline"]) == 2


def test_prose_after_a_comma_is_diagnosed_not_just_blocked(tmp_path, capsys):
    """A comma after the real id makes the following words into rule ids —
    for Semgrep too, so blocking is right. But the operator sees a phantom
    rule and needs telling what they are looking at. The repo's own syntax
    reference recommends ` -- ` for justifications (Stage-3 doubt review,
    D13). The fixture is built through a placeholder, never as a literal, or
    this docstring would itself become a counted site."""
    root = _repo(tmp_path, sources={
        "a.py": f"# nosemgrep: {_RULE}, needed for Windows\n"})
    assert cli.main(["check", "--project-root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "UNRECORDED  needed" in out
    assert "does not look like a rule id" in out


def test_a_project_root_that_is_not_a_directory_fails_closed(tmp_path):
    """Otherwise git errors out, the walk finds nothing, no baseline exists,
    and the gate prints 'no drift.' and exits 0 — a clean bill of health for a
    tree that was never read (Stage-2 code review)."""
    assert cli.main(
        ["check", "--project-root", str(tmp_path / "typo")]) == 2


def test_the_skeleton_pins_the_real_measured_counts(tmp_path, capsys):
    root = _repo(tmp_path, sources={
        "a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_RULE}\n"})
    cli.main(["scan", "--project-root", str(root), "--as-baseline"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["rules"] == [{
        "rule": _RULE, "max_sites": 2,
        "rationale_ref": "TODO", "statement": "TODO",
    }]


def test_scan_lists_each_site_for_the_operator(tmp_path, capsys):
    root = _repo(tmp_path, sources={"pkg/a.py": f"# nosemgrep: {_RULE}\n"})
    assert cli.main(["scan", "--project-root", str(root)]) == 0
    out = capsys.readouterr().out
    assert _RULE in out and "pkg/a.py:1" in out
