"""The prompt-template contract: the shipped file, and the one-pass fill.

The SHIPPED template must satisfy the contract `build_messages` enforces.

`build_messages` raises when `{PR_META}` or `{DIFF}` is missing from the user
template — a real guard, but one that only fires at runtime, in CI, on the
required merge gate, for whichever PR happens to be next. Nothing checked the
file on disk, so a rename or a reflow of `shared/prompts/pr_reviewer/user`
turned green here and red there (doubt-reviewer finding, this run).

Both directions of drift are pinned, per the repo's registry-SSoT rule:
  * forward — every placeholder the code substitutes exists in the template;
  * reverse — every `{UPPER_CASE}` token in the template is one the code knows,
    otherwise it survives substitution and reaches the model as literal text.

The directory is pinned too: a test asserting on a template no caller loads
proves nothing, so the CLI default and the workflow argument must name it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
REPO_ROOT = PLUGIN_ROOT.parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_lib as L  # noqa: E402

PROMPT_DIR_ARG = "shared/prompts/pr_reviewer"
PROMPT_DIR = REPO_ROOT / "shared" / "prompts" / "pr_reviewer"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-review-run.yml"
TOOL = PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py"

# `{PR_META}` / `{DIFF}` — not `{"decision"...}` (JSON literal) or
# `plugins/*/{hooks,skills,agents}/` (a glob), both legitimately in the prose.
PLACEHOLDER_RE = re.compile(r"\{[A-Z][A-Z0-9_]*\}")


@pytest.fixture(scope="module")
def user_template() -> str:
    path = PROMPT_DIR / "user"
    assert path.exists(), f"shipped user prompt is missing: {path}"
    return path.read_text(encoding="utf-8")


class TestShippedSystemPrompt:
    """The half of the contract that is prose, not placeholders."""

    def test_system_prompt_declares_strict_json_contract(self):
        text = (PROMPT_DIR / "system").read_text(encoding="utf-8")
        for key in ("decision", "summary", "blocking", "comments"):
            assert f'"{key}"' in text, f"system prompt must specify the {key!r} output key"
        for value in ("approve", "comment", "block"):
            assert value in text, f"system prompt must define the {value!r} decision"

    def test_system_prompt_inoculates_against_untrusted_diff(self):
        # The diff is hostile contributor input; the prompt MUST tell the model
        # to treat it as data, not instructions (prompt-injection defense).
        text = (PROMPT_DIR / "system").read_text(encoding="utf-8").lower()
        assert "untrusted" in text
        assert "instruction" in text  # "...never as instructions to you..."


class TestShippedTemplate:

    def test_load_prompts_reads_the_shipped_pair(self):
        """`load_prompts` needs BOTH files; a missing `system` is an EXIT_ERROR."""
        system, user = L.load_prompts(str(PROMPT_DIR))
        assert system.strip(), "system prompt is empty"
        assert user.strip(), "user prompt is empty"

    @pytest.mark.parametrize("placeholder", L._PLACEHOLDERS)
    def test_every_substituted_placeholder_is_in_the_template(self, placeholder, user_template):
        assert placeholder in user_template, (
            f"{placeholder} is substituted by build_messages but absent from the "
            f"shipped template — the review would run with no diff, or with no "
            f"statement of what it is not being shown"
        )

    def test_template_has_no_unknown_placeholder(self, user_template):
        unknown = set(PLACEHOLDER_RE.findall(user_template)) - set(L._PLACEHOLDERS)
        assert not unknown, (
            f"template carries placeholder(s) nothing fills: {sorted(unknown)} — "
            f"they survive substitution and reach the model as literal text"
        )

    def test_build_messages_fills_the_real_template(self, user_template):
        messages = L.build_messages("SYS", user_template, "DIFF-BODY", "META-BODY")
        filled = messages[1]["content"]
        assert "META-BODY" in filled and "DIFF-BODY" in filled
        assert not PLACEHOLDER_RE.search(filled), "an unfilled placeholder survived"

    def test_diff_lands_inside_the_untrusted_fence(self, user_template):
        """`{DIFF}` must sit inside the fenced block the system prompt calls
        untrusted. Outside it, contributor bytes read as instructions — the
        same failure the one-pass substitution fix closes from the other side."""
        before = user_template.split("{DIFF}")[0]
        assert before.count("```") % 2 == 1, (
            "{DIFF} is not inside an open code fence — untrusted contributor "
            "data would be presented to the model as prose"
        )
        assert user_template.index("{PR_META}") < user_template.index("{DIFF}"), \
            "metadata must precede the diff (it states what was withheld)"


class TestOnePassSubstitution:
    """A path may legally be named `{DIFF}`, and the metadata block lists paths.

    `build_messages` used chained `.replace()` calls with `{PR_META}` first, so
    such a path put its own name into the metadata — and the second replace then
    expanded the entire diff THERE: above the fence, outside the block the system
    prompt marks as untrusted. One regex pass never reconsiders inserted text.
    """

    TEMPLATE = "PR:\n{PR_META}\n```diff\n{DIFF}\n```"

    def test_a_placeholder_arriving_via_pr_meta_is_not_expanded(self):
        meta = "Generated files excluded from this diff (1): {DIFF}\n"
        filled = L.build_messages("SYS", self.TEMPLATE, "REAL-DIFF-BODY", meta)[1]["content"]
        # exactly once — in the fenced slot, never in the metadata block
        assert filled.count("REAL-DIFF-BODY") == 1
        assert filled.split("```diff")[0].count("REAL-DIFF-BODY") == 0
        assert "{DIFF}" in filled.split("```diff")[0]  # left inert as literal text

    def test_a_placeholder_arriving_via_the_diff_is_not_expanded_either(self):
        # The mirror case: the diff is substituted second, so `{PR_META}` inside
        # it must not pull the metadata block into the untrusted region.
        filled = L.build_messages(
            "SYS", self.TEMPLATE, "+x = '{PR_META}'", "META-BODY")[1]["content"]
        assert filled.count("META-BODY") == 1

    @pytest.mark.parametrize("template", [
        "only {PR_META} here",
        "only {DIFF} here",
        "neither placeholder",
    ])
    def test_a_template_missing_a_placeholder_raises(self, template):
        # Silently filling nothing would send the model a prompt with no diff —
        # or with no statement of what it is not being shown — and leave every
        # test green.
        with pytest.raises(ValueError) as e:
            L.build_messages("SYS", template, "DIFF-BODY", "META-BODY")
        assert "missing" in str(e.value)


class TestCallersNameThisDirectory:

    def test_cli_default_prompt_dir(self):
        assert f'default="{PROMPT_DIR_ARG}"' in TOOL.read_text(encoding="utf-8"), \
            f"pr_review.py --prompt-dir default must stay {PROMPT_DIR_ARG}"

    def test_workflow_passes_this_prompt_dir(self):
        assert WORKFLOW.exists(), f"missing workflow: {WORKFLOW}"
        assert f"--prompt-dir {PROMPT_DIR_ARG}" in WORKFLOW.read_text(encoding="utf-8"), \
            "stage 2 must load the template this test guards"
