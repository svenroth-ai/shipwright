"""Onboarding's delivery of the evidence documents — ``--stamp-adopted``.

Subject: ``shared/scripts/tools/compliance_adopt_stamp.deliver_stamp_adopted``
(iterate-2026-08-05-adopt-derived-evidence-rollout, AC-1 / AC-3).

The third delivery point, and what it puts on disk. The claim under test
throughout is **"a complete set, or nothing"** — every failure path is checked
for what it left behind, not only for what it returned.

Two sibling files, split by subject rather than by size alone:
``test_stamp_adopted_base.py`` covers AC-2 (which commit the evidence names, or
that none does), and ``test_refresh_compliance_docs.py`` covers the release and
PR deliveries. The fixtures are shared; the files are not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Unconditional, and in this order: `shared/tests` carries its own `tools/`
# package and must never sit ahead of `shared/scripts` (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import (  # noqa: E402
    DASHBOARD, RUN, git, head_sha, seed_repo,
)
from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from source_state import parse_banner_line  # noqa: E402
from tools import compliance_adopt_stamp as adopt_stamp  # noqa: E402
from tools import refresh_compliance_docs as docs  # noqa: E402

#: The members that carry a banner at all. The two ``.json`` paths state their
#: provenance in their own fields, so "five of seven" is the whole set, not a gap.
STAMPABLE = frozenset(rel for rel in REFRESH_SET if rel.endswith(".md"))


@pytest.fixture
def adopted_repo(tmp_path: Path) -> Path:
    return seed_repo(tmp_path / "repo")


def _stamp(root: Path, capsys, *extra: str) -> tuple[int, dict]:
    """Drive the CLI the way onboarding does, and read back what it reported."""
    code = docs.main(["--stamp-adopted", "--project-root", str(root), *extra])
    return code, json.loads(capsys.readouterr().out)


def _base_of(root: Path, rel: str = DASHBOARD) -> str | None:
    state = parse_banner_line((root / rel).read_text(encoding="utf-8"))
    return state.base if state else None


def _tree_is_clean(root: Path) -> bool:
    return not git(root, "status", "--porcelain").stdout.strip()


# --- AC-1: the recorded commit reaches the banner ----------------------------


def test_stamps_every_markdown_member_with_the_supplied_base(adopted_repo, capsys):
    sha = head_sha(adopted_repo)
    code, report = _stamp(adopted_repo, capsys, "--base", sha)

    assert code == 0, report
    assert report["status"] == "ok"
    assert set(report["stamped"]) == STAMPABLE, (
        "a partial stamp is the failure this mode exists to make impossible"
    )
    for rel in STAMPABLE:
        assert _base_of(adopted_repo, rel) == sha[:12], (
            f"{rel} does not name the commit onboarding read"
        )


def test_the_run_id_already_in_the_banner_survives(adopted_repo, capsys):
    _stamp(adopted_repo, capsys, "--base", head_sha(adopted_repo))
    state = parse_banner_line((adopted_repo / DASHBOARD).read_text(encoding="utf-8"))
    assert state is not None and state.run_id == RUN, (
        "stamping adds the fixed point; it does not discard what the renderer knew"
    )


# --- AC-3: onboarding is not a release ---------------------------------------


def test_a_stale_release_claim_is_removed_not_merely_left_alone(adopted_repo, capsys):
    doc = adopted_repo / DASHBOARD
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            f"Source-State: run={RUN}",
            f"Source-State: run={RUN} base=1111111111112222 release=v0.4.0"),
        encoding="utf-8")
    git(adopted_repo, "add", "-A")
    git(adopted_repo, "commit", "-m", "a document that shipped with a release")

    _stamp(adopted_repo, capsys, "--base", head_sha(adopted_repo))

    text = doc.read_text(encoding="utf-8")
    assert "release=" not in text, (
        "onboarding ships with no release, so a release inherited from an earlier "
        "delivery would be a claim nobody made"
    )


# --- the shortfall is fatal, and non-mutating --------------------------------


def test_a_bannerless_document_aborts_without_touching_the_tree(adopted_repo, capsys):
    """`stamp_fixed_point` skips a document with no banner and omits it silently.

    Probed 2026-08-06: it returns the paths it DID stamp and says nothing about
    the rest, so a caller comparing nothing would ship a half-stamped set and
    report success — the shape #512 was bitten by one layer down.
    """
    victim = adopted_repo / ".shipwright/compliance/sbom.md"
    victim.write_text("# sbom\n\nno banner here\n" + "row\n" * 40, encoding="utf-8")
    git(adopted_repo, "add", "-A")
    git(adopted_repo, "commit", "-m", "a document that lost its banner")
    before = {rel: (adopted_repo / rel).read_text(encoding="utf-8") for rel in STAMPABLE}

    code, report = _stamp(adopted_repo, capsys, "--base", head_sha(adopted_repo))

    assert code != 0, "a JSON status with exit 0 is trivially ignored by a wrapper"
    assert report["status"] == "partial"
    assert ".shipwright/compliance/sbom.md" in report["missing"]
    for rel, text in before.items():
        assert (adopted_repo / rel).read_text(encoding="utf-8") == text, (
            f"{rel} was written before the set was known to be complete — an "
            "aborted adoption must not leave the repository mutated"
        )
    assert _tree_is_clean(adopted_repo)


@pytest.mark.parametrize(
    ("label", "base_argv"),
    [("with a resolvable base", True), ("with NO resolvable base", False)],
)
def test_an_incomplete_set_stops_the_adoption_either_way(
    adopted_repo, capsys, label, base_argv,
):
    """An absent document is fatal whatever the base turns out to be.

    Absence still gets its OWN status rather than being folded into `partial` —
    they are different diagnoses, and `partial`'s wording is untrue of a file that
    is not there (Stage-1 spec review). But it is not *tolerable*: an earlier
    draft returned `ok` here, and worse, the `no_base` branch sat AHEAD of the
    check, so a repository missing two documents AND lacking a resolvable base
    returned exit 0, Step H continued, and `--verify-commit` is skipped on
    `no_base` by design — an incomplete evidence set shipping green
    (external code review, medium).

    Parametrised over both bases precisely because the second was the hole: a
    single happy-path case would have left it open.
    """
    (adopted_repo / ".shipwright/compliance/sbom.md").unlink()
    argv = ("--base", head_sha(adopted_repo)) if base_argv else ()

    code, report = _stamp(adopted_repo, capsys, *argv)

    assert code != 0, f"{label}: an incomplete set was allowed to proceed"
    assert report["status"] == "incomplete_set", f"{label}: {report}"
    assert report["absent"] == [".shipwright/compliance/sbom.md"]
    assert report["stamped"] == [], f"{label}: stamped part of an incomplete set"
    assert "partial" not in report["detail"], (
        f"{label}: absence must not be described as an unstampable banner"
    )


def test_nothing_to_stamp_at_all_is_reported_rather_than_passing(
    adopted_repo, capsys,
):
    """Green-on-vacuum is the one thing a presence filter must not buy.

    Presence-filtering makes absence non-fatal, which is right per-document and
    wrong for the whole set: if Step F produced nothing, an `ok` with an empty
    `stamped` list would read as success.
    """
    for rel in STAMPABLE:
        (adopted_repo / rel).unlink()
    code, report = _stamp(adopted_repo, capsys, "--base", head_sha(adopted_repo))

    assert code != 0 and report["status"] == "no_documents", report
    assert report["stamped"] == []


def test_a_failed_write_puts_the_originals_back(adopted_repo, capsys, monkeypatch):
    """`write_back` has no rollback, so a raise mid-loop half-stamps the tree.

    Not exotic on Windows — the sibling `restore_to_head` documents a file held
    open by an editor and an index.lock race with a hook as ordinary there. The
    originals are still in the payload at that point, so they go back
    (Stage-2 code review).

    Patched on the module object that CALLS it (ADR-045): a name bound elsewhere
    stays bound to the real function here and the test would prove nothing.
    """
    original = {rel: (adopted_repo / rel).read_text(encoding="utf-8")
                for rel in STAMPABLE}
    victim = sorted(STAMPABLE)[2]

    def _half_write(root, payload):
        # Write two, then fail — the shape that leaves a mixed tree behind.
        for rel in sorted(payload)[:2]:
            (root / rel).write_bytes(payload[rel])
        raise OSError(13, "Permission denied", victim)

    monkeypatch.setattr(adopt_stamp, "write_back", _half_write)
    code, report = _stamp(adopted_repo, capsys, "--base", head_sha(adopted_repo))

    assert code != 0 and report["status"] == "write_failed", report
    assert report["unrestored"] == [], report
    for rel, text in original.items():
        assert (adopted_repo / rel).read_text(encoding="utf-8") == text, (
            f"{rel} kept its half-written stamp after the write failed"
        )
    assert _tree_is_clean(adopted_repo)


# --- the set, and the boundary ----------------------------------------------


def test_the_stamped_set_is_exactly_the_markdown_half_of_the_refresh_set():
    """Seven documents, five stamped — pinned so it cannot read as an oversight."""
    assert adopt_stamp.stampable_paths() == STAMPABLE
    assert len(STAMPABLE) == 5
    assert frozenset(REFRESH_SET) - STAMPABLE == {
        ".shipwright/compliance/test-traceability.json",
        ".shipwright/compliance/ci-security.json",
    }


def test_what_is_written_parses_back_to_what_was_meant(adopted_repo, capsys):
    """Boundary probe: this mode is a new writer on the banner's producer side.

    A stamp that renders is not the same as a stamp that reads back — the pair
    `banner_line` / `parse_banner_line` is the contract, so the round trip is the
    test rather than a substring match on the rendered line.
    """
    sha = head_sha(adopted_repo)
    _stamp(adopted_repo, capsys, "--base", sha)

    for rel in STAMPABLE:
        state = parse_banner_line((adopted_repo / rel).read_text(encoding="utf-8"))
        assert state is not None, f"{rel}: wrote a banner its own parser rejects"
        assert state.base == sha[:12]
        assert state.release is None
        assert state.run_id == RUN
