"""F39 — the Gitleaks-install step must really run with ``pipefail``.

The "Install Gitleaks" step downloads a tarball and verifies its SHA256 in a
pipeline (``echo "<sha>  <file>" | sha256sum -c -``) before extracting. That
gate only fails the step if a non-terminal pipeline element's failure
propagates — i.e. only under ``-o pipefail``.

A code comment used to claim "the default GitHub-Actions bash shell runs with
``-eo pipefail``". That is false: GitHub's implicit ``run:`` shell on Linux is
``bash -e {0}`` (no ``pipefail``); ``-o pipefail`` is added ONLY when the step
sets ``shell: bash`` explicitly. The step was safe today merely because the
verify command happened to be pipeline-last, but a maintainer extending it
(e.g. ``... | sha256sum -c | tee log``) while trusting the comment would
silently lose the gate.

The fix sets ``shell: bash`` on the step (making ``pipefail`` real, matching
the comment) across the monorepo's own workflows AND the adopt-shipped
template. This test pins that invariant and guards against the inaccurate
comment returning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — guaranteed root dependency

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOW_FILES = [
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "security.yml",
    REPO_ROOT / "shared" / "templates" / "github-actions" / "security.yml.template",
]

# The exact false claim the F39 fix removed — guard against its return.
_FALSE_COMMENT_FRAGMENT = "default GitHub-Actions bash shell"


def _gitleaks_step(workflow_path: Path) -> dict:
    """Return the single ``Install Gitleaks`` step dict from a workflow file."""
    assert workflow_path.exists(), (
        f"{workflow_path} is missing — F39 guard cannot locate the Gitleaks "
        f"install step; update WORKFLOW_FILES if the workflow moved."
    )
    doc = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    steps: list = []
    for job in (doc.get("jobs") or {}).values():
        if isinstance(job, dict):
            steps.extend(job.get("steps") or [])
    matches = [
        s for s in steps
        if isinstance(s, dict) and s.get("name") == "Install Gitleaks"
    ]
    assert len(matches) == 1, (
        f"expected exactly one 'Install Gitleaks' step in {workflow_path.name}, "
        f"found {len(matches)} — a rename would silently drop this guard."
    )
    return matches[0]


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_gitleaks_step_sets_shell_bash(workflow_path: Path) -> None:
    """``shell: bash`` is what actually activates ``-o pipefail`` — without it
    the SHA256-verify pipeline cannot gate a checksum mismatch."""
    step = _gitleaks_step(workflow_path)
    assert step.get("shell") == "bash", (
        f"{workflow_path.name}: Install Gitleaks step must set `shell: bash` so "
        f"the SHA256-verify pipeline runs under `-o pipefail`. Found shell="
        f"{step.get('shell')!r} (implicit default is `bash -e`, no pipefail)."
    )


@pytest.mark.parametrize("workflow_path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_no_false_default_pipefail_comment(workflow_path: Path) -> None:
    """The inaccurate "default GitHub-Actions bash shell runs with -eo
    pipefail" comment must not return — it would mislead a maintainer into
    extending the pipeline without an explicit `shell: bash`."""
    text = workflow_path.read_text(encoding="utf-8")
    assert _FALSE_COMMENT_FRAGMENT not in text, (
        f"{workflow_path.name} carries the false '{_FALSE_COMMENT_FRAGMENT}' "
        f"claim again. The default `run:` shell is `bash -e` (no pipefail); "
        f"pipefail comes only from an explicit `shell: bash`."
    )
