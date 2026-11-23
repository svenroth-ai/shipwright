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

import json
import subprocess
import sys

import pytest
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


_RELEASE_COMMIT = REPO_ROOT / "plugins" / "shipwright-changelog" / "scripts" / "lib" / "release_commit.py"


@pytest.mark.covers("FR-01.09/AC01")
def test_the_release_code_takes_the_computed_pathspec_instead():
    """The absence above is only safe because something else supplies the paths: since unit P4 ``release_commit.commit_pathspec``
    reads the ``evidence_pathspec`` that ``release.py sync`` kept from the tool."""
    source = _RELEASE_COMMIT.read_text(encoding="utf-8")
    assert "evidence_pathspec" in source and "REFRESH_SET" not in source, "the commit must use the tool's pathspec, not a list of its own"


def test_the_skill_still_forbids_the_directory_pathspec():
    """A directory pathspec commits every tracked file under it — the widening the
    pinned set exists to prevent, and the one shortcut an operator would reach for
    once the literal list is gone."""
    assert _PROHIBITION in _skill_text()


@pytest.mark.covers("FR-01.09/AC01")
def test_the_release_artifacts_are_still_committed():
    """The regression this file exists to catch: a rewrite of the commit that silently dropped ``decision_log.md`` and the ADR folder,
    taking the aggregator's INDEX.md repair with them. The pathspec is read from ``release_commit.commit_pathspec`` (own process)."""
    code = ("import json, sys\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\nfrom lib import release_commit\n"
            "print(json.dumps(release_commit.commit_pathspec(Path(sys.argv[2]), {})[2]))")
    done = subprocess.run([sys.executable, "-c", code, str(_RELEASE_COMMIT.parent.parent), str(REPO_ROOT)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    paths = json.loads(done.stdout)
    for required in ("CHANGELOG.md", ".shipwright/agent_docs/decision_log.md", ".shipwright/planning/adr/"):
        assert required in paths, f"the release commit no longer carries {required}"
