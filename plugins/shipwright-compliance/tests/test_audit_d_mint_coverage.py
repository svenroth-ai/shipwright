"""D1 / D3 — a change that MINTS a requirement covers and delivers it.

Split out of ``test_audit_groups_a_d.py`` (iterate-2026-07-21): that module sits
far above the 300-line ceiling, so growing it would ratchet the bloat baseline
the wrong way. Same precedent as ``_group_d_link_proof.py``.

**The defect.** The writer (``shared/scripts/lib/fr_gates.py``) accepts a change
naming a requirement under ``new_frs`` ALONE as complete linkage, but D1/D3
recognised coverage/delivery only via ``affected_frs`` — so the change that
CREATES a requirement was invisible to both, and one correct on the first try
stayed flagged forever for never being revised. Surfaced on ``FR-01.15``, the
only requirement ever minted in this repo's 505 events (``evt-edcf1064``, #368).

**What ``tests.total > 0`` does NOT buy:** ``tests`` is the run's whole-suite
total, not per-FR evidence, so it cannot prove the requirement works — it only
keeps the relaxation from being unconditional, leaving a *recording-omission*
check. Per-FR evidence is D1's job via the manifest link proof, pinned by
``test_d1_still_drops_an_explicit_fr_without_a_passing_link``. Two deliberate
asymmetries are pinned too: the ``affected_frs`` path has no test gate
(pre-existing), and the guard is per-EVENT not per-FR. Full rationale in
``.shipwright/planning/iterate/iterate-2026-07-21-fr0115-coverage-bloat.md``.

Hermetic: every fixture is built under ``tmp_path``.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_d  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (kept local so this module stands alone)
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _spec_with_frs(frs: list[tuple[str, str, str]]) -> str:
    rows = "\n".join(f"| {fr_id} | {text} | {prio} |" for fr_id, text, prio in frs)
    return f"# Spec\n\n| FR | Description | Priority |\n| --- | --- | --- |\n{rows}\n"


def _fixture(tmp_path: Path, tests: dict) -> None:
    """A spec carrying FR-01.15 plus a single event that MINTS it."""
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.15", "Cross-repo output contract", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-07-14T16:33:13+00:00",
         "new_frs": ["FR-01.15"], "tests": tests},
    ])


def _manifest(tmp_path: Path, *, source: str) -> None:
    """A schema-valid v3 manifest in which FR-01.15 has NO passing test link.

    Must satisfy ``traceability_schema.json`` exactly: ``load_manifest`` is
    fail-closed, so a near-miss shape silently disables the link proof and the
    test passes for the wrong reason (this fixture cost two such rounds).
    """
    _write(
        tmp_path / ".shipwright" / "compliance" / "test-traceability.json",
        json.dumps({
            "schema_version": 3,
            "collector_version": "1",
            "generated_at": "2026-07-21T00:00:00+00:00",
            "source_commit": "0" * 40,
            "spec_hash": "0" * 12,
            "requirements": {
                "01::FR-01.15": {
                    "id": "FR-01.15",
                    "spec_path": ".shipwright/planning/01-foo/spec.md",
                    "title": "Cross-repo output contract",
                    "priority": "Must",
                    "status": "active",
                    "required_layers": ["unit"],
                    "required_layers_source": source,
                    "tests": {},
                    "coverage": {"unit": "MISSING"},
                },
            },
            "orphans": [],
            "invalid_tags": [],
            "untagged_tests": [],
        }),
    )


def _finding(tmp_path: Path, check_id: str):
    return next(
        f for f in group_d.run(tmp_path, None, None) if f.check_id == check_id
    )


# ---------------------------------------------------------------------------
# AC1 / AC2 — a tested mint covers and delivers
# ---------------------------------------------------------------------------


def test_d1_counts_a_tested_mint_as_coverage(tmp_path):
    """AC1: the change that introduces a requirement covers it."""
    _fixture(tmp_path, {"passed": 4889, "total": 4889})

    d1 = _finding(tmp_path, "D1")
    assert d1.status == "pass", d1.detail


def test_d3_counts_a_tested_mint_as_delivery(tmp_path):
    """AC2: ``work_completed`` means the work is done, so naming a requirement as
    newly-created on it reads "introduced AND delivered", not "promised for
    later". Requiring a separate later affirmation flagged forever any
    requirement that was right the first time."""
    _fixture(tmp_path, {"passed": 4889, "total": 4889})

    d3 = _finding(tmp_path, "D3")
    assert d3.status == "pass", d3.detail
    # The message is audit output a reader acts on, so pin that it states the
    # new rule rather than the old "follow-up affected_frs event" wording.
    assert "tested mint" in d3.detail


# ---------------------------------------------------------------------------
# AC3 — the tests guard survives (the relaxation is not a loophole)
# ---------------------------------------------------------------------------


def test_d1_does_not_count_an_untested_mint_as_coverage(tmp_path):
    """AC3: minting a requirement in a 0/0 docs commit must not mark it covered,
    or the TT2 hardening would be dodgeable by filing under the other key."""
    _fixture(tmp_path, {"passed": 0, "total": 0})

    d1 = _finding(tmp_path, "D1")
    assert d1.status == "fail"
    assert "FR-01.15" in d1.detail


def test_d3_does_not_count_an_untested_mint_as_delivery(tmp_path):
    """AC3, delivery side: without this guard D3 could never fail again, since
    every promise would deliver itself the instant it was made."""
    _fixture(tmp_path, {"passed": 0, "total": 0})

    d3 = _finding(tmp_path, "D3")
    assert d3.status == "fail"
    assert "FR-01.15" in d3.detail


# ---------------------------------------------------------------------------
# The link proof (the guard that does the real work), eligibility, asymmetries
# ---------------------------------------------------------------------------


def test_d1_still_drops_an_explicit_fr_without_a_passing_link(tmp_path):
    """A minted FR with EXPLICIT provenance still owes a manifest test link.

    This — not ``tests.total > 0`` — is what stops the new path from marking a
    requirement covered without per-FR evidence. FR-01.15 itself passes only
    because ``inferred_legacy`` is exempt.
    """
    _fixture(tmp_path, {"passed": 4889, "total": 4889})
    _manifest(tmp_path, source="explicit")

    d1 = _finding(tmp_path, "D1")
    assert d1.status == "fail"
    assert "FR-01.15" in d1.detail


def test_an_ineligible_event_type_never_covers_or_delivers(tmp_path):
    """Only ``work_completed`` counts: a planning event carrying ``new_frs`` and
    a healthy test total satisfies neither check. The second, genuine event is
    needed so D1 actually runs — with no eligible event it returns SKIP and the
    assertion would pass vacuously."""
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([
            ("FR-01.15", "Cross-repo output contract", "Must"),
            ("FR-01.10", "Compliance", "Must"),
        ]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "spec_updated", "ts": "2026-07-14T16:33:13+00:00",
         "new_frs": ["FR-01.15"], "tests": {"passed": 10, "total": 10}},
        {"type": "work_completed", "ts": "2026-07-15T00:00:00+00:00",
         "affected_frs": ["FR-01.10"], "tests": {"passed": 10, "total": 10}},
    ])

    d1 = _finding(tmp_path, "D1")
    assert d1.status == "fail"
    assert "FR-01.15" in d1.detail
    # No promise was ever recorded on an eligible event, so D3 has nothing to judge.
    assert _finding(tmp_path, "D3").status == "skip"


def test_affected_frs_path_has_no_test_gate(tmp_path):
    """Documented asymmetry #1: D3's ``affected_frs`` path never gated on tests
    and still does not — the new path is stricter, not looser. Pinned so the
    inconsistency is a recorded decision, not a latent surprise."""
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.15", "Cross-repo output contract", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-07-14T16:33:13+00:00",
         "new_frs": ["FR-01.15"], "affected_frs": ["FR-01.15"],
         "tests": {"passed": 0, "total": 0}},
    ])

    # Delivered via the ungated affected_frs path despite 0/0 …
    assert _finding(tmp_path, "D3").status == "pass"
    # … while D1, which gates BOTH keys on tests, still refuses it.
    assert _finding(tmp_path, "D1").status == "fail"


def test_guard_is_per_event_not_per_fr(tmp_path):
    """Documented asymmetry #2: one suite total covers the whole event, so an
    untested mint alongside a tested change rides along. Accepted (mints run
    ~1-in-505) and pinned rather than left undocumented."""
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([
            ("FR-01.15", "Cross-repo output contract", "Must"),
            ("FR-01.10", "Compliance", "Must"),
        ]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-07-14T16:33:13+00:00",
         "new_frs": ["FR-01.15"], "affected_frs": ["FR-01.10"],
         "tests": {"passed": 12, "total": 12}},
    ])

    assert _finding(tmp_path, "D1").status == "pass"
    assert _finding(tmp_path, "D3").status == "pass"


def test_non_dict_tests_does_not_crash_the_checks(tmp_path):
    """A hand-edited or union-merged log can carry a non-dict ``tests``. Both
    checks must read it as untested rather than raise — run()'s blanket except
    would turn that into a synthetic HIGH finding for the whole check."""
    _fixture(tmp_path, "not-a-dict")

    assert _finding(tmp_path, "D1").status == "fail"
    assert _finding(tmp_path, "D3").status == "fail"


# ---------------------------------------------------------------------------
# The overlay mechanism: a tests-only patch must not disturb anything else
# ---------------------------------------------------------------------------


def test_a_tests_only_amendment_preserves_classification_and_timestamp():
    """The FR-01.15 correction (evt-ca8ff116 amending evt-edcf1064) supplies the
    ``tests`` block F5b omitted and nothing more. Amending is defensible only
    because the ``new_frs`` classification was already correct and just the
    evidence was missing, so the fold must leave ``new_frs``, ``ts`` and the
    event identity untouched — an overlay that widened would fabricate delivery.
    """
    original = {
        "id": "evt-edcf1064", "type": "work_completed",
        "ts": "2026-07-14T16:33:13.466664+00:00",
        "new_frs": ["FR-01.15"], "spec_impact": "add",
        "adr_id": "iterate-2026-07-14-webui-render-contract",
    }
    amendment = {
        "id": "evt-ca8ff116", "type": "event_amended", "amends": "evt-edcf1064",
        "ts": "2026-07-21T21:55:14+00:00",
        "fields": {"tests": {"passed": 4889, "total": 4889}},
    }

    folded = group_d.events_amend.apply_amendments([original, amendment])
    target = next(e for e in folded if e.get("id") == "evt-edcf1064")

    assert target["tests"] == {"passed": 4889, "total": 4889}   # supplied
    assert target["ts"] == original["ts"]                       # NOT retimed
    assert target["new_frs"] == ["FR-01.15"]                    # NOT reclassified
    assert target["spec_impact"] == "add"
    assert target["adr_id"] == original["adr_id"]
    # Exactly one key gained; nothing else moved.
    assert set(target) - set(original) == {"tests"}
