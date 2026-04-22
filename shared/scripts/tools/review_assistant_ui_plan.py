"""Ad-hoc driver: run external LLM review on the assistant-ui migration plan.

This is a one-off campaign tool, not part of the pipeline canon. It
loads the plan markdown, feeds it to `lib.llm_review.run_review` with a
plan-specific system prompt, and writes the review output to
`~/.claude/plans/assistant-ui-migration-review.md`.

Usage:
    uv run shared/scripts/tools/review_assistant_ui_plan.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_env_local(repo_root: Path) -> None:
    """Load OPENROUTER_API_KEY from .env.local if present — mirrors what
    other shipwright scripts do so the review picks up the key without
    a global export."""
    env_file = repo_root / ".env.local"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    _load_env_local(repo_root)

    # Locate the plan. Prefer ~/.claude/plans; fall back to argv[1].
    default_plan = Path.home() / ".claude" / "plans" / "assistant-ui-migration.md"
    plan_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_plan
    if not plan_path.exists():
        print(f"ERROR: plan not found at {plan_path}", file=sys.stderr)
        return 2

    plan_text = plan_path.read_text(encoding="utf-8")

    # Inject repo path into sys.path so we can import lib.llm_review
    sys.path.insert(0, str(repo_root / "shared" / "scripts"))
    from lib.llm_review import run_review, detect_provider

    provider = detect_provider()
    if provider == "none":
        print(
            "ERROR: no OPENROUTER_API_KEY (or direct GEMINI_API_KEY/OPENAI_API_KEY) "
            "found in env or .env.local. Cannot run external review.",
            file=sys.stderr,
        )
        return 3

    print(f"[review] provider: {provider}", file=sys.stderr)
    print(f"[review] plan size: {len(plan_text)} chars", file=sys.stderr)

    system_prompt = (
        "You are a senior software architect reviewing an implementation plan "
        "for a TypeScript/React monorepo. You are blunt, concise, and focused "
        "on de-risking. Call out concrete failure modes the author missed. "
        "Distinguish between BLOCKER (do not proceed), MAJOR (fix before merge), "
        "and MINOR (nice to have). Do NOT rewrite the plan; critique it."
    )

    user_prompt = (
        "Review the implementation plan below. The team has been stuck in a "
        "14-iteration loop of band-aid fixes and wants to vendor an upstream "
        "UI library to escape. The author has explicitly answered review "
        "questions at the bottom of the plan — address those directly AND "
        "anything else you see as a risk.\n\n"
        "Priority concerns the team cares about most:\n"
        "- Does sub-iterate ordering make sense, or should C run first?\n"
        "- Are the test/UAT gates strong enough to catch the 'unit-tests-"
        "green-but-UI-broken' class of failure?\n"
        "- Is there a simpler architecture we should consider before "
        "committing to this?\n\n"
        "Format your response as:\n"
        "## Verdict (ship / revise / block)\n"
        "## Blockers\n"
        "## Major issues\n"
        "## Minor issues / suggestions\n"
        "## Answers to author's review questions (numbered 1-8)\n\n"
        "## Plan under review\n\n{CONTENT}\n\n## Context\n{CONTEXT}"
    )

    context = (
        "Monorepo: shipwright (SDLC framework built on Claude Code plugins). "
        "The affected app is webui/ — a local-first Hono+React Command Center "
        "that drives Claude Code CLI as a subprocess. Existing stack: React 19, "
        "Vite 6, Tailwind 4, Radix UI, TanStack Query 5. No auth (single-user "
        "local). Tests: vitest (client 417, server 402) + Playwright (33 specs). "
        "TSC baseline: server 14 pre-existing errors, client 0. Previous iterate "
        "campaigns: 14.0-14.14 all landed on main, 4 user-visible bugs remain. "
        "A timeboxed PoC branch exists proving the integration path is viable."
    )

    result = run_review(
        content=plan_text,
        context=context,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=180,
    )

    # Write review output next to the plan for later reference.
    out_path = plan_path.with_name(plan_path.stem + "-review.md")
    md_lines: list[str] = []
    md_lines.append(f"# External LLM Review — {plan_path.name}")
    md_lines.append("")
    md_lines.append(f"- Provider: `{result.get('provider')}`")
    md_lines.append(f"- Reviewer models: gemini-3.1-pro-preview, gpt-5.4 (via OpenRouter)")
    md_lines.append("")
    for name, review in result.get("reviews", {}).items():
        md_lines.append(f"## Reviewer: {name}")
        md_lines.append("")
        status = review.get("status", "unknown")
        md_lines.append(f"- Status: **{status}**")
        if status == "success":
            md_lines.append("")
            # lib.llm_review.run_review returns the body under `feedback`
            # (not `content`) for every successful provider branch.
            body = review.get("feedback") or review.get("content") or ""
            md_lines.append(body.strip() or "(empty response)")
        else:
            md_lines.append(f"- Reason: {review.get('reason', 'unknown')}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    out_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[review] wrote {out_path}", file=sys.stderr)

    # Also emit a compact JSON summary on stdout for programmatic consumption.
    print(json.dumps({
        "out_path": str(out_path),
        "provider": result.get("provider"),
        "reviewers": {
            name: {
                "status": r.get("status"),
                "chars": len(r.get("feedback") or r.get("content") or ""),
            }
            for name, r in result.get("reviews", {}).items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
