"""TT7 — adopt traceability-baseline orchestrator (end-to-end subprocess).

Marked ``slow``: runs the REAL ``seed_traceability_baseline.py`` (which itself
subprocesses the TT6 backfill engine) as a spawned process against temp adopt-shaped
repos, exactly as production — the process boundary keeps the shared/compliance ``lib``
packages apart (ADR-045). Three fixture repos per the test plan: with-tests, no-tests,
with-orphans (+ predeclared decisions). The manifest arm additionally runs the Step F
collector (``update_compliance --phase adopt``, now wired for ``test_links``) to prove
the baseline manifest is populated from the tags this step establishes (AC1).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

_PLUGIN = Path(__file__).resolve().parent.parent
_REPO = _PLUGIN.parents[1]
_TOOL = _PLUGIN / "scripts" / "tools" / "seed_traceability_baseline.py"
_COMPLIANCE = _REPO / "plugins" / "shipwright-compliance"
_UPDATE_COMPLIANCE = _COMPLIANCE / "scripts" / "tools" / "update_compliance.py"
_DECISIONS = (
    _COMPLIANCE / "tests" / "fixtures" / "traceability" / "decisions" / "adopt_ambiguity.json"
)

_SPEC_WITH_TESTS = """# Spec: Adopted App

## Functional Requirements

| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-01.01 | Sign in | Must | User can sign in | `app/auth.py` | unit, e2e (inferred) |
| FR-01.02 | Persist order | Should | Save an order | `app/db.py` | unit, integration (inferred) |

## Removed Requirements

| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-01.09 | Clipboard | Should | Copy to clipboard | `app/ui.py` | e2e |
"""


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-m", "init", "-q"], cwd=root, check=True)


def _make_repo(root: Path, *, spec: str, split: str = "01-adopted", files: dict | None = None) -> None:
    (root / ".shipwright" / "planning" / split).mkdir(parents=True)
    (root / ".shipwright" / "planning" / split / "spec.md").write_text(spec, encoding="utf-8")
    for rel, body in (files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _git_init(root)


def _run_seed(root: Path, *extra: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_TOOL), "--project-root", str(root), *extra],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def _triage_events(root: Path) -> list[dict]:
    path = root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("event") == "append":
            out.append(obj)
    return out


def _triage_titles(root: Path) -> list[str]:
    return [e["title"] for e in _triage_events(root)]


# --------------------------------------------------------------------------- #

def test_with_tests_repo_scaffolds_tags_and_populates_baseline(tmp_path: Path):
    root = tmp_path / "app"
    _make_repo(root, spec=_SPEC_WITH_TESTS, files={
        # An ALREADY-@FR-tagged unit test → the collector links it to FR-01.01 coverage.
        "tests/test_auth.py": (
            "import pytest\n"
            "@pytest.mark.covers('FR-01.01')\n"
            "def test_sign_in():\n    assert True\n"),
        # A test for a REMOVED FR → confirmed orphan.
        "e2e/legacy.spec.ts": "test('copies to clipboard', { tag: ['@FR-01.09'] }, async () => {});\n",
        # A test that maps to NO live FR → unmapped (a review candidate, NOT stale).
        "e2e/widget.spec.ts": "test('renders a legacy widget', async () => {});\n",
    })
    result = _run_seed(root)

    # Tag convention scaffolded into the target repo (AC1).
    assert ".claude/rules/tests.md" in result["tag_convention"]["written"]
    assert (root / ".claude" / "rules" / "tests.md").exists()
    # Existing tests were scanned; the @FR-01.09 tag on the REMOVED FR is a confirmed orphan.
    assert result["backfill"]["confirmed_orphan"] == 1
    assert result["backfill"]["unmapped"] >= 1
    # Orphan → tracked triage (lands in the Step H commit → WebUI Inbox).
    titles = _triage_titles(root)
    assert any("Orphaned test" in t for t in titles)
    # O7 + O-C4: an unmapped test is filed as a REVIEW candidate, and its TT6 category
    # survives structurally into the persisted item (the dedupKey prefix), not just prose.
    events = _triage_events(root)
    unmapped = [e for e in events if e["dedupKey"].startswith("adopt-unmapped::")]
    assert unmapped, "unmapped test must be filed as triage"
    assert all("stale" not in e["title"].lower() for e in unmapped)
    assert all("never" in e["detail"].lower() for e in unmapped)
    assert any(e["dedupKey"].startswith("adopt-orphan-confirmed::") for e in events)
    # Summary artifact written for the Step H banner.
    assert (root / ".shipwright" / "adopt" / "traceability-baseline.json").exists()

    # Step F (collector, now wired) emits a POPULATED, layer-aware manifest from the FRs.
    manifest = _run_step_f_manifest(root)
    reqs = manifest["requirements"]
    assert "01::FR-01.01" in reqs
    # O-C6: the baseline manifest carries the real backward test→FR link — the tagged unit
    # test lands under FR-01.01's unit coverage (proves the tag→FR→manifest round-trip, not
    # just that the FR parsed).
    unit_links = [t["id"] for t in reqs["01::FR-01.01"]["tests"].get("unit", [])]
    assert any("test_sign_in" in tid for tid in unit_links), reqs["01::FR-01.01"]["tests"]
    # Adopt FRs are inferred_legacy → D-layer advisory (WARN), never a false hard gate (AC2).
    assert reqs["01::FR-01.01"]["required_layers_source"] == "inferred_legacy"
    assert any(o["category"] == "confirmed_orphan" for o in manifest["orphans"])


def test_zero_test_repo_adopts_cleanly(tmp_path: Path):
    root = tmp_path / "lib"
    spec = (
        "# Spec: Lib\n\n## Functional Requirements\n\n"
        "| ID | Name | Priority | Description | Source | Layers |\n"
        "|----|------|----------|-------------|--------|--------|\n"
        "| FR-01.01 | Parse | Must | Parse config | `src/p.py` | unit (inferred) |\n"
    )
    _make_repo(root, spec=spec, files={"src/p.py": "def parse():\n    return 1\n"})
    result = _run_seed(root)

    assert result["backfill"]["tests"] == 0
    assert result["skip_inventory"]["count"] == 0
    assert result["triage"]["appended"] == 0          # no false triage
    assert _triage_titles(root) == []                  # empty (no false gate)
    # The FR still resolves (never stalls) even with zero tests + no decisions.
    assert len(result["layer_resolutions"]) == 1
    assert result["layer_resolutions"][0]["resolved_from"] == "inference_default"

    # O8: the manifest is EMPTY-but-PRESENT (a real file, not "manifest missing") — the FR
    # is inferred_legacy, so its MISSING unit layer is advisory (WARN), never a false gate.
    manifest_path = root / ".shipwright" / "compliance" / "test-traceability.json"
    _run_step_f_manifest(root)
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["orphans"] == []
    assert manifest["untagged_tests"] == []
    assert manifest["requirements"]["01::FR-01.01"]["required_layers_source"] \
        == "inferred_legacy"


def test_predeclared_decisions_resolve_unattended_without_stalling(tmp_path: Path):
    # Namespace `app` matches P1's decisions fixture keys (app::FR-03.02 / .03).
    root = tmp_path / "app"
    spec = (
        "# Spec\n\n## Functional Requirements\n\n"
        "| FR | Description | Priority | Layers |\n"
        "|----|-------------|----------|--------|\n"
        "| FR-03.01 | User can sign in | Must | unit, e2e |\n"
        "| FR-03.02 | Dashboard shows live orders | Must | |\n"
        "| FR-03.03 | Persist an order to the database | Should | |\n"
    )
    _make_repo(root, spec=spec, split="app", files={
        "tests/test_x.py": "def test_x():\n    assert True\n",
    })
    result = _run_seed(root, "--split-name", "app", "--decisions", str(_DECISIONS))

    # Both empty-Layers FRs resolved from the fixture; the explicit one is untouched.
    used = result["predeclared_decisions_used"]
    assert used == 2, result["layer_resolutions"]
    # NOTE: adopt's decisions/resolutions map stays split-name namespaced ("app::") --
    # it is a separate, user-authored contract. Only the traceability MANIFEST key below
    # is id-derived ("03::"). The two forms deliberately differ (campaign S3).
    by_key = {r["key"]: r for r in result["layer_resolutions"]}
    assert by_key["app::FR-03.02"]["required_layers"] == ["e2e"]
    assert by_key["app::FR-03.02"]["resolved_from"] == "predeclared_decision"

    # O1: the decision must reach the AUTHORITATIVE spec (written before Step F), so the
    # collector's manifest carries the decided layers — not a silently-discarded choice.
    assert result["layers_written_to_spec"] == 2
    spec_body = (root / ".shipwright" / "planning" / "app" / "spec.md").read_text(encoding="utf-8")
    assert "e2e (inferred)" in spec_body
    manifest = _run_step_f_manifest(root)  # discovers .shipwright/planning/app/spec.md
    assert manifest["requirements"]["03::FR-03.02"]["required_layers"] == ["e2e"]


def test_orphan_baseline_is_idempotent(tmp_path: Path):
    root = tmp_path / "app"
    _make_repo(root, spec=_SPEC_WITH_TESTS, files={
        "e2e/legacy.spec.ts": "test('copies to clipboard', { tag: ['@FR-01.09'] }, async () => {});\n",
    })
    first = _run_seed(root)
    before = len(_triage_titles(root))
    second = _run_seed(root)
    assert first["triage"]["appended"] >= 1
    assert second["triage"]["appended"] == 0          # dedup — no duplicate cards
    assert len(_triage_titles(root)) == before
    assert second["tag_convention"]["written"] == []  # rules already present


def test_dry_run_mutates_nothing(tmp_path: Path):
    # O-C2: --dry-run is a preview — it must not scaffold rules, write triage, or a summary.
    root = tmp_path / "app"
    _make_repo(root, spec=_SPEC_WITH_TESTS, files={
        "e2e/legacy.spec.ts": "test('copies to clipboard', { tag: ['@FR-01.09'] }, async () => {});\n",
    })
    result = _run_seed(root, "--dry-run")
    assert result["dry_run"] is True
    assert not (root / ".claude" / "rules" / "tests.md").exists()
    assert not (root / ".shipwright" / "triage.jsonl").exists()
    assert not (root / ".shipwright" / "adopt" / "traceability-baseline.json").exists()
    # code L1: the TT6 backfill report is routed to a temp dir under --dry-run, so
    # `.shipwright/backfill/` on the adopted repo is NOT created.
    assert not (root / ".shipwright" / "backfill").exists()
    # But it still REPORTS what it would do (the rule file + the orphan).
    assert ".claude/rules/tests.md" in result["tag_convention"]["written"]


def _run_step_f_manifest(root: Path) -> dict:
    """Run the real Step F collector (compliance venv) and return the manifest."""
    proc = subprocess.run(
        ["uv", "run", "--project", str(_COMPLIANCE), "python", str(_UPDATE_COMPLIANCE),
         "--project-root", str(root), "--phase", "adopt"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads((root / ".shipwright" / "compliance" / "test-traceability.json")
                      .read_text(encoding="utf-8"))
