"""PR #876 regression: the promoter must leave the advisory adopted spec alone.

Four integration guards pin every ``Layers`` cell of ``01-adopted/spec.md`` to
``(inferred)`` (SPEC 6.2). The promoter used to rewrite 16 of them from
CI-confirmed evidence, so each iterate re-opened a PR those guards rejected.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.promote_required_layers as mod  # noqa: E402
from scripts.ci_execution_evidence import ExecutionEvidence  # noqa: E402
from scripts.lib.fr_table_shape import FR_TABLE_HEADER, FR_TABLE_SEPARATOR  # noqa: E402
from scripts.lib.layer_promotion import SKIP_ADVISORY_SPEC, evaluate_fr  # noqa: E402
from scripts.lib.layer_promotion_ledger import ledger_path  # noqa: E402
from scripts.lib.layer_promotion_policy import is_advisory_spec  # noqa: E402

_LINK = {"id": "t", "path": "t", "layer": "unit", "status": "enabled", "executed": "pass"}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(  # nosec B603,B607 - fixed argv, shell=False, test helper
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, shell=False, check=True,
    )


def _project(tmp_path: Path, split: str) -> tuple[Path, str, ExecutionEvidence]:
    spec_rel = f".shipwright/planning/{split}/spec.md"
    reqs = {
        f"01::FR-01.{n:02d}": {
            "id": f"FR-01.{n:02d}", "spec_path": spec_rel, "status": "active",
            "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
            "tests": {"unit": [_LINK]}, "coverage": {"unit": "ok"},
        }
        for n in range(1, 4)
    }
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "compliance" / "test-traceability.json").write_text(
        json.dumps({"schema_version": 4, "requirements": reqs}), encoding="utf-8",
    )
    rows = [
        f"| FR-01.{n:02d} | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
        for n in range(1, 4)
    ]
    spec = tmp_path / spec_rel
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "\n".join(["# Spec", "", "## Functional Requirements", "",
                   FR_TABLE_HEADER, FR_TABLE_SEPARATOR, *rows, ""]),
        encoding="utf-8",
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    ci = {k: {"tests": v["tests"], "coverage": v["coverage"]} for k, v in reqs.items()}
    return tmp_path, spec_rel, ExecutionEvidence("confirmed", "test", 1, ci)


@pytest.mark.covers("FR-01.10")
def test_the_adopted_spec_is_not_rewritten_and_no_ledger_is_created(tmp_path, monkeypatch, capsys):
    project, spec_rel, evidence = _project(tmp_path, "01-adopted")
    monkeypatch.setattr(mod, "resolve_execution_evidence", lambda *a, **k: evidence)
    before = (project / spec_rel).read_text(encoding="utf-8")

    assert mod.main(["--project-root", str(project), "--run-id", "iterate-2026-10-10-x"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["promoted"] == []
    assert {s["reason_code"] for s in out["skipped"]} == {"advisory_spec_never_promoted"}
    assert (project / spec_rel).read_text(encoding="utf-8") == before
    assert not ledger_path(project).exists()


@pytest.mark.covers("FR-01.10")
def test_the_same_evidence_still_promotes_in_any_other_spec(tmp_path, monkeypatch, capsys):
    project, spec_rel, evidence = _project(tmp_path, "02-feature")
    monkeypatch.setattr(mod, "resolve_execution_evidence", lambda *a, **k: evidence)

    assert mod.main(["--project-root", str(project), "--run-id", "iterate-2026-10-10-x"]) == 0

    assert len(json.loads(capsys.readouterr().out)["promoted"]) == 3
    assert "(inferred)" not in (project / spec_rel).read_text(encoding="utf-8")


def _fr(spec_path):
    return {
        "id": "FR-01.11", "spec_path": spec_path, "status": "active",
        "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
        "tests": {"unit": [_LINK]}, "coverage": {"unit": "ok"},
    }


@pytest.mark.covers("FR-01.10")
def test_evaluate_fr_skips_the_adopted_spec_but_still_promotes_elsewhere():
    skipped = evaluate_fr(_fr(".shipwright/planning/01-adopted/spec.md"), is_collision=False)
    assert skipped == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_ADVISORY_SPEC}
    promoted = evaluate_fr(_fr(".shipwright/planning/02-feature/spec.md"), is_collision=False)
    assert promoted["action"] == "promote"


@pytest.mark.covers("FR-01.10")
@pytest.mark.parametrize("path,expected", [
    (None, False), ("", False), ("spec.md", False),
    ("01-adopted/spec.md", True),
    (r".shipwright\planning\01-adopted\spec.md", True),
    (".shipwright/planning/01-adopted-x/spec.md", False),
    (".shipwright/planning/02-feature/spec.md", False),
])
@pytest.mark.covers("FR-01.10")
def test_is_advisory_spec_path_matching(path, expected):
    assert is_advisory_spec(path) is expected
