"""Plan-side review-prompt verifier.

Asserts that plan_reviewer/ prompts still ship with this plugin.

iterate_reviewer/ prompts moved to shared/prompts/ — see
shared/tests/test_external_review_prompts.py for those.
"""

from pathlib import Path


class TestPlanPromptsShipWithPlugin:
    @staticmethod
    def _plugin_root() -> Path:
        return Path(__file__).resolve().parent.parent

    def test_plan_reviewer_prompts_exist(self):
        prompts_dir = self._plugin_root() / "prompts" / "plan_reviewer"
        assert (prompts_dir / "system").exists(), "plan_reviewer/system prompt missing"
        assert (prompts_dir / "user").exists(), "plan_reviewer/user prompt missing"

    def test_plan_user_prompt_has_placeholders(self):
        user_prompt = (
            self._plugin_root() / "prompts" / "plan_reviewer" / "user"
        ).read_text()
        assert "{PLAN}" in user_prompt
        assert "{SPEC}" in user_prompt

    def test_plan_user_prompt_mentions_specification(self):
        user_prompt = (
            self._plugin_root() / "prompts" / "plan_reviewer" / "user"
        ).read_text()
        assert "specification" in user_prompt.lower()
