"""``check_ac_coverage_ratchet.py`` — P3.7 feeder (a), "AC without a test",
anti-ratcheted (SPEC §8 E2). Real git repo (``_keystone_repo.py``, shared with
the P3.6 keystone-gate tests) — no mocked reader.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_ac_coverage_ratchet as ratchet  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import make_repo  # noqa: E402

_TOOLS = Path(__file__).resolve().parents[1]


def _run(root: Path, argv: list[str], capsys) -> tuple[int, dict]:
    code = ratchet.main(["--project-root", str(root), *argv])
    payload = json.loads(capsys.readouterr().out)
    return code, payload


def _all_bound_manifest() -> dict:
    """Every one of the three BASE_SPEC ACs carries a passing link."""
    link = [{"id": "tests/test_widget.py::test_it", "layer": "unit",
             "status": "enabled", "executed": "pass"}]
    return {
        "requirements": {
            "ns::FR-01.01": {
                "id": "FR-01.01", "status": "active", "spec_path": "docs/spec.md",
                "acs": {"AC01": {"tests": {"unit": link}}, "AC02": {"tests": {"unit": link}}},
            },
            "ns::FR-01.02": {
                "id": "FR-01.02", "status": "active", "spec_path": "docs/spec.md",
                "acs": {"AC03": {"tests": {"unit": link}}},
            },
        },
    }


def test_no_baseline_and_no_unbound_is_clean(capsys, tmp_path):
    # Every AC bound -> nothing unbound -> nothing to ratchet regardless of baseline.
    root = make_repo(tmp_path, manifest_obj=_all_bound_manifest())
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_OK
    assert payload["status"] == "clean"
    assert payload["new_unbound"] == []


def test_unbound_ac_with_no_baseline_at_all_is_a_ratchet(capsys, tmp_path):
    """No baseline file on disk = an empty grandfathered set, so EVERY unbound
    AC is new — matches the family's fail-CLOSED default for an absent
    artifact THIS gate itself owns (unlike a bloat baseline this repo already
    ships, a coverage baseline that was never committed is not "nothing to
    check", it is "check against nothing grandfathered")."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_BLOCKED
    assert payload["status"] == "blocked"
    assert "FR-01.01/AC01" in payload["new_unbound"]
    assert "FR-01.01/AC02" in payload["new_unbound"]
    assert "FR-01.02/AC03" in payload["new_unbound"]


def test_a_baselined_unbound_ac_does_not_block(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    baseline = root / ratchet.BASELINE_RELPATH
    baseline.write_text(json.dumps({
        "unbound": ["FR-01.01/AC01", "FR-01.01/AC02", "FR-01.02/AC03"],
    }), encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_OK
    assert payload["status"] == "clean"
    assert payload["baseline_count"] == 3


def test_a_new_unbound_ac_outside_a_partial_baseline_still_blocks(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    baseline = root / ratchet.BASELINE_RELPATH
    baseline.write_text(json.dumps({"unbound": ["FR-01.01/AC01"]}), encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_BLOCKED
    assert payload["new_unbound"] == ["FR-01.01/AC02", "FR-01.02/AC03"]


def test_binding_a_baselined_ac_reports_it_resolved_and_does_not_block(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=True))
    baseline = root / ratchet.BASELINE_RELPATH
    baseline.write_text(json.dumps({
        "unbound": ["FR-01.01/AC01", "FR-01.01/AC02", "FR-01.02/AC03"],
    }), encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_OK
    assert payload["resolved_since_baseline"] == ["FR-01.01/AC01"]


def test_write_mode_regenerates_the_baseline_from_current_state(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    code, payload = _run(root, ["--write"], capsys)
    assert code == ratchet.EXIT_OK
    assert payload["status"] == "baseline_written"
    written = json.loads((root / ratchet.BASELINE_RELPATH).read_text(encoding="utf-8"))
    assert written["unbound"] == ["FR-01.01/AC01", "FR-01.01/AC02", "FR-01.02/AC03"]
    assert written["schema_version"] == ratchet.BASELINE_SCHEMA_VERSION
    # And the freshly-written baseline is immediately clean against itself.
    code2, payload2 = _run(root, [], capsys)
    assert code2 == ratchet.EXIT_OK
    assert payload2["status"] == "clean"


def test_a_baseline_missing_schema_version_is_still_accepted(capsys, tmp_path):
    """Backward compatible: a baseline predating the `schema_version` key is
    treated as version 1 (today's only version), not rejected."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    (root / ratchet.BASELINE_RELPATH).write_text(json.dumps({
        "unbound": ["FR-01.01/AC01", "FR-01.01/AC02", "FR-01.02/AC03"],
    }), encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_OK


def test_an_unrecognised_schema_version_is_an_infra_fault(capsys, tmp_path):
    """External plan review (glm, low): a future format change must not be
    silently misread as today's flat string list."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / ratchet.BASELINE_RELPATH).write_text(json.dumps({
        "schema_version": 99, "unbound": [],
    }), encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_INFRA
    assert payload["status"] == "infra_fault"


def test_a_corrupt_baseline_fails_closed_not_open(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / ratchet.BASELINE_RELPATH).write_text("not json", encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_INFRA
    assert payload["status"] == "infra_fault"


def test_an_unreadable_manifest_is_an_infra_fault(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / ratchet.MANIFEST_RELPATH).write_text("not json", encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_INFRA
    assert payload["status"] == "infra_fault"


def test_the_cli_starts_and_exits_cleanly_as_a_real_subprocess(tmp_path):
    """Deliberately the ONLY subprocess case in this module (house convention,
    ``test_keystone_gate_infra.py``): proves the module's own ``sys.path``
    bootstrap works outside pytest's collection side effects."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    done = subprocess.run(
        [sys.executable, str(_TOOLS / "check_ac_coverage_ratchet.py"), "--project-root", str(root)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert done.returncode == ratchet.EXIT_BLOCKED, done.stderr
    assert json.loads(done.stdout)["status"] == "blocked"
