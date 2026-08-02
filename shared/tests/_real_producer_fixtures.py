"""The seeded project that ``test_compliance_refresh_real_producer`` drives.

One consumer, so it lives beside it rather than in ``_compliance_refresh_fixtures``
— which six modules import, and where this content would make an edit to
``_SEED_EVENTS`` touch five unrelated suites (Stage-2 review). ``_d2v_helpers``
and ``_sweep_helpers`` are the same shape.

``seed_repo`` from the shared module is still the base: it commits the seven
documents with plausible content. What is added here is the ``.shipwright`` tree
the real producers need to derive anything *from* them. With no FRs and no tagged
tests the RTM's layer cells come out empty either way, the
rtm←test-traceability ordering coupling cannot show, and the run settles in two
passes instead of three — proving less than it appears to (measured).
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _compliance_refresh_fixtures import git, seed_repo  # noqa: E402
from lib.churn_merge import EVENTS_LOG, TEST_TRACEABILITY, TRIAGE_LOG  # noqa: E402
from triage import should_route_to_outbox  # noqa: E402

#: Paths and values the real-producer module asserts about by name.
COMPLIANCE_CONFIG = "shipwright_compliance_config.json"
RTM = ".shipwright/compliance/traceability-matrix.md"
CHANGE_HISTORY = ".shipwright/compliance/change-history.md"
SBOM = ".shipwright/compliance/sbom.md"
MANIFEST = TEST_TRACEABILITY
FR_IDS = ("FR-01.01", "FR-01.02")
FAILING_LAYER_DEDUP_KEY = "test-fail:unit"
#: Content only the seed can account for — used to prove a document carries a real
#: derivation rather than merely different bytes.
#:
#: ``change-history.md`` renders GIT COMMITS, not events (measured — an earlier
#: draft asserted the event description and failed), and the seeder makes exactly
#: two: ``seed`` and ``feat: widgets``.
CHANGE_HISTORY_MARKER = "| Total commits | 2 |"
SBOM_MARKER = "requests"

__all__ = [
    "CHANGE_HISTORY", "CHANGE_HISTORY_MARKER", "COMPLIANCE_CONFIG",
    "FAILING_LAYER_DEDUP_KEY", "FR_IDS", "MANIFEST", "RTM", "SBOM", "SBOM_MARKER",
    "added_records", "assert_seed_is_sound", "hermetic_gh_env",
    "is_ordered_subsequence", "read_lines", "seed_project",
]

_SPEC_MD = """# Specification - probe / 01-core

## Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.01 | Core | Widget list | Must | The operator can list widgets. | code | unit |
| FR-01.02 | Core | Widget detail | Must | The operator can open one widget. | code | integration |
"""

# Tagged with the frozen `@pytest.mark.covers` grammar (`lib/fr_tag_grammar.py`).
# An earlier draft put `@FR-01.01` in a docstring, which the grammar does not
# read: it produced a manifest carrying two `untagged_tests` while looking like it
# exercised the tag→FR join.
_TAGGED_TESTS = '''"""Fixture test module — parsed by the tag collector, never executed."""

import pytest


@pytest.mark.covers("FR-01.01")
def test_widget_list_returns_rows():
    assert True


@pytest.mark.covers("FR-01.02")
def test_widget_detail_opens():
    assert True
'''

# The FAILING unit layer is load-bearing: it is what makes `test_evidence`'s
# triage leg append, so `.shipwright/triage.jsonl` really moves during a run and
# the append-only assertions are not vacuous.
_SEED_EVENTS = (
    {"id": "evt-0001", "ts": "2026-07-01T09:00:00+00:00", "type": "work_completed",
     "source": "iterate", "run_id": "iterate-2026-07-01-widgets", "commit": "a" * 40,
     "adr_id": "iterate-2026-07-01-widgets", "description": "widget list",
     "intent": "feature", "spec_impact": "add", "affected_frs": ["FR-01.01"],
     "tests": {"passed": 2, "total": 2}},
    {"id": "evt-0002", "ts": "2026-07-02T09:00:00+00:00", "type": "test_run",
     "source": "test", "run_id": "iterate-2026-07-02-widgets",
     "layers": {"unit": {"passed": 1, "total": 2, "failed": 1}}},
)

_SEED_TRIAGE = (
    {"id": "trg-probe01", "ts": "2026-07-01T10:00:00+00:00", "source": "compliance",
     "status": "triage", "severity": "medium", "title": "probe backlog item",
     "dedupKey": "probe:backlog:1"},
)


def _jsonl(records) -> str:
    return "".join(json.dumps(r) + "\n" for r in records)


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def is_ordered_subsequence(needles: list[str], haystack: list[str]) -> bool:
    """Every needle appears in ``haystack``, byte-for-byte and in order.

    Membership would miss a reordering or a dropped duplicate; a prefix test is
    plainly WRONG here — the triage store prepends a schema header when the file
    lacks one, so ``after`` does not start with ``before`` (external review,
    openai/medium; the header was found by reading the bytes, not assumed).
    """
    remaining = iter(haystack)
    return all(any(line == needle for line in remaining) for needle in needles)


def added_records(before: bytes, path: Path) -> list[dict]:
    """JSONL records in ``path`` that ``before`` did not carry.

    A MULTISET difference, so a producer appending a line byte-identical to one
    already present is still counted — the callers assert exact counts, and a set
    difference would quietly swallow such a record (Stage-2 review).
    """
    seeded = Counter(before.decode("utf-8").splitlines())
    return [json.loads(line)
            for line, n in (Counter(read_lines(path)) - seeded).items()
            for _ in range(n)]


def hermetic_gh_env(monkeypatch, gh_config_dir: Path) -> None:
    """Make the ``gh`` CLI unauthenticated for this process AND its children.

    Load-bearing, not hygiene. ``_update_compliance`` shells out **without**
    ``cwd=``, so the child inherits the pytest process's working directory — the
    shipwright worktree — and ``gh api`` resolves ``{owner}/{repo}`` from *that*
    remote. On an authenticated machine the ci-security leg therefore reached the
    REAL repository over the network, three times per run, inside a 30 s
    subprocess timeout; on CI (whose ``shared/tests`` step exports no token) it
    was skipped instead. Same code, two different results, and the conftest's
    in-process ``gh`` stub cannot cross a subprocess boundary (Stage-2 review,
    high — confirmed by measurement: ``ci-security.json`` changed with auth and
    did not change without it).

    Pointing ``GH_CONFIG_DIR`` at an empty directory makes ``gh auth status``
    fail locally, with no network call, so every machine takes the same branch.
    """
    monkeypatch.setenv("GH_CONFIG_DIR", str(gh_config_dir))
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
                "GITHUB_ENTERPRISE_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def seed_project(root: Path) -> Path:
    """:func:`seed_repo` plus the ``.shipwright`` tree the producers derive from.

    Every value is literal and repository-local; nothing is read from the
    environment. It is **not** network-free on its own — see
    :func:`hermetic_gh_env` for the one leg that reaches out, and which the
    caller must neutralise.
    """
    seed_repo(root)
    (root / ".shipwright" / "planning" / "01-core").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "planning" / "01-core" / "spec.md").write_text(
        _SPEC_MD, encoding="utf-8")
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_widgets.py").write_text(_TAGGED_TESTS, encoding="utf-8")
    (root / EVENTS_LOG).write_text(_jsonl(_SEED_EVENTS), encoding="utf-8")
    (root / TRIAGE_LOG).write_text(_jsonl(_SEED_TRIAGE), encoding="utf-8")
    # `phases_covered` deliberately lacks "iterate": that is what the producer
    # appends, so its rewrite of this file is real rather than a no-op.
    (root / COMPLIANCE_CONFIG).write_text(
        json.dumps({"status": "in_progress", "phases_covered": ["build"]}, indent=2)
        + "\n", encoding="utf-8")
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "project_name": "probe"}, indent=2) + "\n",
        encoding="utf-8")
    (root / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"passed": 1, "total": 2}}, indent=2) + "\n",
        encoding="utf-8")
    # The dependency array must be MULTI-LINE: `parse_pyproject_dep_specs` is a
    # line parser that only opens on a line equal to `dependencies = [`, so the
    # equally valid single-line form parses to zero dependencies and the SBOM
    # renders "No dependency manifests found" (measured).
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nversion = "0.1.0"\ndependencies = [\n'
        f'    "{SBOM_MARKER}>=2.0",\n]\n', encoding="utf-8")
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "# Decision Log\n\n## 2026-07-01 - use widgets\n\nBecause.\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-m", "feat: widgets")
    return root


def assert_seed_is_sound(root: Path) -> None:
    """Fail as a FIXTURE fault, before the producer runs.

    Only the checks that can fail for a reason OUTSIDE this file: a malformed
    seed otherwise surfaces as six opaque document assertions and reads as a
    producer defect (external review, openai/medium). Round-tripping this
    module's own literals was dropped — those can only fire when somebody edits
    the constant twenty lines up (Stage-2 review).
    """
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / "plugins" / "shipwright-compliance" / "scripts" / "tools"
            / "update_compliance.py").is_file(), (
        "the compliance plugin is unreachable — `_update_compliance` resolves it by "
        "path constant from the repo root and would silently return []"
    )
    assert os.environ.get("GH_CONFIG_DIR"), (
        "the gh CLI was not neutralised — the ci-security leg would reach the real "
        "GitHub repo from the inherited cwd; call hermetic_gh_env() first"
    )
    # The three-pass count is a property of the SEEDED manifest, and that literal
    # lives in `seed_repo` — a module six suites import, which this file otherwise
    # keeps its hands off. Pass 1's RTM renders "—" layer cells precisely because
    # the seed is not a readable v3 manifest; pass 2 reads the real one pass 1
    # wrote. Turn that placeholder into a plausible manifest and the run settles
    # in two passes, with a failure message that sends the reader to
    # PHASE_REPORTS instead (Stage-3 doubt D1).
    assert json.loads((root / MANIFEST).read_text(encoding="utf-8")
                      ).get("schema_version") != 3, (
        "the seeded test-traceability manifest is READABLE, so pass 1's RTM will "
        "render the same layer cells as pass 2 and the ordering coupling this "
        "module measures cannot appear — see seed_repo in _compliance_refresh_fixtures"
    )
    # Same failure class Stage 2 caught on `gh`, one layer down: the triage
    # appends only land in the TRACKED log — which three cases assert on —
    # because this fixture has no `origin`. Under CI `$CI` forces the same
    # outcome, so a divergence here would be green in CI and red locally.
    assert not should_route_to_outbox(root), (
        "the fixture would route triage appends to the GITIGNORED outbox instead "
        "of the tracked log the append-only assertions read"
    )
    assert not git(root, "status", "--porcelain").stdout.strip(), (
        "the seed left the tree dirty, so 'changed against the committed seed' "
        "would not mean what the assertions take it to mean"
    )
