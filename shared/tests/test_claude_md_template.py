"""Pin the iterate-discoverability content in the CLAUDE.md template.

Both pipelines that produce a CLAUDE.md for a Shipwright-managed
project must surface the same iterate workflow:

- `shared/templates/claude-md-template.md` — read by /shipwright-project
  (greenfield) per `plugins/shipwright-project/skills/project/references/
  project-scaffolding.md`.
- `plugins/shipwright-adopt/scripts/lib/artifact_writer.py:_render_claude_md`
  — hardcoded f-string used by /shipwright-adopt (brownfield).

The two are split-brain by design (template-loading vs hardcoded
render), so this test asserts the content stays mirrored. Drift here
means greenfield and brownfield projects ship different onboarding
text — exactly the kind of inconsistency that lost adopted users
the CHANGELOG-fragment + ADR conventions before this iterate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "shared" / "templates" / "claude-md-template.md"


# Bullets that must appear in BOTH the template and adopt's rendered
# output. Substring matches — full prose lives in the source files.
REQUIRED_ITERATE_BULLETS = (
    "/shipwright-iterate",
    "Do NOT edit code directly",
    "ADR",
    "CHANGELOG",
    "Conventional Commits",
    "iterate/",
)


def test_template_file_lists_what_iterate_handles() -> None:
    """Greenfield path: the template file itself surfaces the bullets."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    for bullet in REQUIRED_ITERATE_BULLETS:
        assert bullet in body, (
            f"claude-md-template.md missing required bullet {bullet!r} — "
            f"greenfield CLAUDE.md will not surface iterate-workflow rules."
        )


def test_template_warns_against_other_skills() -> None:
    """Adopted/onboarded projects must not use the pre-onboarding skills
    (project/plan/build) directly — iterate is the single entry point."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "shipwright-project" in body
    assert "shipwright-plan" in body
    assert "shipwright-build" in body


def test_adopt_rendered_claude_md_mirrors_template_iterate_bullets() -> None:
    """Brownfield path: adopt's hardcoded `_render_claude_md` must
    surface the same bullets as the template. Subprocess-load of
    artifact_writer to avoid the `lib` namespace collision documented
    in shared/tests/test_verifiers_adopt.py.
    """
    adopt_scripts = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys; sys.path.insert(0, r'"
        + str(adopt_scripts).replace("\\", "\\\\")
        + "');\n"
        "from lib.artifact_writer import _render_claude_md\n"
        "out = _render_claude_md(\n"
        "    project_name='Demo', profile='vite-hono',\n"
        "    stack={'runtime': {}, 'frontend': {}, 'backend': {},\n"
        "           'database': {}, 'auth': {}},\n"
        "    commands={'build': 'x', 'test': 'x', 'dev': 'x'},\n"
        "    product_description='demo',\n"
        ")\n"
        "import sys; sys.stdout.buffer.write(out.encode('utf-8'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", helper],
        capture_output=True, check=True,
    )
    body = result.stdout.decode("utf-8")
    for bullet in REQUIRED_ITERATE_BULLETS:
        assert bullet in body, (
            f"adopt's rendered CLAUDE.md missing required bullet {bullet!r} — "
            f"brownfield CLAUDE.md drifted from claude-md-template.md."
        )
