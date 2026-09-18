"""CLI entry point for the Codex-CLI internal-review transport.

The AC1 dispatch target: a driving harness that cannot spawn an independent
Agent-tool subagent (Codex CLI itself, or a Claude Code session redirected to
a non-Anthropic backend) runs this instead of `Task(...)` for one review
role. Wraps `lib.codex_review_transport.run_codex_review` — reads the
reviewer agent's `.md` file plus its review subject (`--spec-file` always;
`--diff-file` for spec/code/doubt, `--plan-file` for plan_review — the same
two file paths an Agent-tool spawn of that role receives), builds the
transport prompt (frontmatter stripped, subject + addendum + injection
boundary appended), runs `codex exec`, and prints the result as one JSON
line on stdout. Every failure mode, including an unreadable input file,
prints `{"status": "error", ...}` rather than a traceback.

On `status: "completed"`, `canonical_path` is the already schema-validated
payload file. For `--role spec|code|doubt`, pass it straight to
`record_review_pass.py record --from <role>-reviewer --payload-file
<canonical_path> --transport codex` (no `--model-tier` — the row carries no
legal Claude tier). For `--role plan_review`, there is no `--from` adapter
(`plan_internal` is a metadata-only row) — read `canonical_path` directly and
write its `findings`/`summary` into `plan.md`'s own `## Internal Plan
Review` section instead. On `status: "error"`, `reason` names the concrete
failure — either fall back to an ordinary Agent-tool spawn (then record
`--transport agent --transport-note "<reason>"`) or, when no fallback
exists, record `--status not_run --disposition "<reason>"`. See
`codex_review_transport.py`'s own docstring for the full design and its
Internal Plan Review findings, and `shared/prompts/codex_review_dispatch.md`
for the complete runnable procedure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.codex_review_transport import ROLE_SCHEMAS, build_prompt, run_codex_review  # noqa: E402


def _emit_error(reason: str) -> int:
    print(json.dumps({"status": "error", "transport": "codex", "reason": reason}))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--role", required=True, choices=sorted(ROLE_SCHEMAS))
    parser.add_argument("--worktree-root", required=True, help="passed to `codex exec --cd`")
    parser.add_argument("--agent-md", required=True,
                        help="path to the reviewer agent's .md file (frontmatter stripped here)")
    parser.add_argument("--out-dir", required=True,
                        help="the run's own evidence directory, e.g. "
                             ".shipwright/planning/iterate/<run_id>/")
    # The review subject: every agent .md this transport can drive (spec/code/
    # doubt-reviewer, opus-plan-reviewer) documents receiving two file paths —
    # without these the child has no idea what it is reviewing (code-reviewer
    # REJECT, 2026-09-17).
    parser.add_argument("--spec-file", required=True,
                        help="the spec/section-plan file path (all four roles take this)")
    parser.add_argument("--diff-file", default=None,
                        help="required for --role spec|code|doubt: the diff being reviewed")
    parser.add_argument("--plan-file", default=None,
                        help="required for --role plan_review: the plan being reviewed")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    args = parser.parse_args(argv)

    if args.role == "plan_review":
        if not args.plan_file:
            return _emit_error("--plan-file is required for --role plan_review")
        context_paths = {"Plan file": args.plan_file, "Spec file": args.spec_file}
    else:
        if not args.diff_file:
            return _emit_error(f"--diff-file is required for --role {args.role}")
        context_paths = {"Spec file": args.spec_file, "Diff file": args.diff_file}

    try:
        agent_markdown = Path(args.agent_md).read_text(encoding="utf-8")
        context_sections = {
            f"{label} ({path})": Path(path).read_text(encoding="utf-8")
            for label, path in context_paths.items()
        }
    except OSError as exc:
        return _emit_error(f"could not read an input file: {exc}")
    # An empty subject (e.g. `git diff HEAD` on an all-new-file change, per
    # this repo's own recorded gotcha) is not an OSError, so it would
    # otherwise reach codex as a review of nothing — schema-valid, exit 0,
    # promoted as a real PASS over no subject (doubt-reviewer, HIGH, 2026-09-17).
    for label, content in context_sections.items():
        if not content.strip():
            return _emit_error(f"{label} is empty — nothing to review")

    prompt = build_prompt(agent_markdown, context_sections)
    kwargs: dict[str, float | int] = {}
    # Clamped the same way as `codex_settings()` — an unclamped `--timeout 0`
    # fires TimeoutExpired instantly, and `--max-retries -1` makes `range()`
    # empty, returning the misleading "no attempt made" placeholder instead
    # of a usage error (code-reviewer, low finding, 2026-09-17).
    if args.timeout is not None and args.timeout > 0:
        kwargs["timeout"] = args.timeout
    if args.max_retries is not None:
        kwargs["max_retries"] = max(0, args.max_retries)

    result = run_codex_review(
        args.role, Path(args.worktree_root), prompt, Path(args.out_dir), **kwargs)
    print(json.dumps(result))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
