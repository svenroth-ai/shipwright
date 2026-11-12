"""G4 - closing token in a commit vs the card's status (trg-52196e41). Report only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_g4  # noqa: E402
from scripts.audit.triage_bundle import _triage_api  # noqa: E402

A, B, C = "trg-aaaaaaaa", "trg-bbbbbbbb", "trg-cccccccc"

pytestmark = pytest.mark.covers("FR-01.14")



@pytest.mark.parametrize("message,expected", [
    (f"fix: x\n\nCloses {A}", [A]),
    (f"fix: x\n\nfixes triage {A}", [A]),
    (f"resolves triage card {A}", [A]),
    (f"FIXES {A.upper()}", [A]),
    (f"Closes {A}, {B} and {C}", [A, B, C]),
    (f"Closes {A} and {B}", [A, B]),
    (f"Fixes {A}, and {B}", [A, B]),
    (f"Closes {A} and {A}", [A]),
])
def test_tokens(message, expected):
    assert group_g4.closing_ids(message) == expected


@pytest.mark.parametrize("message", [
    f"Related: {A}",
    f"supersedes {A}",
    f"see triage {A}",
    f"fixed here, filed as {A}",
    f"deferred to triage {A}",
    f"Closes the loop on {A}",
    f"Closes {A[:-1]}",
    f"Fixes {A}0",
    f"Fixes {A}x",
    f"Fixes {A} (first half)",
    f"Fixes {A} (root half)",
    f"Fixes {A} (--project-root half)",
    f"Fixes {A} first half",
    f"Resolves {A} (part 1)",
    f'Revert "fix: x\n\nCloses {A}"',
])
def test_not_tokens(message):
    assert group_g4.closing_ids(message) == []


def test_longer_id_in_a_list_is_dropped_not_truncated():
    assert group_g4.closing_ids(f"Closes {A}, {B}9") == [A]


def test_partial_then_full_in_one_list():
    assert group_g4.closing_ids(f"Fixes {A} (half), {B}") == []  # conservative: the list starts with a partial


def test_evaluate_status_rules():
    commits = [("1" * 40, f"Closes {A}, {B}, {C}"), ("2" * 40, "Closes trg-dddddddd")]
    findings, unknown = group_g4.evaluate(
        commits, {A: "triage", B: "dismissed", C: "snoozed"})
    assert [(f[1], f[2]) for f in findings] == [(A, "triage"), (C, "snoozed")]
    assert unknown == [("2" * 40, "trg-dddddddd")]
    assert group_g4.evaluate(commits, {A: "promoted", B: "dismissed", C: "dismissed"})[0] == []


def test_parse_log():
    raw = f"{'1' * 40}\x1fsubject\n\nbody\n\x1e\n{'2' * 40}\x1fother\x1e\n"
    assert [(s[:1], b.splitlines()[0]) for s, b in group_g4.parse_log(raw)] == [("1", "subject"), ("2", "other")]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, status_event: str | None, tag: bool = True) -> tuple[Path, str]:
    from triage import append_triage_item, mark_status  # noqa: PLC0415
    _git(tmp_path.parent, "init", "-b", "main", str(tmp_path))
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    card = append_triage_item(tmp_path, source="t", severity="low", kind="bug", title="c", detail="d")
    if status_event:
        mark_status(tmp_path, card, new_status=status_event, by="t", reason="r")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "chore: base")
    if tag:
        _git(tmp_path, "tag", "v1.0.0")
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-m", f"fix: thing\n\nCloses {card}")
    return tmp_path, card


def test_reports_seeded_close_without_status(tmp_path):
    assert _triage_api()[3] is not None
    repo, card = _repo(tmp_path, None)
    [f] = group_g4.run(repo, {}, None)
    assert (f.check_id, f.status, f.severity) == ("G4", "fail", "MEDIUM")
    assert any(card in e and "'triage'" in e for e in f.evidence)
    assert "since v1.0.0" in f.detail
    assert card in f.detail  # actionable from the backlog card: ids are named


def test_silent_when_status_exists(tmp_path):
    repo, _ = _repo(tmp_path, "dismissed")
    [f] = group_g4.run(repo, {}, None)
    assert f.status == "pass"


def test_no_tag_says_so(tmp_path):
    repo, _ = _repo(tmp_path, None, tag=False)
    [f] = group_g4.run(repo, {}, None)
    assert f.status == "fail" and "no release tag" in f.detail and "500" in f.detail


def test_unknown_id_is_info_only(tmp_path):
    repo, _ = _repo(tmp_path, "dismissed")
    (repo / "g.txt").write_text("y", encoding="utf-8")
    _git(repo, "add", "g.txt")
    _git(repo, "commit", "-m", "fix: y\n\nFixes trg-deadbeef")
    [f] = group_g4.run(repo, {}, None)
    assert f.status == "pass"
    assert any(e.startswith("info:") and "trg-deadbeef" in e for e in f.evidence)


def test_registered_under_group_g(tmp_path):
    from scripts.audit import audit_detector, _registry  # noqa: PLC0415
    _registry.register_all()
    repo, card = _repo(tmp_path, None)
    findings = audit_detector._GROUPS["G"](repo, {}, None)
    assert any(f.check_id == "G4" and f.status == "fail" and card in " ".join(f.evidence) for f in findings)
