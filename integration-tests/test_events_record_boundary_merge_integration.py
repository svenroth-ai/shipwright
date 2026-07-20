"""INTEGRATION: a real git union merge composed with every event-log reader.

The `cross_component` integration-coverage case for
iterate-2026-07-19-…-readers. The unit tests prove each reader recovers records
from a concatenated line *in isolation*; this proves the pieces COMPOSE — that
real `merge=union` on real git delivers such a line into the merged tree, and
that the shared readers plus the compliance collector and both audit-group
loaders all see BOTH records on the other side.

WHAT THIS TEST CORRECTED
------------------------
The predecessor's stated mechanism was that union merge CREATES the
concatenation by joining an unterminated blob's last line to the other side's
first line. Building this test disproved that (git 2.54, builtin driver, no
custom `merge.union.*`): git tracks "\\ No newline at end of file" as a diff
property and RECONCILES it. ``test_union_merge_does_not_itself_join_records``
pins that finding so the claim cannot silently come back.

The real exposure — pinned by ``test_union_merge_propagates_...`` — is that union
merge PROPAGATES an existing concatenated line verbatim into the merged tree,
with no conflict and no repair. One unguarded write anywhere (an interrupted
write, an external writer, an operator edit, or any record already on disk from
before the writer guard landed) therefore reaches every consumer of the merged
log. That is what makes reader-side recovery load-bearing rather than redundant
with the writer guard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
_COMPLIANCE = _REPO_ROOT / "plugins" / "shipwright-compliance"

from lib.churn_merge import validate_events_text  # noqa: E402
from lib.events_log import finalized_run_ids, latest_event_dt  # noqa: E402
from lib.phase_quality import STATUS_PASS  # noqa: E402
from tools.verifiers.adopt_compliance import check_a7_adopted_event  # noqa: E402
from tools.verifiers.common import read_events_jsonl  # noqa: E402

# Reads the event log through the three compliance-side readers with ONLY the
# compliance roots on sys.path — the production shape, and the one that keeps the
# ambiguous `scripts` package resolving to the plugin rather than the repo root.
_TIER_B_DRIVER = """
import json, sys
from pathlib import Path
comp, repo = sys.argv[1], sys.argv[2]
sys.path.insert(0, comp + "/scripts")   # `lib.collectors` (collector package)
sys.path.insert(0, comp)                # `scripts.audit` (audit package)
from lib.collectors import change_history
from scripts.audit import group_b, group_d
root = Path(repo)
print(json.dumps({
    "change_history": [e.get("id") for e in change_history._read_event_log(root)],
    "group_b": [e.get("id") for e in (group_b._load_events(root) or [])],
    "group_d": [e.get("id") for e in (group_d._load_events(root) or [])],
}))
"""

_A1 = {"v": 1, "id": "evt-a1", "ts": "2026-07-19T10:00:00+00:00",
       "type": "work_completed", "adr_id": "iterate-a1", "run_id": "iterate-a1"}
_A2 = {"v": 1, "id": "evt-a2", "ts": "2026-07-19T10:30:00+00:00",
       "type": "work_completed", "adr_id": "iterate-a2", "run_id": "iterate-a2"}
_B1 = {"v": 1, "id": "evt-b1", "ts": "2026-07-19T11:00:00+00:00",
       "type": "work_completed", "adr_id": "iterate-b1", "run_id": "iterate-b1"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@example.test")
    _git(repo, "config", "user.name", "t")
    # Text conversion off: on Windows autocrlf normalises the file on checkout,
    # which would silently repair the very byte pattern under test.
    _git(repo, "config", "core.autocrlf", "false")
    # The real driver declaration, from the monorepo root .gitattributes.
    (repo / ".gitattributes").write_text(
        "shipwright_events.jsonl merge=union\n", encoding="utf-8"
    )


def _write_log(repo: Path, text: str) -> None:
    (repo / "shipwright_events.jsonl").write_text(text, encoding="utf-8", newline="")


def _merge_two_sides(repo: Path, side_a: str, side_b: str) -> Path:
    """Commit ``side_a`` and ``side_b`` on divergent branches, union-merge them."""
    _init_repo(repo)
    _write_log(repo, json.dumps({"id": "evt-base"}) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "checkout", "-qb", "side-a")
    _write_log(repo, side_a)
    _git(repo, "commit", "-qam", "side a")

    _git(repo, "checkout", "-q", base)
    _git(repo, "checkout", "-qb", "side-b")
    _write_log(repo, side_b)
    _git(repo, "commit", "-qam", "side b")

    _git(repo, "checkout", "-q", "side-a")
    merged = _git(repo, "merge", "side-b")
    assert merged.returncode == 0, f"union merge must not conflict:\n{merged.stderr}"
    return repo / "shipwright_events.jsonl"


def _physical_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# The mechanism, pinned in both directions
# ---------------------------------------------------------------------------

def test_union_merge_does_not_itself_join_records(tmp_path: Path) -> None:
    """Git RECONCILES an unterminated blob rather than joining it.

    Disproves the predecessor's stated mechanism. Kept as a live assertion so the
    claim cannot quietly return to the docs: if a future git ever does join here,
    this fails and the rationale gets revisited deliberately.
    """
    log = _merge_two_sides(
        tmp_path / "reconciles",
        side_a=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_A1),  # NO newline
        side_b=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_B1) + "\n",
    )
    assert not [ln for ln in _physical_lines(log) if "}{" in ln], (
        "git union merge is not expected to create a concatenated line"
    )


def test_union_merge_propagates_an_existing_concatenated_line(tmp_path: Path) -> None:
    """The real exposure: an existing concatenation rides the merge into main.

    No conflict, no repair — so one unguarded write reaches every consumer of the
    merged log, and reader-side recovery is what stands between that and a
    ``work_completed`` reading as absent.
    """
    log = _merge_two_sides(
        tmp_path / "propagates",
        # Side A already holds two records on ONE physical line — an interrupted
        # write, an external writer, or a record predating the writer guard.
        side_a=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_A1) + json.dumps(_A2) + "\n",
        side_b=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_B1) + "\n",
    )
    joined = [ln for ln in _physical_lines(log) if "}{" in ln]
    assert len(joined) == 1, f"the concatenated line must survive the merge: {_physical_lines(log)}"


# ---------------------------------------------------------------------------
# AC7 — every reader composes with the merged tree
# ---------------------------------------------------------------------------

def test_all_readers_recover_both_records_after_a_real_union_merge(tmp_path: Path) -> None:
    """The composition proof: real git merge -> every reader sees all three runs.

    Pre-fix, the concatenated line was skipped whole at all six sites, so
    ``iterate-a1`` and ``iterate-a2`` — steps that demonstrably happened, and
    whose records are on disk in the merged tree — read as steps that never did.
    """
    repo = tmp_path / "compose"
    _merge_two_sides(
        repo,
        side_a=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_A1) + json.dumps(_A2) + "\n",
        side_b=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_B1) + "\n",
    )
    expected_ids = {"evt-a1", "evt-a2", "evt-b1"}
    expected_runs = {"iterate-a1", "iterate-a2", "iterate-b1"}

    # Tier A — shared readers.
    assert expected_ids <= {e["id"] for e in read_events_jsonl(repo)}
    assert finalized_run_ids(repo) is not None, "a clean merged log must be determinable"
    assert expected_runs <= finalized_run_ids(repo)
    latest = latest_event_dt(repo)
    assert latest is not None and latest.isoformat() == "2026-07-19T11:00:00+00:00"

    # Tier B — compliance collector + both audit-group loaders, across the
    # ADR-045 import boundary. Run as their OWN PROCESS with only the compliance
    # roots on sys.path, mirroring `test_fold_map_e2e.py` and, more importantly,
    # mirroring production: the audit really does run as a separate process.
    #
    # In-process import was tried and F0.5 caught it failing: `scripts` is
    # ambiguous between the repo-root `scripts/` and the compliance plugin's
    # `scripts/`, so whichever bound first won — the same ADR-045 collision class
    # this iterate is about, one namespace level up. A subprocess sidesteps it
    # instead of racing it.
    proc = subprocess.run(
        [sys.executable, "-c", _TIER_B_DRIVER, str(_COMPLIANCE), str(repo)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"tier-B driver failed:\n{proc.stdout}\n{proc.stderr}"
    seen = json.loads(proc.stdout)
    for reader, ids in seen.items():
        assert expected_ids <= set(ids), f"{reader} lost records: {ids}"


# ---------------------------------------------------------------------------
# AC7 (part-2 remainder) — the merge VALIDATOR and a converted READER compose
# ---------------------------------------------------------------------------

def test_validator_and_reader_compose_after_a_real_union_merge(tmp_path: Path) -> None:
    """``churn_merge.validate_events_text`` (the ``integrate_main`` gate) and the
    converted ``check_a7_adopted_event`` reader BOTH see the run after a real
    ``merge=union`` merge propagates a concatenated line.

    Pre-fix this is the paired false failure: the validator reported a spurious
    ``check_events_has_commit`` failure (the run's ``work_completed`` sat second on
    the joined line and never matched ``require_run_id``) while the A7 reader
    reported the ``adopted`` event as absent — both for records demonstrably on
    disk in the merged tree.
    """
    adopted = {"id": "evt-adopted", "type": "adopted"}
    work = {"id": "evt-work", "type": "work_completed",
            "adr_id": "iterate-merged", "run_id": "iterate-merged", "commit": ""}
    repo = tmp_path / "compose2"
    log = _merge_two_sides(
        repo,
        # Side A holds the ``adopted`` event and this run's ``work_completed`` on
        # ONE physical line (work_completed second — the inverted case).
        side_a=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(adopted) + json.dumps(work) + "\n",
        side_b=json.dumps({"id": "evt-base"}) + "\n" + json.dumps(_B1) + "\n",
    )
    assert [ln for ln in _physical_lines(log) if "}{" in ln], "the concatenated line must survive the merge"

    # The validator: no false check_events_has_commit failure for the run.
    merged_text = log.read_text(encoding="utf-8")
    assert validate_events_text(merged_text, require_run_id="iterate-merged") == []

    # The reader: exactly one recovered ``adopted`` event -> A7 PASSes.
    assert check_a7_adopted_event(repo)["status"] == STATUS_PASS
