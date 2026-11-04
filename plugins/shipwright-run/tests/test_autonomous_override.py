"""autonomous_override: the rule that lets an autonomous run override a failing screenshot check without asking.

Conservative on purpose: a real failure (an error, an undocumented or uncommitted cause, a screen that still fails without the
accepted causes, another gate finding, an unverifiable ratio, an interactive run) always stays a question. The evidence is
checked where it can be: the ratio is recomputed from the neutralised screenshot pair (bound to the check's real pair) and the gate
verdict comes from the real validator.
"""
from __future__ import annotations

import copy
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.06/AC12")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
import autonomous_override as ao  # noqa: E402

SHOT_MSG = "Screenshot check did not pass (status='fail'); built screens do not match"

RESULTS = {
    "screenshot_check": {"applies": True, "status": "fail", "captured": True, "tolerance": 0.15, "screens": [
        {"mockup": "01-a.html", "status": "fail", "diff_ratio": 0.31,
         "screenshots": {"approved": "e2e/screenshots/real/a.png", "built": "e2e/screenshots/real/b.png"}},
        {"mockup": "02-b.html", "status": "pass", "diff_ratio": 0.05}]},
    "screenshot_check_accepted_causes": {
        "accepted_causes": {"a": "brief-required header line", "b": "local fonts"},
        "sources": {"a": "brief:brief.md", "b": "ADR-129"},
        "quotes": {"a": "the header line shows the mode", "b": "fonts are bundled offline"},
        "screens": [{"mockup": "01-a.html", "real_diff_ratio": 0.31, "attributed_diff_ratio_without_accepted_causes": 0.0,
                     "causes": ["a", "b"],
                     "neutralised": {"approved": "e2e/screenshots/n/a.png", "built": "e2e/screenshots/n/b.png"}}]},
}


def png(path: Path, boxes, size=(128, 80)):
    """A small 8-bit gray PNG: white page with black rectangles (content the comparison can see)."""
    w, h = size
    rows = [[255] * w for _ in range(h)]
    for x0, y0, x1, y1 in boxes:
        for y in range(y0, y1):
            for x in range(x0, x1):
                rows[y][x] = 0
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


SAME = [(8, 8, 60, 20), (8, 40, 120, 70)]
NEUTRAL = SAME + [(100, 5, 104, 9)]  # the built page minus the accepted causes: close to the approved one, not a copy of it


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


def project(tmp_path, results=None, config=None, adr="ADR-129", commit=True, built=NEUTRAL):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "brief").mkdir(exist_ok=True)
    (tmp_path / "brief" / "brief.md").write_text("# brief\nthe header line shows the mode and the date\n", encoding="utf-8")
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(f"### {adr}: local fonts\n- fonts are bundled offline\n", encoding="utf-8")
    cfg = {"autonomy": "guided", "brief_dir": "brief", "brief_package": {"package_sha256": "0" * 64}} if config is None else config
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    shots = tmp_path / "e2e" / "screenshots"
    png(shots / "n" / "a.png", SAME)
    png(shots / "n" / "b.png", built)
    png(shots / "real" / "a.png", SAME)  # the check's own pair: the built page still carries the accepted causes
    png(shots / "real" / "b.png", SAME + [(60, 25, 125, 78)])
    cmp_ = ao._load_module(Path(ao.__file__).resolve().parents[3] / "shipwright-test" / "scripts" / "lib" / "png_compare.py", "_t_png")
    ratio = cmp_.compare_images(shots / "real" / "a.png", shots / "real" / "b.png", 0.15)["diff_ratio"]
    text = json.dumps(RESULTS if results is None else results).replace("0.31", repr(ratio))
    (tmp_path / "shipwright_test_results.json").write_text(text, encoding="utf-8")
    if commit and not (tmp_path / ".git").exists():
        git(tmp_path, "init", "-q")
        git(tmp_path, "add", ".shipwright/agent_docs/decision_log.md")
        git(tmp_path, "commit", "-q", "-m", "x")
    return tmp_path


def mutated(fn):
    r = copy.deepcopy(RESULTS)
    fn(r)
    return r


def decide(root, asks=(SHOT_MSG,), extra=None):
    return ao.decide_screenshot_override(root, extra, gate=list(asks))


def test_documented_causes_with_checked_evidence_are_allowed_with_a_reason(tmp_path):
    out = decide(project(tmp_path))
    assert out["allowed"] is True and out["screens"] == ["01-a.html"], out
    assert out["reason"].startswith(ao.AUTONOMOUS_REASON_PREFIX) and "ADR-129" in out["reason"] and "brief:brief.md" in out["reason"]


@pytest.mark.parametrize("config", [{"autonomy": "guided"}, {"autonomy": "guided", "brief_dir": "brief"}, "nonsense"])
def test_an_interactive_run_is_never_decided_by_the_rule(tmp_path, config):
    out = decide(project(tmp_path, config=config))
    assert out["allowed"] is False and "not an autonomous run" in out["reasons"][0]


def test_unattended_has_no_override_path_and_autonomy_alone_is_enough_otherwise(tmp_path):
    out = decide(project(tmp_path, config={"autonomy": "unattended", "brief_dir": "brief"}))
    assert out["allowed"] is False and "no override path" in out["reasons"][0]
    r = mutated(lambda d: d["screenshot_check_accepted_causes"].update(sources={"a": "ADR-129", "b": "ADR-129"}, quotes={"a": "fonts are bundled offline", "b": "fonts are bundled offline"}))
    assert decide(project(tmp_path / "x", results=r, config={"autonomy": " Autonomous "}))["allowed"] is True


def test_the_gate_verdict_comes_from_the_validator_not_the_caller(tmp_path):
    out = decide(project(tmp_path), asks=(SHOT_MSG, "Smoke test failed - app not responding correctly. Continue anyway?"))
    assert out["allowed"] is False and "other findings" in out["reasons"][0]
    assert decide(project(tmp_path / "y"), asks=())["allowed"] is False  # no screenshot finding at all
    assert decide(project(tmp_path / "z"), extra=["something else"])["allowed"] is False  # a caller can only ADD findings
    root = project(tmp_path / "v")  # the real validator: this results file has no other layers, so it raises findings of its own
    out = ao.decide_screenshot_override(root)
    assert out["allowed"] is False and ao.gate_asks(root) is not None


def test_an_error_check_is_never_excused(tmp_path):
    r = mutated(lambda d: d["screenshot_check"].update(status="error"))
    assert decide(project(tmp_path, results=r))["allowed"] is False


def test_a_screen_in_error_has_no_attribution(tmp_path):
    r = mutated(lambda d: d["screenshot_check"]["screens"].append({"mockup": "03-c.html", "status": "error"}))
    out = decide(project(tmp_path, results=r))
    assert out["allowed"] is False and "03-c.html" in " ".join(out["reasons"])


@pytest.mark.parametrize("sources,quotes,needle", [
    ({"a": "brief:brief.md"}, None, "'b'"),                                     # a cause with no source
    ({"a": "brief:brief.md", "b": "ADR-999"}, None, "ADR-999"),                 # an ADR the committed log does not hold
    ({"a": "brief:nope.md", "b": "ADR-129"}, None, "not a file"),               # a file the package does not hold
    ({"a": "brief:../secret", "b": "ADR-129"}, None, "does not name"),
    ({"a": "brief:C:secrets.txt", "b": "ADR-129"}, None, "does not name"),
    ({"a": "my own judgement", "b": "ADR-129"}, None, "neither"),
    ({"a": "brief:brief.md", "b": "ADR-129"}, {"a": "text that is not in the file"}, "verbatim"),   # brief.md always exists: the quote must
    ({"a": "brief:brief.md", "b": "ADR-129"}, {}, "verbatim"),
])
def test_every_cause_needs_a_documented_earlier_source(tmp_path, sources, quotes, needle):
    def change(d):
        d["screenshot_check_accepted_causes"]["sources"] = sources
        if quotes is not None:
            d["screenshot_check_accepted_causes"]["quotes"] = quotes
    out = decide(project(tmp_path, results=mutated(change)))
    assert out["allowed"] is False and needle in " ".join(out["reasons"])


def test_an_adr_the_test_phase_just_wrote_is_not_decided_earlier(tmp_path):
    root = project(tmp_path, adr="ADR-100")  # the committed log holds ADR-100 only
    log = root / ".shipwright" / "agent_docs" / "decision_log.md"
    log.write_text(log.read_text(encoding="utf-8") + "### ADR-129: written now\n", encoding="utf-8")  # uncommitted
    out = decide(root)
    assert out["allowed"] is False and "ADR-129" in " ".join(out["reasons"])


def test_without_git_an_adr_source_cannot_be_confirmed(tmp_path):
    out = decide(project(tmp_path, commit=False))
    assert out["allowed"] is False and "cannot be read" in " ".join(out["reasons"])


def test_a_copied_capture_or_a_missing_real_pair_cannot_neutralise_a_screen(tmp_path):
    copied = decide(project(tmp_path / "c", built=SAME))  # built "neutralised" = byte copy of the approved capture
    assert copied["allowed"] is False and "copy of the opposite" in " ".join(copied["reasons"])
    same_file = mutated(lambda d: d["screenshot_check_accepted_causes"]["screens"][0].update(
        neutralised={"approved": "e2e/screenshots/real/a.png", "built": "e2e/screenshots/real/a.png"}))
    assert decide(project(tmp_path / "s", results=same_file))["allowed"] is False
    no_real = mutated(lambda d: d["screenshot_check"]["screens"][0].pop("screenshots"))
    assert decide(project(tmp_path / "n", results=no_real))["allowed"] is False


def test_another_screens_genuine_capture_is_not_a_neutralised_pair(tmp_path):
    r = mutated(lambda d: d["screenshot_check_accepted_causes"]["screens"][0].update(neutralised={
        "approved": "e2e/screenshots/screenshot-check/approved/02-b.png", "built": "e2e/screenshots/screenshot-check/built/02-b.png"}))
    root = project(tmp_path, results=r)
    png(root / "e2e" / "screenshots" / "screenshot-check" / "approved" / "02-b.png", SAME)
    png(root / "e2e" / "screenshots" / "screenshot-check" / "built" / "02-b.png", NEUTRAL)
    out = decide(root)
    assert out["allowed"] is False and "capture folder" in " ".join(out["reasons"])


def test_the_package_evidence_folder_and_an_adr_heading_are_not_sources(tmp_path):
    root = project(tmp_path)
    (root / "brief" / "evidence").mkdir()
    (root / "brief" / "evidence" / "mine.md").write_text("the header line shows the mode and the date\n", encoding="utf-8")
    r = mutated(lambda d: d["screenshot_check_accepted_causes"].update(sources={"a": "brief:evidence/mine.md", "b": "ADR-129"}))
    assert decide(project(tmp_path / "e", results=r))["allowed"] is False
    heading = mutated(lambda d: d["screenshot_check_accepted_causes"]["quotes"].update(b="ADR-129: local fonts"))
    assert decide(project(tmp_path / "h", results=heading))["allowed"] is False  # the heading line is not quotable evidence


def test_the_ratio_is_recomputed_from_the_neutralised_pair(tmp_path):
    out = decide(project(tmp_path, built=[(60, 30, 120, 78)]))  # the claim says 0.0, the pair says otherwise
    assert out["allowed"] is False and "recomputed" in " ".join(out["reasons"])


@pytest.mark.parametrize("pair", [None, {}, {"approved": "e2e/screenshots/n/a.png"}, {"approved": "../x.png", "built": "e2e/screenshots/n/b.png"},
                                   {"approved": "e2e/screenshots/n/a.png", "built": "e2e/screenshots/n/missing.png"},
                                   {"approved": "brief/brief.md", "built": "e2e/screenshots/n/b.png"}])
def test_the_attribution_must_name_a_contained_pair(tmp_path, pair):
    def change(d):
        d["screenshot_check_accepted_causes"]["screens"][0]["neutralised"] = pair
    assert decide(project(tmp_path, results=mutated(change)))["allowed"] is False


def test_a_screen_that_still_fails_without_the_causes_is_a_real_mismatch(tmp_path):
    r = mutated(lambda d: d["screenshot_check_accepted_causes"]["screens"][0].update(attributed_diff_ratio_without_accepted_causes=0.4))
    out = decide(project(tmp_path, results=r))
    assert out["allowed"] is False and "real mismatch" in " ".join(out["reasons"])


def test_an_attribution_naming_an_unaccepted_cause_or_for_another_run_is_refused(tmp_path):
    r = mutated(lambda d: d["screenshot_check_accepted_causes"]["screens"][0].update(causes=["a", "z"]))
    assert decide(project(tmp_path, results=r))["allowed"] is False
    r = mutated(lambda d: d["screenshot_check_accepted_causes"]["screens"][0].update(real_diff_ratio=0.2))
    assert "different run" in " ".join(decide(project(tmp_path / "w", results=r))["reasons"])


def test_a_loosened_tolerance_or_a_stale_capture_is_refused(tmp_path):
    assert decide(project(tmp_path, results=mutated(lambda d: d["screenshot_check"].update(tolerance=0.5))))["allowed"] is False
    assert decide(project(tmp_path / "x", results=mutated(lambda d: d["screenshot_check"].update(captured=False))))["allowed"] is False


def test_a_null_or_nonnumeric_tolerance_is_refused_not_a_crash(tmp_path):
    for i, bad in enumerate((None, "0.15", [])):
        r = mutated(lambda d, b=bad: d["screenshot_check"].update(tolerance=b))
        assert decide(project(tmp_path / str(i), results=r))["allowed"] is False


def test_no_recorded_causes_means_ask(tmp_path):
    r = mutated(lambda d: d.pop("screenshot_check_accepted_causes"))
    assert decide(project(tmp_path, results=r))["allowed"] is False


def test_fail_open_shapes_are_refused(tmp_path):
    for i, screens in enumerate(([], ["x"], None)):
        r = mutated(lambda d, s=screens: d["screenshot_check"].update(screens=s))
        assert decide(project(tmp_path / str(i), results=r))["allowed"] is False
    r = mutated(lambda d: d["screenshot_check"].update(screens=[{"mockup": "02-b.html", "status": "pass"}]))
    assert "no failing screen" in " ".join(decide(project(tmp_path / "p", results=r))["reasons"])


@pytest.mark.parametrize("ratio", [float("nan"), -0.1, float("inf"), True])
def test_a_non_finite_or_negative_ratio_is_refused(tmp_path, ratio):
    r = mutated(lambda d: d["screenshot_check_accepted_causes"]["screens"][0].update(attributed_diff_ratio_without_accepted_causes=ratio))
    assert decide(project(tmp_path, results=r))["allowed"] is False


def test_the_reason_never_carries_agent_written_text(tmp_path):
    r = mutated(lambda d: d["screenshot_check_accepted_causes"]["accepted_causes"].update(a='x" $(touch pwned) `y`'))
    out = decide(project(tmp_path, results=r))
    assert out["allowed"] is True and "pwned" not in out["reason"] and '"' not in out["reason"] and "`" not in out["reason"]
    r = mutated(lambda d: d["screenshot_check_accepted_causes"].update(accepted_causes={'a"; x': "t", "b": "t"}, sources={'a"; x': "ADR-129", "b": "ADR-129"}))
    assert decide(project(tmp_path / "q", results=r))["allowed"] is False


def test_the_apply_hook_recheck_covers_the_screenshot_finding_only():
    from orchestrator_pkg import phase_gate

    cfg = {"autonomy": "guided"}
    task = {"phase": "test", "phaseTaskId": "ptk-1"}

    def run(ask, reason):
        hook, _ = phase_gate.override_hook(reason=reason, verdict={"ask": ask, "inform": [], "checked": True})
        hook(cfg, task)

    shot = {"severity": "ask", "message": SHOT_MSG}
    other = {"severity": "ask", "message": "Smoke test failed"}
    with pytest.raises(phase_gate.OverrideRefused):
        run([shot, other], phase_gate.AUTONOMOUS_REASON_PREFIX + " x")
    with pytest.raises(phase_gate.OverrideRefused):
        run([], phase_gate.AUTONOMOUS_REASON_PREFIX + " x")
    with pytest.raises(phase_gate.OverrideRefused):  # the screenshot finding alone, but no project root to re-run the rule in
        run([shot], phase_gate.AUTONOMOUS_REASON_PREFIX + " x")


def test_the_apply_hook_reruns_the_rule(tmp_path):
    from orchestrator_pkg import phase_gate
    from orchestrator_pkg.autonomous_hook import by_rule_refusal

    ask = [{"severity": "ask", "message": SHOT_MSG}]
    refused, _ = phase_gate.override_hook(reason=phase_gate.AUTONOMOUS_REASON_PREFIX + " x", verdict={"ask": ask, "inform": [], "checked": True},
                                          project_root=project(tmp_path / "bad", built=SAME))
    with pytest.raises(phase_gate.OverrideRefused):
        refused({"autonomy": "guided"}, {"phase": "test", "phaseTaskId": "ptk-1"})
    assert by_rule_refusal(project(tmp_path / "ok"), ask) is None


def test_cli_exit_code_and_json(tmp_path, capsys, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setattr(ao, "gate_asks", lambda r: [SHOT_MSG])
    monkeypatch.setattr(sys, "argv", ["x", "--project-root", str(root)])
    assert ao.main() == 0
    assert json.loads(capsys.readouterr().out)["allowed"] is True
    (root / "shipwright_run_config.json").write_text(json.dumps({"autonomy": "guided"}), encoding="utf-8")
    assert ao.main() == 1


def test_the_run_loop_points_at_the_rule_and_keeps_it_narrow():
    ref = Path(__file__).resolve().parent.parent / "skills" / "run" / "references" / "single-session-loop.md"
    flat = " ".join(ref.read_text(encoding="utf-8").split())
    assert "Autonomous override rule" in flat and "autonomous_override.py" in flat
    assert "Never brief a phase-runner to call it" in flat and "never use it for any other finding" in flat
