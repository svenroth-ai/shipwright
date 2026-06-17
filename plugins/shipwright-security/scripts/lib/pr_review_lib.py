"""Pure helpers for the Tier-3 PR reviewer (no network / no subprocess).

Split out of `scripts/tools/pr_review.py` so the I/O-free review logic
(redaction, prompt loading, diff truncation, response parsing, decision →
exit-code mapping, comment rendering) stays small and unit-testable, and the
tool script stays under the source-size guideline. See B4.5 in
`Spec/early-access-readiness-plan.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

# A diff larger than this is reviewed on a truncated copy. A truncated (partial)
# review FAILS CLOSED (we never saw the whole change): for a required gate on an
# untrusted PR the reviewer forces a request-changes state + non-zero exit (needs
# human) so a large diff cannot bypass review by size. See B4.5 error-behavior +
# iterate-2026-06-17-pr-review-truncation-failclosed (was: comment-state + exit 0).
MAX_DIFF_CHARS = 200_000

EXIT_OK = 0
EXIT_BLOCK = 1
EXIT_ERROR = 2


def _redact(text: str, *secrets: str) -> str:
    """Mask each secret value in ``text``. Safe with None/empty secrets.

    Applied to every string that reaches stdout/stderr (raw response dumps,
    error messages) so the OpenRouter key can never leak into CI logs.
    """
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***REDACTED***")
    return out


def load_prompts(prompt_dir: str) -> tuple[str, str]:
    """Read the `system` and `user` prompt files from a prompt directory.

    Mirrors the `code_reviewer/{system,user}` / `iterate_reviewer/{system,user}`
    directory form (PR #119). Both files are extension-less.
    """
    base = Path(prompt_dir)
    system = (base / "system").read_text(encoding="utf-8")
    user = (base / "user").read_text(encoding="utf-8")
    return system, user


def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> tuple[str, bool]:
    """Return (diff, truncated). Truncates to ``max_chars`` when over the cap."""
    if len(diff) <= max_chars:
        return diff, False
    return diff[:max_chars], True


def build_messages(system_prompt: str, user_prompt: str, diff: str, pr_meta: str) -> list[dict]:
    """Fill the user-prompt template (`{PR_META}`, `{DIFF}`) and build chat messages."""
    filled = user_prompt.replace("{PR_META}", pr_meta).replace("{DIFF}", diff)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": filled},
    ]


def _strip_code_fence(raw: str) -> str:
    """Drop a leading ```json / ``` fence line and the trailing ``` if present.

    Even with `response_format: json_object`, OpenRouter -> Anthropic does not
    strictly enforce raw-JSON output, so the model frequently wraps the object
    in a markdown code fence. Verified live on a B4.5 Tier-3 smoke-test PR.
    """
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    nl = text.find("\n")
    if nl != -1:
        text = text[nl + 1:]  # drop the opening ``` / ```json line
    fence = text.rfind("```")
    if fence != -1:
        text = text[:fence]   # drop the closing ``` fence
    return text.strip()


def parse_review_response(raw: str) -> dict:
    """Parse the strict-JSON review object, tolerating a ```json fence or
    surrounding prose around the object. Raises ValueError on any deviation.

    Tries, in order: the raw text, the fence-stripped text, and the outermost
    ``{ ... }`` slice (handles leading/trailing prose).
    """
    stripped = _strip_code_fence(raw)
    candidates = [raw or "", stripped]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start:end + 1])

    data = None
    last_err: Exception = ValueError("empty response")
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except (json.JSONDecodeError, TypeError) as e:
            last_err = e
            continue
        if isinstance(parsed, dict):
            data = parsed
            break
        last_err = ValueError("response JSON is not an object")
    if data is None:
        raise ValueError(f"response is not valid JSON: {last_err}")
    if "decision" not in data:
        raise ValueError("response JSON missing required 'decision' field")
    return data


def decision_to_exit(decision: str) -> int:
    """approve|comment -> 0, block -> 1, anything else -> 2 (treated as an error)."""
    # str() guard: a model may return a non-string `decision` (e.g. a list);
    # coerce so an odd-but-valid-JSON response maps to exit 2, never AttributeError.
    norm = str(decision or "").strip().lower()
    if norm in ("approve", "comment"):
        return EXIT_OK
    if norm == "block":
        return EXIT_BLOCK
    return EXIT_ERROR


def render_comment(review: dict, *, model: str, truncated: bool) -> str:
    """Render the PR comment Markdown from a parsed review object."""
    decision = str(review.get("decision") or "unknown").strip().lower()
    badge = {"approve": "✅ APPROVE", "comment": "💬 COMMENT", "block": "🔴 BLOCK"}.get(
        decision, f"⚠️ {decision.upper()}"
    )
    lines = [
        "## 🤖 Shipwright PR Review",
        "",
        f"**Decision: {badge}**",
        "",
        str(review.get("summary") or "_No summary provided._"),
        "",
    ]
    if truncated:
        lines += [
            f"> ⚠️ **Diff truncated** at {MAX_DIFF_CHARS:,} characters — this review is "
            "**partial**, so the check **fails closed**: a human must review this PR "
            "before merge (a maintainer can apply the `skip-pr-review` label after a "
            "manual look).",
            "",
        ]
    blocking = [b for b in (review.get("blocking") or []) if str(b).strip()]
    if blocking:
        lines.append("### 🚫 Blocking issues")
        lines += [f"- {b}" for b in blocking]
        lines.append("")
    comments = [c for c in (review.get("comments") or []) if str(c).strip()]
    if comments:
        lines.append("### Comments")
        lines += [f"- {c}" for c in comments]
        lines.append("")
    lines += [
        "---",
        f"_Automated Tier-3 review by `{model}` via OpenRouter "
        "(external / sensitive-path PR). Tier 1/2 PRs are reviewed locally at "
        "`/shipwright-iterate` Step 8 — see B4.5._",
    ]
    return "\n".join(lines)
