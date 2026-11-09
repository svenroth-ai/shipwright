"""I10 - FRs that can still be split (atomic-frs U1): advisory, never red, listed with the group count."""

from __future__ import annotations

import pytest

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_i  # noqa: E402

_SPEC = """## 2. Functional Requirements

| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-01.01 | Reports and reminders | Must | Exports reports and sends reminders. | `x` | unit |
| FR-01.02 | Ledger postings | Must | Posts entries to the ledger. | `y` | unit |

### FR-01.01 - Reports and reminders

- (E) [AC01] Given a finished month, when the owner exports the ledger report, then a PDF file is produced.
- (E) [AC02] Given a ledger report export, when a booking has no category, then it is listed as uncategorised.
- (E) [AC03] Given a ledger report export, when a month has no bookings, then the export says the month is empty.
- (E) [AC04] Given an overdue invoice, when the reminder mail is sent, then the customer receives one message.
- (E) [AC05] Given a sent reminder, when the customer already paid, then no further message is sent.
- (E) [AC06] Given a reminder mail, when the customer address bounces, then the reminder is marked undelivered.

### FR-01.02 - Ledger postings

- (E) [AC01] Given the booking posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC02] Given the refund posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC03] Given the deposit posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC04] Given the interest posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC05] Given the invoice posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC06] Given the payment posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC07] Given the balance posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC08] Given the currency posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC09] Given the account posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC10] Given the period posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC11] Given the audit posting rule, when the ledger posts an entry, then the ledger stays consistent.
- (E) [AC12] Given the statement posting rule, when the ledger posts an entry, then the ledger stays consistent.
"""


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _project(root: Path) -> None:
    _w(root, ".shipwright/planning/01-core/spec.md", _SPEC)
    _w(root, "src/exporter.py", "")
    _w(root, "src/mailer.py", "")
    _w(root, "src/ledger.py", "")
    _w(root, "tests/test_export.py", 'from src.exporter import x\n# FR-01.01.AC01\ndef test_a():\n    # FR-01.01.AC02 FR-01.01.AC03\n    pass\n')
    _w(root, "tests/test_mail.py", 'from src.mailer import x\ndef test_b():\n    # FR-01.01.AC04 FR-01.01.AC05 FR-01.01.AC06\n    pass\n')
    # the large single capability: twelve criteria over three test files that all touch the ledger module
    for n in range(3):
        refs = " ".join(f"FR-01.02.AC{k:02d}" for k in range(n * 4 + 1, n * 4 + 5))
        _w(root, f"tests/test_ledger_{n}.py", f"from src.ledger import x\ndef test_c():\n    # {refs}\n    pass\n")


@pytest.mark.covers("FR-01.10")
def test_i10_lists_the_splittable_fr_with_evidence_and_leaves_the_large_single_capability_alone(tmp_path):
    _project(tmp_path)
    f = {f.check_id: f for f in group_i.run(tmp_path, None, None)}["I10"]
    assert f.status == "pass" and "advisory" in f.detail  # never red
    assert "1 splittable" in f.detail and "FR-01.01 (6 criteria, 2 groups by test files: " in f.detail
    assert "test_export.py" in f.detail and "exporter.py" in f.detail and "test_mail.py" in f.detail  # evidence, not just counts
    assert "FR-01.02" not in f.detail.split("with no evidence")[0]  # 12 criteria, one connected capability: not flagged


@pytest.mark.covers("FR-01.10")
def test_i10_says_no_evidence_when_nothing_is_bound_to_a_test(tmp_path):
    _w(tmp_path, ".shipwright/planning/01-core/spec.md", _SPEC)
    f = {f.check_id: f for f in group_i.run(tmp_path, None, None)}["I10"]
    assert f.status == "pass" and "0 splittable" in f.detail and "2 of 2 with no evidence" in f.detail
    assert "too little evidence" not in f.detail  # partial evidence is counted apart from no evidence
    assert "not clean" in f.detail  # thin evidence must not read as a clean bill


@pytest.mark.covers("FR-01.10")
def test_i10_says_could_not_read_instead_of_reading_clean(tmp_path):
    from scripts.audit.group_i_clusters import splittable_report
    _w(tmp_path, ".shipwright/planning/01-core/spec.md", "Some prose that declares no requirement this check can parse.\n")
    status, detail = splittable_report(tmp_path)
    assert status == "skip" and detail.startswith("could not read")


@pytest.mark.covers("FR-01.10")
def test_i10_counts_partial_evidence_apart_from_no_evidence(tmp_path):
    from scripts.audit.group_i_clusters import splittable_report
    _project(tmp_path)
    (tmp_path / "tests/test_ledger_2.py").unlink()  # FR-01.02: 8 of 12 bound is enough; drop two more files -> 4 of 12 = partial
    (tmp_path / "tests/test_ledger_1.py").unlink()
    status, detail = splittable_report(tmp_path)
    assert status == "pass" and "1 with too little evidence" in detail and "0 of 2 with no evidence" in detail


@pytest.mark.covers("FR-01.10")
def test_i10_separates_a_broken_loader_from_an_unreadable_catalog(tmp_path, monkeypatch):
    from scripts.audit import group_i_clusters as g
    _project(tmp_path)

    def boom(name):
        raise ModuleNotFoundError("No module named 'lib.ac_surface'")
    monkeypatch.setattr(g, "load_shared_lib", boom)
    status, detail = g.splittable_report(tmp_path)
    assert status == "skip" and detail.startswith("I10 broken (cannot load its modules)") and "could not read" not in detail

    class _Cat:
        @staticmethod
        def load_catalog(_root):
            raise OSError("disk gone")
    monkeypatch.setattr(g, "load_shared_lib", lambda name: _Cat)
    status, detail = g.splittable_report(tmp_path)
    assert status == "skip" and detail.startswith("could not read") and "OSError" in detail


@pytest.mark.covers("FR-01.10")
def test_i10_an_internal_fault_is_a_distinct_skip_never_a_crash_or_clean(tmp_path, monkeypatch):
    from scripts.audit import group_i_clusters as g
    _project(tmp_path)
    real = g.load_shared_lib

    class _Broken:
        @staticmethod
        def cluster_frs(*_a, **_k):
            raise KeyError("verdict")

    monkeypatch.setattr(g, "load_shared_lib", lambda name: _Broken if name == "fr_clusters" else real(name))
    status, detail = g.splittable_report(tmp_path)
    assert status == "skip" and detail.startswith("I10 broken (internal error)") and "KeyError" in detail
