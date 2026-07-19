"""Adopt-phase verifier tests (Phase-Quality A1–A8 canon checks).

The original A3 check hardcoded ``ADR-0001`` as the adoption ADR id.
After the brownfield-numbering fix, /shipwright-adopt picks the next-
free 3-digit id (``max(existing) + 1``), so the verifier must accept
any heading-level + any 3+ digit id with ``Adopt`` in the title — see
the bug report at .shipwright/agent_docs/decision_log.md (the entry
that fixed the shipwright-webui ADR-0053 collision regression).
"""

from __future__ import annotations

from pathlib import Path

from scripts.lib.phase_quality import STATUS_FAIL, STATUS_PASS
from scripts.tools.verifiers.adopt_compliance import check_a3_adoption_adr


def _write_log(tmp_path: Path, body: str) -> Path:
    """Lay down a decision_log.md under the standard agent_docs path."""
    log_dir = tmp_path / ".shipwright" / "agent_docs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "decision_log.md"
    log.write_text(body, encoding="utf-8")
    return log


def test_a3_passes_for_greenfield_adr_001(tmp_path: Path) -> None:
    """Greenfield → adoption ADR is ADR-001 (3-digit zero-padded)."""
    _write_log(
        tmp_path,
        "# Decision Log\n\n"
        "## ADR-001: Adopt this repository into the Shipwright SDLC\n\n"
        "Body.\n",
    )
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_PASS


def test_a3_passes_for_brownfield_next_free_id(tmp_path: Path) -> None:
    """Brownfield with existing ADRs → adoption ADR id = max + 1.
    The verifier must accept the new id (was hardcoded to ADR-0001 before)."""
    _write_log(
        tmp_path,
        "# Decision Log\n\n"
        "## ADR-058: Pre-existing entry\n\nBody.\n\n"
        "## ADR-059: Adopt this repository into the Shipwright SDLC\n\n"
        "Adoption decision.\n",
    )
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_PASS


def test_a3_passes_for_legacy_4_digit_id(tmp_path: Path) -> None:
    """Older Shipwright outputs used 4-digit ADR-0001 — still valid for
    repos onboarded before the brownfield fix landed."""
    _write_log(
        tmp_path,
        "## ADR-0001: Adopt this repository into the Shipwright SDLC\n",
    )
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_PASS


def test_a3_passes_for_h3_compact_format(tmp_path: Path) -> None:
    """The compact H3 form is canonical for downstream ADRs and must
    also be accepted as the adoption-ADR heading."""
    _write_log(
        tmp_path,
        "### ADR-001: Adopt this repository\n\nBody.\n",
    )
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_PASS


def test_a3_fails_when_no_adoption_adr(tmp_path: Path) -> None:
    """A log full of unrelated ADRs but no 'Adopt' title must fail."""
    _write_log(
        tmp_path,
        "## ADR-001: Use Postgres\n\nBody.\n\n"
        "## ADR-002: Pick monorepo\n\nBody.\n",
    )
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_FAIL


def test_a3_fails_when_log_missing(tmp_path: Path) -> None:
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_FAIL


def test_a3_does_not_match_under_3_digit_id(tmp_path: Path) -> None:
    """1- and 2-digit ids predate Shipwright's canon. The A3 check
    treats them as non-canonical so the operator surfaces the issue
    before downstream RTM/SBOM consumers do."""
    _write_log(
        tmp_path,
        "## ADR-1: Adopt this repository\n\nBody.\n",
    )
    finding = check_a3_adoption_adr(tmp_path)
    assert finding["status"] == STATUS_FAIL


# ---------------------------------------------------------------------------
# Integration: adopt's rendered decision_log.md round-trips through the
# shared `parse_adr_headers` consumer used by G3 + F1/F2/F3 audits.
# This is the contract that was silently broken before the H2→H3 switch:
# adopt wrote H2 with colon, but `_ADR_COMPACT_HEADER_RE` requires H3 and
# `_ADR_OLD_HEADER_RE` requires H2 with pipes — so neither matched and
# downstream audits skipped adopt's adoption ADR.
# ---------------------------------------------------------------------------

def test_adopt_render_roundtrips_through_parse_adr_headers() -> None:
    """End-to-end: adopt's rendered output is parseable by the shared
    compact-form parser. Brownfield + retroactive ADRs all picked up.

    We invoke adopt's artifact_writer in a subprocess so the plugin's
    own `scripts/lib` namespace (which collides with `shared/scripts/lib`
    if loaded into the test process) stays isolated.
    """
    import subprocess
    import sys

    from scripts.lib.adr_headers import parse_adr_headers

    repo_root = Path(__file__).resolve().parents[2]
    adopt_scripts = repo_root / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys; sys.path.insert(0, r'"
        + str(adopt_scripts).replace("\\", "\\\\")
        + "');\n"
        "from lib.artifact_writer import _render_decision_log\n"
        "out = _render_decision_log(\n"
        "    project_name='Demo', profile='x', scope='full_app',\n"
        "    commit_sha='abc1234', features_count=3,\n"
        "    retroactive_adrs=[\n"
        "        {'sha': 'def5678', 'subject': 'First retroactive',\n"
        "         'context': 'ctx', 'decision': 'dec', 'consequences': 'csq'},\n"
        "        {'sha': 'ghi9012', 'subject': 'Second retroactive',\n"
        "         'context': 'ctx', 'decision': 'dec', 'consequences': 'csq'},\n"
        "    ],\n"
        "    start_adr_number=59,\n"
        ")\n"
        "import sys; sys.stdout.buffer.write(out.encode('utf-8'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", helper],
        capture_output=True, check=True,
    )
    body = result.stdout.decode("utf-8")
    headers = parse_adr_headers(body)
    ids = [h.id for h in headers]
    # All three adopt-written ADRs are picked up — adoption + 2 retroactive.
    assert ids == ["ADR-059", "ADR-060", "ADR-061"], (
        f"parse_adr_headers should round-trip all three adopt ADRs, got: {ids}"
    )
    statuses = {h.id: h.status for h in headers}
    assert statuses["ADR-059"] == "accepted"
    # Retroactive Status is "accepted (retroactive, llm-inferred)" — the
    # status regex stops at `(`, so we get "accepted" cleanly.
    assert statuses["ADR-060"] == "accepted"
    # Sanity: ensure the H2 form did not regress.
    import re as _re
    assert not _re.search(r"^## ADR-\d{3}:\s+Adopt", body, _re.MULTILINE), (
        "adopt regressed to H2 ADR heading"
    )
