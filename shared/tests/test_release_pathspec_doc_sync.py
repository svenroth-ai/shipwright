"""The release skill does not duplicate the evidence registry in prose.

Subject: `plugins/shipwright-changelog/skills/changelog/SKILL.md` Step 6 vs
`lib.compliance_refresh.REFRESH_SET` (iterate-2026-07-31-derived-docs-at-release).

An earlier draft spelled the seven paths out in the skill and pinned them here by
set equality. That traded one failure mode for another: prose that silently falls
behind the registry, and — measured on this very run — a rewrite of that block
that quietly dropped two unrelated release artifacts from the commit.

So the skill names NO evidence path at all. It uses the `evidence_pathspec` the
tool computes from `REFRESH_SET`, which cannot drift and is already
presence-filtered for a project that has never run a CI scan. This test enforces
that absence, which is the only thing left that a human can get wrong.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.compliance_refresh import REFRESH_SET  # noqa: E402

_SKILL = (REPO_ROOT / "plugins" / "shipwright-changelog" / "skills" / "changelog"
          / "SKILL.md")
#: The one place a compliance path may legitimately appear: the prohibition itself.
_PROHIBITION = "never `.shipwright/compliance/`"


def _skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_the_skill_names_no_individual_evidence_path():
    """Naming one means naming all seven, and a list in prose is what drifts."""
    text = _skill_text().replace(_PROHIBITION, "")
    named = sorted(rel for rel in REFRESH_SET if rel in text)
    assert not named, (
        "the release skill hardcodes evidence paths, which duplicates "
        f"REFRESH_SET and will drift from it: {named}. Use the tool's "
        "`evidence_pathspec` instead."
    )


def test_the_skill_points_at_the_computed_pathspec_instead():
    """The absence above is only safe because something else supplies the paths."""
    assert "evidence_pathspec" in _skill_text(), (
        "Step 6 must tell the operator where the evidence paths come from"
    )


def test_the_skill_still_forbids_the_directory_pathspec():
    """A directory pathspec commits every tracked file under it — the widening the
    pinned set exists to prevent, and the one shortcut an operator would reach for
    once the literal list is gone."""
    assert _PROHIBITION in _skill_text()


def test_the_release_artifacts_are_still_committed():
    """The regression this file now exists to catch. Rewriting Step 6 to fix the
    directory-pathspec problem silently dropped `decision_log.md` and the ADR
    folder from the release commit, taking the aggregator's INDEX.md repair with
    them."""
    text = _skill_text()
    commit = re.search(r"git commit -m \"chore\(release\): v\{version\}\" --(.*?)\n\n",
                       text, re.DOTALL)
    assert commit, "could not find the Step 6 release commit — update this reader"
    for required in ("CHANGELOG.md",
                     ".shipwright/agent_docs/decision_log.md",
                     ".shipwright/planning/adr/"):
        assert required in commit.group(1), (
            f"the release commit no longer carries {required}"
        )
