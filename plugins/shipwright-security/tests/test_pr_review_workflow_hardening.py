"""Supply-chain + injection hardening for the two-stage Tier-3 PR review
workflows (B4.5, FR-01.17). Split out of test_pr_review_workflow_shape.py to
keep that module inside the file-size guideline
(iterate-2026-08-31-pr-review-deepseek-model) — these checks are generic
workflow-hardening concerns, independent of the tier/waiver logic the sibling
module covers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE1_PATH = REPO_ROOT / ".github" / "workflows" / "pr-review.yml"
STAGE2_PATH = REPO_ROOT / ".github" / "workflows" / "pr-review-run.yml"


def _read(path: Path) -> str:
    assert path.exists(), f"missing workflow: {path}"
    return path.read_text(encoding="utf-8")


class TestHardening:

    @pytest.mark.parametrize("path", [STAGE1_PATH, STAGE2_PATH])
    def test_third_party_actions_sha_pinned(self, path):
        text = _read(path)
        for m in re.finditer(r"uses:\s*astral-sh/setup-uv@(\S+)", text):
            assert re.fullmatch(r"[0-9a-f]{40}", m.group(1)), \
                f"astral-sh/setup-uv must be SHA-pinned, got {m.group(1)!r}"

    @pytest.mark.parametrize("path", [STAGE1_PATH, STAGE2_PATH])
    def test_no_direct_github_context_in_run_body(self, path):
        # run-shell-injection guard: never interpolate ${{ github.* }} directly
        # inside a `run:` shell body — hoist into env first. Tracks the run-block
        # by indentation so the legitimate `${{ github.* }}` in `env:` blocks is
        # not flagged (only deeper-indented run-block lines count).
        text = _read(path)
        offenders = []
        run_indent = None
        for line in text.splitlines():
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if run_indent is not None:
                if indent > run_indent:
                    if "${{ github." in line:
                        offenders.append(line.strip())
                    continue
                run_indent = None  # block ended (dedent to <= run: indent)
            stripped = line.strip()
            if stripped.startswith("run:"):
                if "${{ github." in line:  # inline run on the same line
                    offenders.append(stripped)
                if stripped in ("run: |", "run: >") or stripped.startswith(("run: |", "run: >")):
                    run_indent = indent
        assert not offenders, f"raw ${{{{ github.* }}}} in run body (injection risk): {offenders}"
