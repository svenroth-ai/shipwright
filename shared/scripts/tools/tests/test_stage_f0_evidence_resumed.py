"""A RESUMED F0 run is staged as resumed-local evidence - never as a full green run.

`suite_resume_report.manifest_extra` marks the retained manifest; `stage_f0_evidence` carries
that marking into the staged provenance sidecar and its own output; the AC-ratchet mirror
says so too. A full run keeps byte-identical behaviour (no marking anywhere).
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.check_ac_ratchet_f0 as ratchet  # noqa: E402
import scripts.tools.stage_f0_evidence as mod  # noqa: E402
from scripts.lib import evidence_drop  # noqa: E402
from scripts.tools.suite_retention import Retention  # noqa: E402
from scripts.tools.suite_units import Unit  # noqa: E402

_RESUMED = {"run_id": "r1", "invocation": "r1@2", "prior_invocations": ["r1@1"],
            "tree_changed_files": 3,
            "units": {"shipwright-x": {"mode": "failed-only", "rerun_tests": ["t::a"]}}}


def _project(tmp_path: Path, extra: dict | None) -> Path:
    root = tmp_path / "project"
    plugin = root / "plugins" / "shipwright-x"
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("", encoding="utf-8")
    retention = Retention(project_root=root, run_id="r1")
    if extra:
        retention.extra.update(extra)
    report = tmp_path / "r.xml"
    report.write_text("<testsuites/>", encoding="utf-8")
    retention.record(Unit(id="shipwright-x", cwd="plugins/shipwright-x", target="tests"),
                     report, "pass")
    retention.publish()
    return root


def _stage(root: Path) -> dict:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        assert mod.main(["--project-root", str(root), "--run-id", "r1",
                         "--head-commit", "abc"]) == mod.EXIT_OK
    return json.loads(out.getvalue())


def test_the_manifest_carries_the_marking_the_runner_gave_it(tmp_path):
    root = _project(tmp_path, {"resumed": _RESUMED})
    run_dir = mod.find_published_run(root, "r1")
    assert mod.published_resumed(run_dir) == _RESUMED
    assert json.loads((run_dir / "manifest.json").read_text())["units"][0]["outcome"] == "pass"


def test_a_resumed_run_is_staged_as_resumed_local_evidence(tmp_path):
    root = _project(tmp_path, {"resumed": _RESUMED})

    payload = _stage(root)

    assert payload["resumed"] is True and payload["staged"] == 1
    prov = evidence_drop.read_provenance(root)
    assert prov["resumed_local"] == _RESUMED
    assert prov["run_id"] == "r1" and prov["reports"]["junit"]  # still valid evidence


def test_a_full_run_is_staged_without_any_marking(tmp_path):
    root = _project(tmp_path, None)

    payload = _stage(root)

    assert payload["resumed"] is False
    assert "resumed_local" not in evidence_drop.read_provenance(root)
    assert mod.published_resumed(mod.find_published_run(root, "r1")) is None


def test_a_fallback_only_manifest_is_not_a_resume(tmp_path):
    root = _project(tmp_path, {"resume_fallback": "gate said no"})
    assert _stage(root)["resumed"] is False


def test_an_unreadable_manifest_reads_as_not_resumed(tmp_path):
    assert mod.published_resumed(tmp_path) is None
    (tmp_path / "manifest.json").write_text("[1]", encoding="utf-8")
    assert mod.published_resumed(tmp_path) is None
    (tmp_path / "manifest.json").write_text('{"resumed": "yes"}', encoding="utf-8")
    assert mod.published_resumed(tmp_path) is None


def test_provenance_extra_never_overrides_the_freshness_keys(tmp_path):
    prov = evidence_drop.stage_reports(
        tmp_path, run_id="real", head_commit="h", junit_reports=[],
        provenance_extra={"run_id": "forged", "head_commit": "forged", "note": "kept"})
    assert (prov["run_id"], prov["head_commit"], prov["note"]) == ("real", "h", "kept")


def test_the_ratchet_mirror_says_when_its_evidence_is_a_resume(tmp_path, capsys, monkeypatch):
    root = _project(tmp_path, {"resumed": _RESUMED})
    (root / "plugins" / "shipwright-compliance").mkdir(parents=True)
    (root / "shipwright_ac_coverage_baseline.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ratchet, "snapshot_tree", lambda *_a: (_ for _ in ()).throw(
        ratchet.RatchetF0Error("stop here: the notice is already printed")))

    assert ratchet.run(root, "r1") == ratchet.EXIT_INFRA
    assert "RESUME" in capsys.readouterr().out
