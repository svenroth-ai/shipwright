"""Spec chain: plan stubs, plan/PR finders, AC history, the plan-stub F11 check, and the F5b plan_path fold."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import spec_chain as sc
from tools.spec_chain_cli import replay, with_history
from tools.verifiers import _finalization_claims as claims
from tools.verifiers.plan_stub_check import CHECK_NAME, check_plan_stub_recorded

_RUN = "iterate-2026-10-31-chain-probe"


@pytest.mark.covers("FR-01.11")
def test_stub_shapes_and_roundtrip():
    tiny = sc.render_stub("tiny", "g", "r", "PR 1")
    assert tiny.count("\n") == 1
    three = sc.render_stub("three", "g", "r", "PR 1")
    assert three.count("\n") == 3
    full = sc.render_stub("full", "g", "r", "PR 1", acs=["FR-01.11.AC01"], gap_fr="FR-01.11")
    assert "Affected ACs: FR-01.11.AC01" in full and "Catalog gap: FR-01.11" in full
    assert sc.parse_stub("Goal (WHAT): g\nReason (WHY): r\n")["reason"] == "r"
    for text in (tiny, three, full):
        assert sc.parse_stub(text) == {"goal": "g", "reason": "r", "reference": "PR 1"}
    assert sc.stub_kind([], "", True) == "tiny"
    assert sc.stub_kind([], "", False) == "three"
    assert sc.stub_kind(["FR-01.11.AC01"], "", True) == "full"
    assert sc.stub_kind([], "FR-01.11") == "full"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("raw,expected", [
    ("FR-01.03.AC05", "FR-01.03.AC05"), ("FR-01.03 AC5", "FR-01.03.AC05"), ("FR-01.03.5", None),
    ("FR-01.03", None), ("nonsense", None), (None, None),
])
def test_normalise_ac(raw, expected):
    assert sc.normalise_ac(raw) == expected


@pytest.mark.covers("FR-01.11")
def test_fold_plan_path_only_when_stub_exists(tmp_path):
    evt: dict = {}
    sc.fold_plan_path(evt, tmp_path, _RUN)
    assert "plan_path" not in evt
    (tmp_path / sc.plan_rel_path(_RUN)).parent.mkdir(parents=True)
    (tmp_path / sc.plan_rel_path(_RUN)).write_text("Goal: a\nReason: b\nReference: c\n", encoding="utf-8")
    sc.fold_plan_path(evt, tmp_path, _RUN)
    assert evt["plan_path"] == sc.plan_rel_path(_RUN)
    named = {"plan_path": "custom.md"}
    sc.fold_plan_path(named, tmp_path, _RUN)
    assert named["plan_path"] == "custom.md"


@pytest.mark.covers("FR-01.11")
def test_find_plan_field_convention_legacy_adr(tmp_path):
    base = tmp_path / ".shipwright/planning/iterate"
    (base / _RUN).mkdir(parents=True)
    assert sc.find_plan(tmp_path, {"adr_id": _RUN}) is None
    (base / _RUN / "mini_plan.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": _RUN}) == (f".shipwright/planning/iterate/{_RUN}/mini_plan.md", "legacy")
    (base / _RUN / "plan.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": _RUN})[1] == "convention"
    assert sc.find_plan(tmp_path, {"adr_id": _RUN, "plan_path": sc.plan_rel_path(_RUN)})[1] == "field"
    (base / "2026-05-16-old-run.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": "iterate-2026-05-16-old-run"})[1] == "legacy"
    (base / "iterate-2026-10-31-x-longer-run.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": "iterate-2026-10-31-x"}) is None  # a longer run is not a match
    (base / "iterate-2026-10-31-x-MINIPLAN.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": "iterate-2026-10-31-x"})[1] == "legacy"
    adr = tmp_path / ".shipwright/planning/adr"
    adr.mkdir(parents=True)
    (adr / "ADR-5.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": "ADR-5"}) == (".shipwright/planning/adr/ADR-5.md", "adr")


@pytest.mark.covers("FR-01.11")
def test_find_plan_ignores_paths_outside_planning(tmp_path):
    (tmp_path / "secret.md").write_text("x", encoding="utf-8")
    assert sc.find_plan(tmp_path, {"adr_id": "ADR-1", "plan_path": "secret.md"}) is None
    assert sc.find_plan(tmp_path, {"adr_id": "ADR-1", "plan_path": ".shipwright/planning/../../secret.md"}) is None


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


@pytest.mark.covers("FR-01.11")
def test_find_pr_field_and_git_exact_match(tmp_path):
    assert sc.find_pr(tmp_path, {"adr_id": _RUN, "pr": 7}) == (7, "field")
    assert sc.find_pr(tmp_path, {"adr_id": _RUN, "pr": "#8"}) == (8, "field")
    _git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-q", "-m", "feat: other (#41)\n\nRun-ID: " + _RUN + "-longer")
    assert sc.find_pr(tmp_path, {"adr_id": _RUN}) is None  # a longer id is a different run
    (tmp_path / "f").write_text("2", encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "feat: probe (#42)\n\nRun-ID: " + _RUN)
    assert sc.find_pr(tmp_path, {"adr_id": _RUN}) == (42, "git")


_SPEC = """## Acceptance Criteria

### FR-01.01 — A

- (E) [AC01] Given x, when y, then z.
- (E) [AC02] Given x, when y, then z
  continued. (iterate-2026-07-27-name-the-blocker; iterate-2026-08-03-other-run)
- (E) [AC03] Given a, then b.

### FR-01.02 — B

- [AC01] Given q. (iterate-2026-09-01-third)
"""


@pytest.mark.covers("FR-01.11")
def test_parse_spec_acs_collects_run_ids_per_ac():
    got = sc.parse_spec_acs(_SPEC)
    assert got == {"FR-01.01.AC01": [], "FR-01.01.AC02": ["iterate-2026-07-27-name-the-blocker", "iterate-2026-08-03-other-run"],
                   "FR-01.01.AC03": [], "FR-01.02.AC01": ["iterate-2026-09-01-third"]}


@pytest.mark.covers("FR-01.11")
def test_ac_history_joins_spec_text_events_plan_and_pr(tmp_path):
    base = tmp_path / ".shipwright/planning/iterate"
    base.mkdir(parents=True)
    (base / "iterate-2026-09-01-third.md").write_text("x", encoding="utf-8")
    events = [
        {"type": "work_completed", "adr_id": "iterate-2026-09-01-third", "ts": "2026-09-01", "pr": 11},
        {"type": "work_completed", "adr_id": _RUN, "ts": "2026-10-31", "pr": 12, "plan_path": "p.md",
         "affected_acs": [{"ac": "FR-01.02.AC01", "disposition": "changed", "why": "w"}]},
    ]
    out = sc.ac_history(tmp_path, "FR-01.02.AC01", events, sc.parse_spec_acs(_SPEC))
    rows = {r["run_id"]: r for r in out["runs"]}
    assert set(rows) == {"iterate-2026-09-01-third", _RUN}
    assert rows["iterate-2026-09-01-third"]["pr"] == 11 and rows["iterate-2026-09-01-third"]["plan_kind"] == "legacy"
    assert rows[_RUN]["via"] == ["event"] and rows[_RUN]["disposition"] == "changed"


def _seed(root: Path, **event) -> None:
    evt = {"type": "work_completed", "source": "iterate", "commit": "", "adr_id": _RUN, "intent": "change",
           "changed_files": ["shared/scripts/lib/x.py"], **event}
    (root / "shipwright_events.jsonl").write_text(json.dumps(evt) + "\n", encoding="utf-8")


@pytest.mark.covers("FR-01.11")
def test_check_warns_when_plan_stub_missing_never_errors(tmp_path):
    _seed(tmp_path)
    result = check_plan_stub_recorded(tmp_path, _RUN, "")
    assert result.ok is False and result.severity == "warning" and result.strict_exempt is True
    _seed(tmp_path, plan_path="gone.md")
    assert check_plan_stub_recorded(tmp_path, _RUN, "").severity == "warning"
    plan = tmp_path / ".shipwright/planning/p.md"; plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("nothing useful\n", encoding="utf-8")
    _seed(tmp_path, plan_path=".shipwright/planning/p.md")
    assert check_plan_stub_recorded(tmp_path, _RUN, "").severity == "warning"
    plan.write_text(sc.render_stub("three", "g", "r", "ref"), encoding="utf-8")
    ok = check_plan_stub_recorded(tmp_path, _RUN, "")
    assert ok.ok is True and ok.detail == "recorded"


@pytest.mark.covers("FR-01.11")
def test_check_skips_without_event_or_scoped_intent(tmp_path):
    assert check_plan_stub_recorded(tmp_path, _RUN, "").severity == "skipped"
    _seed(tmp_path, changed_files=["docs/guide.md"])
    assert check_plan_stub_recorded(tmp_path, _RUN, "").severity == "warning"  # asked in any project, whatever paths
    _seed(tmp_path, intent="docs")
    assert check_plan_stub_recorded(tmp_path, _RUN, "").severity == "skipped"


@pytest.mark.covers("FR-01.11")
def test_check_is_registered():
    assert check_plan_stub_recorded in claims.CLAIM_CHECKS
    assert CHECK_NAME


@pytest.mark.covers("FR-01.11")
def test_load_events_applies_pr_amendment_and_fr_history(tmp_path):
    lines = [{"type": "work_completed", "id": "e1", "adr_id": _RUN, "affected_frs": ["FR-01.11"]},
             {"type": "event_amended", "amends": "e1", "fields": {"pr": 99}}]
    (tmp_path / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    events = sc.load_events(tmp_path)
    assert len(events) == 1 and events[0]["pr"] == 99
    assert sc.fr_history(tmp_path, "FR-01.11", events)["runs"][0]["pr"] == 99


@pytest.mark.covers("FR-01.11")
def test_replay_separates_post_change_cohort_and_with_history(tmp_path):
    base = tmp_path / ".shipwright/planning/iterate"
    base.mkdir(parents=True)
    (base / "iterate-2026-10-31-a").mkdir()
    (base / "iterate-2026-10-31-a" / "plan.md").write_text("Goal: g\nReason: r\n", encoding="utf-8")
    events = [
        {"type": "work_completed", "id": "e1", "adr_id": "iterate-2026-10-31-a", "affected_frs": ["FR-01.11"],
         "plan_path": sc.plan_rel_path("iterate-2026-10-31-a"), "pr": 5},
        {"type": "work_completed", "id": "e2", "adr_id": "ADR-9", "affected_frs": ["FR-01.11"]},
    ]
    events[0]["ts"], events[1]["ts"] = "2026-11-01", "2026-11-02"
    events[0].update(intent="change", source="iterate", affected_acs=[{"ac": "FR-01.11.AC01"}])
    events[1].update(intent="change", source="iterate")
    out = replay(tmp_path, events, 1, 20, "2026-11-01")
    assert out["sampled"] == 2 and out["fr_plan_pr_resolved"] == 1
    cohort = out["post_change_cohort"]
    assert (cohort["eligible"], cohort["sampled"], cohort["resolved_plan_pr_and_ac"]) == (2, 2, 1)
    assert cohort["failed"] == ["ADR-9"]  # a run that forgot plan_path is counted as a failure, not left out
    assert len(out["unresolved"]) == 1
    assert with_history(tmp_path, [{"type": "work_completed", "adr_id": "x", "affected_acs": [{"ac": "FR-01.11.AC01"}]}]) == ["FR-01.11.AC01"]


@pytest.mark.covers("FR-01.11")
def test_check_warns_not_crashes_on_non_utf8_plan(tmp_path):
    plan = tmp_path / ".shipwright/planning/p.md"
    plan.parent.mkdir(parents=True)
    plan.write_bytes("Goal: g\nReason: r\n".encode("utf-16"))
    _seed(tmp_path, plan_path=".shipwright/planning/p.md")
    assert check_plan_stub_recorded(tmp_path, _RUN, "").severity == "warning"


@pytest.mark.covers("FR-01.11")
def test_parse_spec_acs_section_after_last_fr_and_one_char_slug():
    text = "### FR-01.01 - A\n\n- [AC01] x (iterate-2026-10-31-x)\n\n## Non-functional\n\n- [AC01] y\n"
    assert sc.parse_spec_acs(text) == {"FR-01.01.AC01": ["iterate-2026-10-31-x"]}


@pytest.mark.covers("FR-01.11")
def test_write_plan_stub_cli_refuses_overwrite_and_bad_run_id(tmp_path):
    tool = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "write_plan_stub.py"
    base = ["uv", "run", str(tool), "--project-root", str(tmp_path), "--goal", "g", "--reason", "r", "--ref", "x"]
    import sys as _sys
    from tools import write_plan_stub
    argv = ["write_plan_stub", "--project-root", str(tmp_path / "inproc"), "--run-id", _RUN, "--goal", "g", "--reason", "r", "--ref", "x", "--tiny"]
    old, _sys.argv = _sys.argv, argv
    try:
        assert write_plan_stub.main() == 0
        assert write_plan_stub.main() == 1  # refuses to overwrite
    finally:
        _sys.argv = old
    assert sc.parse_stub((tmp_path / "inproc" / sc.plan_rel_path(_RUN)).read_text(encoding="utf-8"))["goal"] == "g"
    first = subprocess.run([*base, "--run-id", _RUN], capture_output=True, text=True)
    assert first.returncode == 0 and (tmp_path / sc.plan_rel_path(_RUN)).read_bytes().count(b"\r") == 0
    assert subprocess.run([*base, "--run-id", _RUN], capture_output=True, text=True).returncode == 1
    assert subprocess.run([*base, "--run-id", "../evil"], capture_output=True, text=True).returncode == 2


@pytest.mark.covers("FR-01.11")
def test_find_pr_prefers_run_id_trailer_over_a_mention(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-q", "-m", "feat: newer (#51)\n\nfollows up " + _RUN + " in prose\n\nRun-ID: other-run")
    (tmp_path / "f").write_text("2", encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "feat: real (#50)\n\nRun-ID: " + _RUN)
    assert sc.find_pr(tmp_path, {"adr_id": _RUN}) == (50, "git")
    assert sc.find_plan(tmp_path, {"adr_id": "../x"}) is None and sc.find_pr(tmp_path, {"adr_id": "../x"}) is None


@pytest.mark.covers("FR-01.11")
def test_parse_spec_acs_pads_ac_numbers():
    assert list(sc.parse_spec_acs("### FR-01.01 - A\n\n- [AC5] x\n")) == ["FR-01.01.AC05"]
