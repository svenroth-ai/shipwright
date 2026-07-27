"""I6 as a Group I finding — the wiring, not the parser.

The parser's own shape cases live in ``test_group_i_criteria*.py``. What is
asserted here is the contract I6 has with the audit as a whole:

- it is **advisory** — `AuditReport.any_fail` is driven by ``status == "fail"``,
  so an I6 that failed would flip ``run_audit``'s exit code and the dashboard
  verdict for every project carrying an unelaborated requirement. The decided
  rule keeps the too-broad judgement human, so the signal must not read as a
  verdict;
- it **skips** rather than passes when there are no rows to judge, matching
  every other check in the group;
- it never reports a **retired** requirement, which is history rather than
  unfinished work.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_i  # noqa: E402

_SPEC_WITH_A_GAP = """\
## 2. Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.01 | Core | Login | Must | The system SHALL authenticate a user. | interview | unit |
| FR-01.02 | Core | Signup | Must | The system SHALL register a user. | interview | unit |

## Acceptance Criteria

### FR-01.01 — Login

- (E) Given valid credentials, when submitted, then a session starts.
"""

_SPEC_WITH_RETIRED = """\
## 2. Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.01 | Core | Login | Must | The system SHALL authenticate a user. | interview | unit |

### Removed Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.02 | Core | Social login | Should | The system SHOULD allow Google sign-in. | interview | unit |

## Acceptance Criteria

### FR-01.01 — Login

- (E) Given valid credentials, when submitted, then a session starts.
"""


def _spec(root: Path, body: str, split: str = "01-adopted") -> Path:
    d = root / ".shipwright" / "planning" / split
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")
    return root


def _findings(root: Path) -> dict:
    return {f.check_id: f for f in group_i.run(root, None, None)}


def test_i6_is_registered():
    ids = {cid for cid, _name, _sev in group_i._CHECKS}
    assert "I6" in ids


def test_i6_reports_the_requirement_without_criteria(tmp_path: Path):
    f = _findings(_spec(tmp_path, _SPEC_WITH_A_GAP))["I6"]
    assert "FR-01.02" in f.detail
    assert "FR-01.01" not in f.detail


def test_i6_never_fails(tmp_path: Path):
    """Load-bearing: a failing finding would flip the audit exit code."""
    f = _findings(_spec(tmp_path, _SPEC_WITH_A_GAP))["I6"]
    assert f.status == "pass"
    assert f.detail.startswith("advisory")


def test_i6_passes_cleanly_when_every_row_is_elaborated(tmp_path: Path):
    elaborated = _SPEC_WITH_A_GAP + "\n### FR-01.02 — Signup\n\n- (E) Given ... then ...\n"
    f = _findings(_spec(tmp_path, elaborated))["I6"]
    assert f.status == "pass"
    assert "no FR(s) with no acceptance criteria found" in f.detail


def test_i6_skips_without_rows(tmp_path: Path):
    """No spec on disk → skip, like every other check in the group."""
    f = _findings(tmp_path)["I6"]
    assert f.status == "skip"


def test_retired_rows_excluded(tmp_path: Path):
    """A removed requirement is history, not an unelaborated one."""
    f = _findings(_spec(tmp_path, _SPEC_WITH_RETIRED))["I6"]
    assert f.status == "pass"
    assert "FR-01.02" not in f.detail


def test_i6_does_not_change_the_group_verdict(tmp_path: Path):
    """The gap must not make any other check fail, nor I6 itself."""
    findings = _findings(_spec(tmp_path, _SPEC_WITH_A_GAP))
    assert not any(f.status == "fail" for f in findings.values())


def test_moved_row_scanner_still_reachable_from_group_i(tmp_path: Path):
    """The §5.4 pure move must not break the established entry point."""
    _spec(tmp_path, _SPEC_WITH_A_GAP)
    assert [r.id for r in group_i.scan_fr_rows(tmp_path)] == ["FR-01.01", "FR-01.02"]
    assert group_i.scan_specs(tmp_path).state == "rows"
    assert group_i.FrRow(
        id="FR-01.01", name="n", description="d", split="s", spec_path="p",
    ).id == "FR-01.01"
