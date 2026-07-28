"""Pure helpers for the Tier-3 PR reviewer (no network / no subprocess).

Split out of `scripts/tools/pr_review.py` so the I/O-free review logic stays
small and unit-testable, and the tool script stays under the source-size
guideline. This module is now the pure-logic core only — redaction, prompt
loading, the template fill, diff truncation, response parsing and the
decision → exit-code mapping. Diff filtering (`pr_review_diff_filter`),
rendering (`pr_review_render`) and the `gh` boundary (`pr_review_gh`) live in
their own modules and are re-exported here for existing callers. See B4.5 in
`Spec/early-access-readiness-plan.md`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Generated-artifact diff filtering lives in its own cohesive module; re-exported
# here so `pr_review_lib.filter_generated_paths` / `.is_generated_path` keep
# working for callers and tests. See pr_review_diff_filter for the rationale.
from pr_review_diff_filter import (  # noqa: F401
    MAX_DIFF_CHARS,
    ReviewedDiff,
    filter_generated_paths,
    is_generated_path,
    truncate_diff_at_boundary,
)
# Rendering (comment + model meta + the path sanitiser) lives in its own
# module; re-exported so existing call sites keep working.
from pr_review_render import (  # noqa: F401
    build_pr_meta,
    nothing_reviewed_summary,
    render_comment,
    safe_path,
)


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


def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> ReviewedDiff:
    """Cut an over-cap diff at a file boundary. See ``ReviewedDiff``.

    Returns a record, not a tuple: read ``.incomplete`` for the gate and
    ``.omitted`` / ``.partial`` for the message.
    """
    return truncate_diff_at_boundary(diff, max_chars)


_PLACEHOLDERS = ("{PR_META}", "{DIFF}")
_PLACEHOLDER_RE = re.compile("|".join(re.escape(p) for p in _PLACEHOLDERS))


def build_messages(system_prompt: str, user_prompt: str, diff: str, pr_meta: str) -> list[dict]:
    """Fill the user-prompt template (`{PR_META}`, `{DIFF}`) and build chat messages.

    ONE pass. Chained `.replace()` calls re-scan what the earlier one inserted,
    and `{PR_META}` is filled first — so a file literally named ``{DIFF}`` (a
    legal path; the sanitiser strips control characters, not braces) put its own
    name into the metadata block and the second replace expanded the whole diff
    there, **above the fence and outside the block the system prompt marks as
    untrusted**. A single substitution never reconsiders inserted text.

    Raises if a placeholder is missing: a silent no-op here would send the model
    a prompt with no diff, or with no statement of what it is not being shown,
    and every test would stay green.
    """
    missing = [p for p in _PLACEHOLDERS if p not in user_prompt]
    if missing:
        raise ValueError(f"user prompt template is missing {', '.join(missing)}")
    values = {"{PR_META}": pr_meta, "{DIFF}": diff}
    filled = _PLACEHOLDER_RE.sub(lambda m: values[m.group(0)], user_prompt)
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
