"""Issue #1035: callers can gate on 'every configured reviewer answered'.

Default behaviour (#670: one opinion is enough) is unchanged; strictness is opt-in via
``external_review.require_all_legs``, ``--require-all-legs`` or ``--min-reviews N``.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _d in (_SCRIPTS / "lib", _SCRIPTS / "tools"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from external_review_degraded import finalize_review_output  # noqa: E402
from external_review_strict import required_reviews, strict_config_flag  # noqa: E402

OK = {"status": "success", "feedback": "x", "via": "openrouter"}
ERR = {"status": "error", "reason": "codex exec exited 1: usage limit", "via": "codex"}
SKIP = {"status": "skipped", "reason": "No key"}


@pytest.mark.covers("FR-01.03/AC23")
def test_expected_count_is_always_reported():
    out, _code = finalize_review_output("codex", {"glm": OK, "openai": ERR})
    assert out["reviews_expected"] == 2
    assert out["reviews_succeeded"] == 1
    assert out["missing_legs"] == ["openai"]


@pytest.mark.covers("FR-01.03/AC23")
def test_default_partial_pass_still_succeeds():
    out, code = finalize_review_output("codex", {"glm": OK, "openai": ERR})
    assert (out["success"], code) == (True, 0)
    assert out["partially_degraded"] is True
    assert "strict_failure" not in out


@pytest.mark.covers("FR-01.03/AC23")
def test_require_all_fails_partial_pass_and_names_legs(capsys):
    out, code = finalize_review_output("codex", {"glm": OK, "openai": ERR}, min_required=2)
    assert code == 1 and out["success"] is False
    assert out["strict_failure"] is True
    assert "openai" in out["strict_reason"] and "1/2" in out["strict_reason"]
    assert "openai" in capsys.readouterr().err


@pytest.mark.covers("FR-01.03/AC23")
def test_skipped_leg_counts_as_missing_under_strictness():
    out, code = finalize_review_output("none", {"glm": OK, "openai": SKIP}, min_required=2)
    assert code == 1 and out["missing_legs"] == ["openai"]


@pytest.mark.covers("FR-01.03/AC23")
def test_full_pass_satisfies_strictness():
    out, code = finalize_review_output("x", {"glm": OK, "openai": OK}, min_required=2)
    assert (out["success"], code) == (True, 0)
    assert "strict_failure" not in out


@pytest.mark.covers("FR-01.03/AC23")
def test_total_failure_keeps_degraded_semantics():
    out, code = finalize_review_output("x", {"glm": ERR, "openai": ERR}, min_required=2)
    assert code == 1 and out["degraded"] is True and out["success"] is False


@pytest.mark.parametrize(
    ("config", "flag", "min_reviews", "expected", "want"),
    [
        ({}, False, None, 2, None),
        ({"external_review": {"require_all_legs": True}}, False, None, 2, 2),
        ({}, True, None, 2, 2),
        ({}, False, 1, 2, 1),
        ({}, False, 3, 2, 3),
        ({"external_review": {"require_all_legs": True}}, False, 1, 2, 2),
        ({"external_review": {"require_all_legs": "yes"}}, False, None, 2, None),
    ],
)
@pytest.mark.covers("FR-01.03/AC23")
def test_required_reviews_resolution(config, flag, min_reviews, expected, want):
    assert required_reviews(config, expected, require_all=flag, min_reviews=min_reviews) == want


@pytest.mark.covers("FR-01.03/AC23")
def test_strict_config_flag_degrades_on_malformed_config():
    assert strict_config_flag({"external_review": []}) is False
    assert strict_config_flag({"external_review": {"require_all_legs": True}}) is True


def _mark(tmp_path, *extra):
    script = _SCRIPTS / "checks" / "mark-review-state.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--planning-dir", str(tmp_path), "--status", "completed", *extra],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)["state"]


@pytest.mark.covers("FR-01.03/AC23")
def test_marker_records_partial_pass(tmp_path):
    state = _mark(tmp_path, "--partial", "--missing-legs", "openai,glm")
    assert state["status"] == "completed"
    assert state["partial"] is True
    assert state["missing_legs"] == ["glm", "openai"]


def _run_mark_in_process(monkeypatch, capsys, tmp_path, *argv):
    import importlib.util

    spec = importlib.util.spec_from_file_location("mark_review_state_under_test", _SCRIPTS / "checks" / "mark-review-state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["mark-review-state.py", "--planning-dir", str(tmp_path), *argv])
    code = module.main()
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.covers("FR-01.03/AC23")
def test_missing_legs_alone_implies_partial(monkeypatch, capsys, tmp_path):
    code, out = _run_mark_in_process(monkeypatch, capsys, tmp_path, "--status", "completed", "--missing-legs", "openai")
    assert code == 0 and out["state"]["partial"] is True


@pytest.mark.covers("FR-01.03/AC23")
def test_partial_without_legs_records_an_empty_list(monkeypatch, capsys, tmp_path):
    code, out = _run_mark_in_process(monkeypatch, capsys, tmp_path, "--status", "completed", "--partial")
    assert code == 0 and out["state"]["partial"] is True and out["state"]["missing_legs"] == []


@pytest.mark.covers("FR-01.03/AC23")
def test_partial_is_refused_on_a_skipped_status(monkeypatch, capsys, tmp_path):
    code, out = _run_mark_in_process(
        monkeypatch, capsys, tmp_path, "--status", "skipped_user_opt_out", "--reason", "offline", "--partial")
    assert code == 2 and out["error"] == "invalid_partial"


@pytest.mark.covers("FR-01.03/AC23")
@pytest.mark.parametrize("bad", ["0", "-1", "x"])
def test_min_reviews_rejects_non_positive_values(bad):
    import argparse

    from external_review_strict import add_strict_arguments

    parser = argparse.ArgumentParser()
    add_strict_arguments(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["--min-reviews", bad])
    assert parser.parse_args(["--min-reviews", "2"]).min_reviews == 2


@pytest.mark.covers("FR-01.03/AC23")
def test_empty_diff_envelope_expects_nothing(monkeypatch):
    """An empty diff needs no review, so succeeded == expected == 0 and no leg counts as missing."""
    from external_review_empty import empty_diff_envelope

    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", raising=False)
    out = empty_diff_envelope("claude", {})
    assert out["reviews_expected"] == 0 and out["reviews_succeeded"] == 0
    assert out["missing_legs"] == [] and out["success"] is True


@pytest.mark.covers("FR-01.03/AC23")
def test_strict_mode_also_fails_the_no_keys_state():
    out, code = finalize_review_output("none", {"glm": SKIP, "openai": SKIP}, min_required=2)
    assert code == 1 and out["success"] is False and out["missing_legs"] == ["glm", "openai"]


@pytest.mark.covers("FR-01.03/AC23")
def test_marker_without_partial_is_unchanged(tmp_path):
    state = _mark(tmp_path)
    assert "partial" not in state and "missing_legs" not in state
