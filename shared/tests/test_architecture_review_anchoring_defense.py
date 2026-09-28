"""AC5 — the architecture pass's anchoring defense holds in code, not just prose.

`shared/prompts/architecture_reviewer/system`'s brief "deliberately does not
tell you which ones the author rejected, or why" — a promise the spec text
itself can break. Unlike the plan side's plan.md/spec.md split, the iterate
spec is the ONE document: `## Internal Plan Review` / `## Internal
Architecture Review` / `## Self-Review` all land in the very file handed to
this mode as --spec-file, each carrying the disposition-plus-reason the brief
exists to withhold. `strip_prior_review_sections` (external_review_modes.py)
is the code-level backstop; these tests prove it actually runs for
`--mode architecture` and is skipped for `--mode iterate`, where the
rejection rationale is intentionally shown (Stage-3 doubt review, high, D1).
"""

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SHARED / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _run_main_capturing_strip_calls(monkeypatch, spec, primary_file, mode, primary_flag):
    """In-process `main()` call with `strip_prior_review_sections` spied on.

    In-process (not subprocess) so the monkeypatch is visible — mirrors
    `test_main_iterate_mode_loads_iterate_prompts` in test_external_review_cli.py.
    Spies on the strip call directly, not on a provider call three steps
    downstream, so the assertion holds regardless of which provider branch a
    keyless run takes.
    """
    for key in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(spec.parent)
    import external_review
    real_strip = external_review.strip_prior_review_sections

    def spy(text):
        result = real_strip(text)
        seen.append(result)
        return result

    seen: list[str] = []
    monkeypatch.setattr(external_review, "strip_prior_review_sections", spy)
    plugin_root = spec.parent / "unused-plugin"
    plugin_root.mkdir(exist_ok=True)
    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", mode, "--spec-file", str(spec),
        primary_flag, str(primary_file), "--plugin-root", str(plugin_root),
        "--driver", "claude",
    ])
    rc = external_review.main()
    return rc, seen


def test_architecture_mode_strips_prior_review_sections_before_use(monkeypatch, tmp_path):
    """The architecture pass's anchoring defense (shared/prompts/architecture_reviewer
    /system: the brief "deliberately does not tell you which ones the author
    rejected, or why") depends on the spec not carrying that rationale. Unlike
    the plan side's plan.md/spec.md split, the iterate spec is the ONE document:
    `## Internal Plan Review` / `## Internal Architecture Review` / `## Self-Review`
    all land in the very file handed to this mode as --spec-file, each carrying
    the disposition-plus-reason the brief exists to withhold. A prose-only
    instruction does not stop that (Stage-3 doubt review, high)."""
    spec = tmp_path / "spec.md"
    brief = tmp_path / "architecture_brief.md"
    spec.write_text(
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y\n\n"
        "## Verification (medium+)\nRun tests.\n",
        encoding="utf-8",
    )
    brief.write_text("# Brief\n\n## Options on the table\n- A\n- B\n", encoding="utf-8")

    rc, seen = _run_main_capturing_strip_calls(monkeypatch, spec, brief, "architecture", "--brief-file")
    assert rc == 0
    assert seen, "strip_prior_review_sections was never called for --mode architecture"
    assert "Internal Plan Review" not in seen[-1]
    assert "rejected option B because Y" not in seen[-1]
    assert "## Goal" in seen[-1] and "Do X." in seen[-1], "unrelated sections must survive"


def test_iterate_mode_does_not_strip_prior_review_sections(monkeypatch, tmp_path):
    """Iterate mode intentionally shows the mini-plan's own rejection rationale
    — only architecture mode's anchoring defense needs the strip."""
    spec = tmp_path / "spec.md"
    plan = tmp_path / "mini-plan.md"
    spec.write_text(
        "# Spec\n\n## Internal Plan Review (opus-plan-reviewer)\nkept\n",
        encoding="utf-8",
    )
    plan.write_text("# Mini-plan\nStep 1.", encoding="utf-8")

    rc, seen = _run_main_capturing_strip_calls(monkeypatch, spec, plan, "iterate", "--plan-file")
    assert rc == 0
    assert not seen, "iterate mode must not call the architecture-only strip"
