"""Cross-layer coverage sees a FOLDED acceptance criterion
(iterate-2026-07-27-name-the-blocker).

`shared/fr-authoring.md` §3 makes folding the common case: when a change
completes, fixes or extends something that already exists, you append an
acceptance criterion to the existing requirement rather than mint a new row.

The gate resolved behaviour change from FR **row** fields only — title and
required_layers — so a correctly folded change left the row untouched and always
landed in "no FR-row-level behaviour change was determinable". The pattern the
framework recommends was the one pattern its gate could not see.

This suite pins the PARSER that makes folding visible: turning a spec into a
digest per requirement, and reading a spec out of git. What the gate then DOES
with those digests — the union with row changes, what stays undecidable, and the
fail-closed wiring — lives in `test_layer_coverage_verdict.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers._layer_coverage_ac import (  # noqa: E402
    criteria_digests,
    spec_text_at,
)


# --- the parser ---------------------------------------------------------------

_SPEC = """\
# Spec

## Acceptance Criteria

### FR-01.01 — First thing

- (E) Given a change, when it runs, then it works.
- (E) Given a failure, when it runs, then it stops.

### FR-01.02 — Second thing

- (E) Given something else, then something else happens.
"""


def test_each_requirement_section_gets_its_own_digest():
    digests = criteria_digests(_SPEC)
    assert sorted(digests) == ["FR-01.01", "FR-01.02"]
    assert digests["FR-01.01"] != digests["FR-01.02"]


def test_appending_a_criterion_changes_only_that_requirement():
    """The fold. This is the case the gate used to be blind to."""
    before = criteria_digests(_SPEC)
    after = criteria_digests(
        _SPEC.replace(
            "- (E) Given a failure, when it runs, then it stops.",
            "- (E) Given a failure, when it runs, then it stops.\n"
            "- (E) Given a blocked merge, then the cause is named.",
        )
    )
    assert after["FR-01.01"] != before["FR-01.01"]
    assert after["FR-01.02"] == before["FR-01.02"]


def test_a_multiline_criterion_is_digested_whole():
    """External review, high severity — and this repo's own spec.md wraps its
    `(E)` bullets. Digesting only the first line of a criterion would miss an
    edit to its second line, which is where the actual guarantee often sits."""
    wrapped = _SPEC.replace(
        "- (E) Given a change, when it runs, then it works.",
        "- (E) Given a change, when it runs, then it works\n  and reports success.",
    )
    edited = wrapped.replace("and reports success.", "and reports failure.")
    assert criteria_digests(wrapped)["FR-01.01"] != criteria_digests(edited)["FR-01.01"]


def test_reflowing_a_criterion_is_not_a_change():
    """Whitespace-normalised: re-wrapping a paragraph must not demand
    executed-passing tests, or every formatting pass trips a HARD gate."""
    one_line = _SPEC.replace(
        "- (E) Given a change, when it runs, then it works.",
        "- (E) Given a change, when it runs,   then it works.",
    )
    two_lines = _SPEC.replace(
        "- (E) Given a change, when it runs, then it works.",
        "- (E) Given a change, when it runs,\n  then it works.",
    )
    assert criteria_digests(one_line)["FR-01.01"] == criteria_digests(two_lines)["FR-01.01"]


def test_prose_outside_a_criterion_is_not_a_criterion_change():
    """Deliberately narrow. In a post-rollout repo a resolved change is a HARD
    gate, so a typo fix in surrounding prose must not require new tests."""
    edited = _SPEC.replace("### FR-01.01 — First thing\n", "### FR-01.01 — First thing\n\nSome note.\n")
    assert criteria_digests(edited)["FR-01.01"] == criteria_digests(_SPEC)["FR-01.01"]


def test_checkbox_and_alternate_markers_are_criteria():
    """`fr-authoring.md` §3's worked example uses `- [ ]`; `*` and numbered
    lists are ordinary markdown. All are criteria."""
    for marker in ("- [ ] does a thing", "* does a thing", "+ does a thing", "1. does a thing"):
        spec = f"## Acceptance Criteria\n\n### FR-01.01 — T\n\n{marker}\n"
        assert criteria_digests(spec).get("FR-01.01")


def test_a_requirement_with_no_criteria_still_has_an_entry():
    spec = "## Acceptance Criteria\n\n### FR-01.01 — T\n\nnothing yet\n"
    assert "FR-01.01" in criteria_digests(spec)


def test_non_fr_headings_are_ignored():
    spec = "### Notes\n\n- (E) not a requirement\n\n### FR-01.01 — T\n\n- (E) real\n"
    assert sorted(criteria_digests(spec)) == ["FR-01.01"]


def test_empty_text_yields_nothing():
    assert criteria_digests("") == {}


def test_an_id_anchored_twice_pools_both_blocks_instead_of_last_write_wins():
    """External code review, medium, 2026-08-25: ``iter_anchored_blocks``'s wide
    anchor surface (any heading level, plus the bold form) makes a doubly-anchored
    id materially more likely than the old, narrower parser saw. A last-write-wins
    assignment would let a LATER, empty block for the same id silently overwrite
    an earlier, criteria-bearing one — collapsing the digest to the empty-criteria
    value and making this HARD gate see "no change" when there was one."""
    spec = (
        "## Acceptance Criteria\n\n"
        "### FR-01.01 — First anchor\n\n"
        "- (E) Given the first block, when read, then it counts.\n\n"
        "**FR-01.01: Second anchor**\n"
        "- (E) Given the second block, when read, then it ALSO counts.\n"
    )
    digests = criteria_digests(spec)
    empty_digest = criteria_digests(
        "## Acceptance Criteria\n\n### FR-01.01 — T\n\nnothing yet\n",
    )["FR-01.01"]
    first_block_only = criteria_digests(
        "## Acceptance Criteria\n\n### FR-01.01 — First anchor\n\n"
        "- (E) Given the first block, when read, then it counts.\n",
    )["FR-01.01"]
    second_block_only = criteria_digests(
        "## Acceptance Criteria\n\n**FR-01.01: Second anchor**\n"
        "- (E) Given the second block, when read, then it ALSO counts.\n",
    )["FR-01.01"]

    assert digests["FR-01.01"] != empty_digest
    assert digests["FR-01.01"] != first_block_only  # not JUST the first block
    assert digests["FR-01.01"] != second_block_only  # not JUST the second block


# --- reading a spec out of git ------------------------------------------------

def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "spec.md").write_text(_SPEC, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "one")
    return root


def test_reads_a_spec_at_a_commit(tmp_path):
    root = _repo(tmp_path)
    sha = _git(root, "rev-parse", "HEAD")
    assert "FR-01.01" in (spec_text_at(root, sha, "spec.md") or "")


def test_a_path_absent_at_that_commit_is_empty_not_an_error(tmp_path):
    """A spec file that did not exist at base is a real answer — every one of
    its requirements is new — not a failure to read history."""
    root = _repo(tmp_path)
    sha = _git(root, "rev-parse", "HEAD")
    assert spec_text_at(root, sha, "does/not/exist.md") == ""


def test_an_unreadable_commit_is_none_not_empty(tmp_path):
    """External review, high severity: `""` and "cannot read" must not collapse
    into the same value. Treating a broken history as an empty spec would
    conclude that no criteria changed and suppress the warning."""
    root = _repo(tmp_path)
    assert spec_text_at(root, "0" * 40, "spec.md") is None


def test_only_bullets_inside_the_acceptance_criteria_section_count():
    """External code review: bullets elsewhere in the document are not criteria.
    A requirement discussed under some other `##` section — with a bullet list of
    implementation notes — must not read as a criteria change, because in a
    post-rollout repo that is a HARD gate demanding executed-passing tests."""
    spec = (
        "## Design Notes\n\n### FR-01.01 — T\n\n- an implementation note\n\n"
        "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- (E) the real criterion\n"
    )
    edited = spec.replace("- an implementation note", "- a DIFFERENT implementation note")
    assert criteria_digests(edited)["FR-01.01"] == criteria_digests(spec)["FR-01.01"]


def test_criteria_stop_at_the_next_top_level_section():
    spec = (
        "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- (E) real\n\n"
        "## Open Questions\n\n- something else entirely\n"
    )
    before = criteria_digests(spec)
    after = criteria_digests(spec.replace("- something else entirely", "- changed"))
    assert after["FR-01.01"] == before["FR-01.01"]


def test_a_spec_without_an_acceptance_criteria_heading_still_parses():
    """Fail-safe: scoping must never make the gate go SILENT. A spec that names
    its criteria some other way is scanned whole rather than yielding nothing —
    a false green is the one outcome worse than over-firing."""
    spec = "# Spec\n\n### FR-01.01 — T\n\n- (E) a criterion\n"
    assert criteria_digests(spec).get("FR-01.01")


# --- delegation to lib.fr_criteria (campaign REQ3.04 R0) ---------------------
# External plan review, both reviewers (2026-08-25): this gate now inherits
# `fr_criteria`'s placeholder-rejection and marker-stripping, which the old
# in-module `_criteria` walk never did. Pin the new behaviour rather than
# leave it an unstated side effect of the delegation.


def test_placeholder_only_criterion_digests_the_same_as_no_criteria():
    """A `- [ ] TBD` bullet is now filtered as a placeholder, same as the old
    behaviour did NOT do. The digest becomes indistinguishable from "no
    criteria bullets at all" — both fold to the empty-string digest."""
    tbd = "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- [ ] TBD\n"
    empty = "## Acceptance Criteria\n\n### FR-01.01 — T\n\nnothing yet\n"
    assert criteria_digests(tbd)["FR-01.01"] == criteria_digests(empty)["FR-01.01"]


def test_assertion_marker_is_stripped_before_digesting():
    """`(E)` is decoration, not content — a bullet with and without the marker
    must digest identically."""
    marked = "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- (E) Given X, then Y.\n"
    unmarked = "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- Given X, then Y.\n"
    assert criteria_digests(marked)["FR-01.01"] == criteria_digests(unmarked)["FR-01.01"]


def test_a_real_criterion_still_digests_differently_from_a_placeholder():
    """The filtering is narrow: a real criterion is never mistaken for TBD."""
    real = "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- (E) Given X, then Y.\n"
    placeholder = "## Acceptance Criteria\n\n### FR-01.01 — T\n\n- [ ] TBD\n"
    assert criteria_digests(real)["FR-01.01"] != criteria_digests(placeholder)["FR-01.01"]


# --- Stage-3 doubt review, 2026-08-25 -----------------------------------------


def test_a_nested_fr_heading_still_gets_its_own_digest_entry():
    """A DEEPER heading nested inside a parent's block (`### FR-01.02` inside
    `## FR-01.01`) must still yield its own anchor — the old ``i = j`` jump in
    ``iter_anchored_blocks`` swallowed it into the parent's span instead of
    ever considering it as a candidate anchor (medium, 2026-08-25): the id
    vanished from BOTH sides of a diff, so ``criteria_changed_keys`` could
    never see it change. No wrapping ``## Acceptance Criteria`` heading here
    — the whole-document fail-safe scans it directly, exercising
    ``iter_anchored_blocks`` on exactly the reviewer's example."""
    spec = (
        "# Spec\n\n"
        "## FR-01.01 — Parent\n\n"
        "- (E) parent criterion\n\n"
        "### FR-01.02 — Nested\n\n"
        "- (E) nested criterion\n"
    )
    digests = criteria_digests(spec)
    assert "FR-01.01" in digests
    assert "FR-01.02" in digests
    assert digests["FR-01.01"] != digests["FR-01.02"]


def test_level_3_acceptance_criteria_heading_scopes_correctly():
    """`/shipwright-project`'s real spec.md nests the section one level
    deeper than `/shipwright-adopt`'s (`### Acceptance Criteria` under
    `## 2. Functional Requirements`, `spec-generation.md:305`, both the
    abstract template and its worked example) — a level-2-only regex never
    matched it, so ``_criteria_region`` fell back to whole-document scanning
    on every project-generated spec, not a rare exception (medium,
    2026-08-25). With the fix, a bolded FR reference OUTSIDE the level-3
    section (a cross-reference under the sibling `### Removed Requirements`
    heading, same shape a real spec's own template puts there) must not be
    pooled into that FR's digest."""
    spec = (
        "## 2. Functional Requirements\n\n"
        "### Acceptance Criteria\n\n"
        "**FR-01.01: Name**\n"
        "- [ ] real criterion\n\n"
        "### Removed Requirements\n\n"
        "Some note referencing **FR-01.01: Name** again elsewhere.\n"
        "- an unrelated bullet under that stray reference\n\n"
        "## 3. Constraints\n\n"
        "- something\n"
    )
    only_real = (
        "## 2. Functional Requirements\n\n"
        "### Acceptance Criteria\n\n"
        "**FR-01.01: Name**\n"
        "- [ ] real criterion\n"
    )
    assert criteria_digests(spec)["FR-01.01"] == criteria_digests(only_real)["FR-01.01"]


