"""``check_ac_coverage_ratchet.py`` — P3.7 feeder (a), "AC without a test",
anti-ratcheted (SPEC §8 E2). Real git repo (``_keystone_repo.py``, shared with
the P3.6 keystone-gate tests) — no mocked reader.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_ac_coverage_ratchet as ratchet  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_all, make_repo  # noqa: E402

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


def test_a_baseline_with_a_non_string_entry_fails_closed(capsys, tmp_path):
    """External code review (glm, medium): a hand-edited/half-migrated
    baseline containing a non-string entry used to be silently filtered out
    of the grandfathered set (a false NEW block, or worse, masked
    corruption). Now it is a non-None error, same as any other malformed
    shape."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / ratchet.BASELINE_RELPATH).write_text(json.dumps({
        "schema_version": 1, "unbound": ["FR-01.01/AC01", 42],
    }), encoding="utf-8")
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_INFRA
    assert payload["status"] == "infra_fault"


def test_check_baseline_growth_blocks_a_same_commit_self_grandfather(capsys, tmp_path):
    """CLI wiring for `--check-baseline-growth`: the flag the push-only step
    in ci.yml passes. `unbound - baselined` alone would read clean here (the
    baseline already contains the newly-unbound AC) — the growth flag is
    what actually catches it."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    baseline = root / ratchet.BASELINE_RELPATH
    baseline.write_text(json.dumps({"unbound": ["FR-01.01/AC01"]}), encoding="utf-8")
    commit_all(root, "parent: only AC01 grandfathered")
    baseline.write_text(json.dumps({
        "unbound": ["FR-01.01/AC01", "FR-01.01/AC02", "FR-01.02/AC03"],
    }), encoding="utf-8")
    commit_all(root, "head: self-grandfather AC02 and AC03 too")

    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_OK and payload["status"] == "clean", (
        "sanity check: the plain comparison must NOT catch this on its own"
    )
    code, payload = _run(root, ["--check-baseline-growth"], capsys)
    assert code == ratchet.EXIT_BLOCKED
    assert payload["status"] == "blocked"
    assert payload["baseline_grew_since_parent"] == ["FR-01.01/AC02", "FR-01.02/AC03"]
    assert payload["new_unbound"] == []


def test_check_baseline_growth_accepts_an_explicit_parent_sha(capsys, tmp_path):
    """`ci.yml` always passes `--parent-sha` (the push event's `before` SHA)
    rather than relying on the HEAD~1 default — prove the CLI actually wires
    it through to the growth diff, not just the default fallback path."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    baseline = root / ratchet.BASELINE_RELPATH
    baseline.write_text(json.dumps({"unbound": ["FR-01.01/AC01"]}), encoding="utf-8")
    before_sha = commit_all(root, "before: the push's real pre-image")
    baseline.write_text(json.dumps({
        "unbound": ["FR-01.01/AC01", "FR-01.01/AC02", "FR-01.02/AC03"],
    }), encoding="utf-8")
    commit_all(root, "push commit 1: self-grandfather AC02 and AC03")
    (root / "README-unrelated.md").write_text("noise", encoding="utf-8")
    commit_all(root, "push commit 2 (the pushed tip): unrelated")

    # HEAD~1 alone (no --parent-sha) is blind to this — it is the earlier
    # commit's OWN grown baseline, so nothing looks new.
    code, payload = _run(root, ["--check-baseline-growth"], capsys)
    assert code == ratchet.EXIT_OK and payload["baseline_grew_since_parent"] == []

    code, payload = _run(root, ["--check-baseline-growth", "--parent-sha", before_sha], capsys)
    assert code == ratchet.EXIT_BLOCKED
    assert payload["baseline_grew_since_parent"] == ["FR-01.01/AC02", "FR-01.02/AC03"]


def test_check_baseline_growth_rejects_combination_with_write(tmp_path):
    """External code review (glm, low): growing computed against a baseline
    the same run is about to overwrite is silently ambiguous — reject it
    loudly rather than let the two flags interact in an undocumented way."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    with pytest.raises(SystemExit) as exc_info:
        ratchet.main(["--project-root", str(root), "--write", "--check-baseline-growth"])
    assert exc_info.value.code == 2


def test_check_baseline_growth_warnings_surface_without_blocking(capsys, tmp_path):
    """The one wiring path (`warnings += growth_warnings`) that had no direct
    coverage (external code review, glm, low): a corrupt PARENT baseline
    warns but must not, by itself, turn a clean push into a blocked one."""
    root = make_repo(tmp_path, manifest_obj=_all_bound_manifest())
    (root / ratchet.BASELINE_RELPATH).write_text("not json", encoding="utf-8")
    commit_all(root, "parent: corrupt baseline")
    (root / ratchet.BASELINE_RELPATH).write_text(json.dumps({"unbound": []}), encoding="utf-8")
    commit_all(root, "head")

    code, payload = _run(root, ["--check-baseline-growth"], capsys)
    assert code == ratchet.EXIT_OK
    assert payload["status"] == "clean"
    assert any("not valid JSON" in w for w in payload["warnings"])


def test_check_baseline_growth_is_clean_when_the_baseline_only_shrank(capsys, tmp_path):
    """Binding an AC (removing it from the baseline) is always welcome per
    the baseline's own `$comment` — must never be flagged as growth."""
    root = make_repo(tmp_path, manifest_obj=_all_bound_manifest())
    baseline = root / ratchet.BASELINE_RELPATH
    baseline.write_text(json.dumps({"unbound": ["FR-01.01/AC02"]}), encoding="utf-8")
    commit_all(root, "parent")
    baseline.write_text(json.dumps({"unbound": []}), encoding="utf-8")
    commit_all(root, "head: AC02 got bound, removed from the baseline")

    code, payload = _run(root, ["--check-baseline-growth"], capsys)
    assert code == ratchet.EXIT_OK
    assert payload["status"] == "clean"
    assert payload["baseline_grew_since_parent"] == []


def test_check_baseline_growth_omitted_leaves_payload_shape_unchanged(capsys, tmp_path):
    """The pull_request invocation never passes the flag — its payload must
    not gain the new key, so an existing consumer parsing this JSON is
    unaffected."""
    root = make_repo(tmp_path, manifest_obj=_all_bound_manifest())
    code, payload = _run(root, [], capsys)
    assert code == ratchet.EXIT_OK
    assert "baseline_grew_since_parent" not in payload


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
