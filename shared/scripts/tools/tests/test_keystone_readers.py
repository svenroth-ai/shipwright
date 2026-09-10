"""P3.6 — the two criteria readers, and the guard for where they disagree.

AC-K9(d) (the reader-divergence guard, SCOPED to this PR's diff) and AC-K15 (the
repo-wide drift pin) of
``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md``.

**The readers are not interchangeable, and assuming they were is what an earlier
draft of this design got wrong:**

* ``ac_identity.read_all`` — heading-anchored only, ``strict=True``: only the
  CONTIGUOUS LEADING bullet run under the heading counts.
* ``_layer_coverage_ac.criteria_digests`` — headings PLUS the legacy bold-anchor
  form, and ``strict=False`` deliberately, so an introductory note between an
  FR's heading and its bullets does not hide them.

So an FR whose bullets follow one ordinary sentence yields ZERO criteria from the
first and NON-ZERO from the second. Round 1 made that shape an exit 2 — an "infra
failure" with no authoring remedy, which adding one sentence anywhere would have
triggered. Round 2 downgraded it to exit 1 but left it firing on ANY active FR in
the repo, so the day one such sentence landed, EVERY later PR would red including
docs-only ones. The shipped rule fires only when the FR-level reader says *this
PR* changed that FR's criteria — a repo-wide condition is a drift TEST's job, and
that test is at the bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # shared/scripts

from lib import ac_identity  # noqa: E402
from verifiers import _keystone_ac_digest as kd  # noqa: E402
from verifiers._layer_coverage_ac import criteria_digests  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import git as _git  # noqa: E402
from _keystone_repo import make_repo  # noqa: E402
from _keystone_repo import manifest as _manifest  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]

#: An FR whose bullets are preceded by an ordinary sentence. `read_all` sees zero
#: criteria here; `criteria_digests` sees two.
_DIVERGENT_FR = """### FR-01.02: Gadgets

This section describes the gadget subsystem.

- [AC03] The gadget must whirr.
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def _change_set(repo: Path, head_sha: str):
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    return kd.ac_change_set(repo, base, head_sha, _manifest(), _manifest())


def test_the_two_readers_genuinely_disagree_on_this_shape():
    """The premise, pinned first. Everything below is only meaningful while the
    two readers really do differ on an intro-sentence FR — if a future change
    aligns them, this test fails and the guard can be deleted rather than left
    as machinery guarding nothing."""
    text = "### FR-09.09: Thing\n\nAn introductory sentence.\n\n- [AC01] It must work.\n"
    assert ac_identity.read_all(text)["FR-09.09"] == []
    assert criteria_digests(text).get("FR-09.09")


def test_a_divergent_fr_inside_this_prs_diff_is_reported(repo):
    """AC-K9(d)(i) — exit 1 with an authoring remedy, never exit 2 and never
    "no ACs changed".

    **This test found a hole in the design's scoping rule and is written to fail
    against it.** §5.1 scoped the guard to ``criteria_digests(base)[fr] !=
    criteria_digests(head)[fr]`` alone. But ADDING an introductory sentence
    changes no criterion TEXT, so that digest is byte-identical across the very
    PR that creates the divergence (asserted below) — the guard would never fire
    on the change that causes it. The AC then vanishes from ``read_all``, and the
    next PR to edit it reads ``added`` rather than ``changed``, i.e. never blocks
    on greenness: the two-PR version of the dodge. The shipped rule adds "the AC
    reader could see this FR at base and cannot now" as a second signal.
    """
    divergent_spec = BASE_SPEC.replace(
        "### FR-01.02: Gadgets\n\n- [AC03] The gadget must whirr.\n", _DIVERGENT_FR)
    head = _commit_spec(repo, divergent_spec)
    assert criteria_digests(BASE_SPEC)["FR-01.02"] == criteria_digests(
        divergent_spec)["FR-01.02"], "the FR-level digest must be UNCHANGED here"
    cs = _change_set(repo, head)
    assert cs.reader_divergence == ["FR-01.02"]


def test_a_pre_existing_divergence_the_pr_does_not_touch_is_invisible(repo):
    """AC-K9(d)(ii) — THE blast-radius pin, written to fail against round 2's
    unscoped guard.

    The divergent FR is introduced in an EARLIER commit, then a later commit
    edits a DIFFERENT FR. An unscoped guard reds this PR — and by the same rule
    every docs-only PR in the repo forever, contradicting AC-K1.
    """
    diverged = BASE_SPEC.replace(
        "### FR-01.02: Gadgets\n\n- [AC03] The gadget must whirr.\n", _DIVERGENT_FR)
    _commit_spec(repo, diverged, "pre-existing divergence, not this PR's doing")
    head = _commit_spec(repo, diverged.replace(
        "The widget must fizz.", "The widget must fizz TWICE."))
    cs = _change_set(repo, head)
    assert cs.reader_divergence == []
    assert cs.changed == {("FR-01.01", "AC01")}


def test_a_brand_new_divergent_fr_does_not_raise_on_the_base_lookup(repo):
    """The ``.get(fr)`` half of the fix: an FR absent at base would make a bare
    subscript raise ``KeyError`` INSIDE the guard — an infra-shaped crash for an
    ordinary authoring mistake.

    The head manifest carries a node for the new FR because that is what CI
    produces: ``build_requirement_index`` parses requirements out of the SPEC
    TEXT, not out of ``@covers`` tags, so every FR declared in ``spec.md`` gets a
    node whether or not any test names it. The earlier fixture omitted it and so
    modelled a state the regeneration step cannot emit — which is why adding the
    active-FR filter below made it fail.
    """
    head = _commit_spec(repo, BASE_SPEC + "\n" + _DIVERGENT_FR.replace(
        "FR-01.02", "FR-01.03"))
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    cs = kd.ac_change_set(
        repo, base, head,
        _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03")), _manifest(),
    )
    assert cs.reader_divergence == ["FR-01.03"]


def test_a_RETIRED_fr_with_the_divergent_shape_is_exempt(repo):
    """Stage-1 spec review (minor). The design states the predicate twice as
    "``read_all`` yields zero criteria for an **ACTIVE** FR" (§5.1, AC-K9(d)), and
    every sibling predicate in this gate filters to active nodes — ``_links_for``,
    ``_keystone_layer_gap._fr_node``, ``_active_display_ids``. This guard had
    dropped the qualifier by omission.

    Unreachable in this repo today, which is precisely the "latent, so leave it"
    reasoning round 3 already rejected once: an FR's ``spec.md`` heading survives
    retirement, so the day a retired FR gains an introductory sentence, an
    unfiltered guard HARD-blocks a PR over a requirement nothing else in the gate
    enforces.
    """
    head = _commit_spec(repo, BASE_SPEC + "\n" + _DIVERGENT_FR.replace(
        "FR-01.02", "FR-01.03"))
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    retired = _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))
    retired["requirements"]["ns::FR-01.03"]["status"] = "retired"

    cs = kd.ac_change_set(repo, base, head, retired, _manifest())
    assert cs.reader_divergence == [], "a retired FR is out of scope, as for every sibling"

    active = _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))
    same_input = kd.ac_change_set(repo, base, head, active, _manifest())
    assert same_input.reader_divergence == ["FR-01.03"], (
        "the SAME spec diff must still fire while the FR is active -- otherwise this "
        "test would pass against a guard that never fires at all"
    )


def test_a_new_fr_stating_no_criterion_at_all_is_reported_separately(repo):
    """Arm 2's own input, told apart from divergence: the FR has NO bullets, so
    both readers agree there is nothing there. The remedy differs ("state a
    criterion" vs "move the note below the bullets"), so the classes must not be
    collapsed."""
    manifest = _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))
    head = _commit_spec(repo, BASE_SPEC + "\n### FR-01.03: Empties\n\nNothing yet.\n")
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    cs = kd.ac_change_set(repo, base, head, manifest, _manifest())
    assert cs.new_frs_without_criteria == ["FR-01.03"]
    assert cs.reader_divergence == []


def test_a_new_fr_with_unminted_bullets_is_not_ALSO_reported_as_stating_none(repo):
    """Precedence, arm 1 over arm 2 (Stage-2 code review, medium): a brand-new
    FR hand-authored with bullets but no ``[ACnn]`` markers yet is already
    reported by arm 1 (``unminted_changed``) — it must not ALSO land in
    ``new_frs_without_criteria``, whose message ("states no acceptance
    criterion") would then be false: it states criteria, just unminted ones.
    This is the single most likely first real-world encounter with the gate —
    an FR authored before running the minter."""
    manifest = _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))
    head = _commit_spec(
        repo,
        BASE_SPEC + "\n### FR-01.03: Widgets\n\n- The widget must spin.\n",
    )
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    cs = kd.ac_change_set(repo, base, head, manifest, _manifest())
    assert [fr for fr, _ in cs.unminted_changed] == ["FR-01.03"]
    assert cs.new_frs_without_criteria == []


def test_an_fr_present_at_base_SPEC_but_missing_from_the_base_MANIFEST_is_not_new(repo):
    """Stage-2 code review, medium: arm 2's "new active FR" predicate is
    `active(head manifest) - active(base manifest)`, but the manifest is
    REGENERATED at head and read from the last COMMIT at base — and the two
    are known to drift (the traceability drift step is advisory, not a hard
    gate). An FR whose heading already existed in the base SPEC, with no
    criteria at all, is not "new in this PR" merely because a stale base
    manifest never carried it; without the spec-derived exclusion this would
    HARD-block an unrelated PR that never touched the FR. Genuinely pinned:
    the FR carries NO minted criteria, so arm 2's other conjunct
    (`not any(k[0] == fr_id for k in head_minted)`) cannot save this test on
    its own -- only the `base_fr_digests` exclusion can."""
    head = base = _commit_spec(repo, BASE_SPEC + "\n### FR-01.03: Empties\n\nNothing yet.\n")
    base_manifest = _manifest(ids=("FR-01.01", "FR-01.02"))  # FR-01.03 missing here...
    head_manifest = _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))  # ...but present here
    cs = kd.ac_change_set(repo, base, head, head_manifest, base_manifest)
    assert cs.new_frs_without_criteria == []
    assert not cs.changed and not cs.added and not cs.removed and not cs.reader_divergence
    # Companion, so this guard cannot pass merely because arm 2 never fires
    # for this FR shape: `test_a_new_fr_stating_no_criterion_at_all_is_reported_separately`
    # (above) uses the identical FR-01.03 shape genuinely absent from the base
    # SPEC and asserts arm 2 DOES fire for it.


def test_an_absent_base_manifest_suppresses_the_new_fr_arm_entirely(repo):
    """External plan review (glm, low) asked for arm 2's set operation to be
    stated; stating it exposed a repo-wide false red.

    "NEW active FR" is `active(head) - active(base)`. Under
    `base_manifest_absent` the base side is EMPTY, so **every** head FR
    trivially reads as new and arm 2 fires for every criteria-less FR in the
    repo at once — the same blast-radius mistake round 3 fixed for the
    divergence guard, in the one mode that is already degraded. "New" is not
    answerable without a base to be new relative to, so it is not answered.
    """
    head = _commit_spec(repo, BASE_SPEC + "\n### FR-09.09: Empties\n\nNothing yet.\n")
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    manifest = _manifest(ids=("FR-01.01", "FR-01.02", "FR-09.09"))
    with_base = kd.ac_change_set(repo, base, head, manifest, _manifest())
    assert with_base.new_frs_without_criteria == ["FR-09.09"], "the arm works normally"

    no_base = kd.ac_change_set(repo, base, head, manifest, {})
    assert no_base.new_frs_without_criteria == []
    assert any("unanswerable" in w for w in no_base.warnings), (
        "suppression must be warned about, never silently inferred"
    )


def test_an_fr_that_is_new_and_divergent_reports_divergence_only(repo):
    """The precedence rule at the change-set level: an FR that is both new and
    divergent must not be handed to the evaluator as BOTH, or the operator gets
    two findings whose remedies contradict each other."""
    manifest = _manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))
    head = _commit_spec(repo, BASE_SPEC + "\n" + _DIVERGENT_FR.replace(
        "FR-01.02", "FR-01.03"))
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    cs = kd.ac_change_set(repo, base, head, manifest, _manifest())
    assert cs.reader_divergence == ["FR-01.03"]
    assert cs.new_frs_without_criteria == []


# --------------------------------------------------------------------------
# AC-K15 — the repo-wide drift pin
# --------------------------------------------------------------------------

def test_the_two_readers_agree_on_this_repos_real_spec_md():
    """AC-K15. A divergence anywhere in the real spec is caught the day it
    appears — by a failing test that NAMES the FR, never by redding an unrelated
    PR. This is the correct division of labour the scoping above depends on.
    """
    spec = _REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"
    if not spec.is_file():  # pragma: no cover - the repo always has one today
        pytest.skip(f"no spec.md at {spec}")
    text = spec.read_text(encoding="utf-8")
    by_ac_reader = ac_identity.read_all(text)
    by_fr_reader = criteria_digests(text)
    divergent = sorted(
        fr for fr, digest in by_fr_reader.items()
        if digest != kd._EMPTY_CRITERIA_DIGEST and not by_ac_reader.get(fr)
    )
    assert not divergent, (
        f"{len(divergent)} FR(s) are visible to _layer_coverage_ac.criteria_digests but "
        f"invisible to ac_identity.read_all: {divergent}. Their acceptance criteria are not a "
        "contiguous leading bullet run under the FR heading — move the introductory prose below "
        "the bullets. Until then the keystone gate cannot see those FRs' criteria at all."
    )
