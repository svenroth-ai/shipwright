"""Layer-3 review runner: call shared/scripts/lib/llm_review.py on generated artifacts.

Without OPENROUTER_API_KEY (or any fallback key), this gracefully skips
with a documented reason. Writes `.shipwright/adopt/review.md`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _locate_llm_review() -> Path | None:
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        candidate = ancestor.parent / "shared" / "scripts" / "lib" / "llm_review.py"
        if candidate.exists():
            return candidate
    return None


def _has_any_api_key() -> bool:
    return bool(
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def run_review(
    project_root: Path,
    *,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Run llm_review on the generated CLAUDE.md + architecture + spec.

    Returns {"status": "completed"|"skipped", "reason": str,
             "review_path": str|None, "provider": str|None}
    """
    review_dir = project_root / ".shipwright" / "adopt"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_dir / "review.md"

    if not _has_any_api_key():
        review_path.write_text(
            "# Adopt Review — SKIPPED\n\n"
            "No `OPENROUTER_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` detected. "
            "Layer-3 external review was skipped.\n\n"
            "Set one of these env vars and re-run Adopt (or `/shipwright-iterate` "
            "and run review manually) to generate a post-generation sanity check.\n",
            encoding="utf-8",
        )
        return {
            "status": "skipped",
            "reason": "no_api_key",
            "review_path": str(review_path),
            "provider": None,
        }

    llm_review_path = _locate_llm_review()
    if llm_review_path is None:
        review_path.write_text(
            "# Adopt Review — SKIPPED\n\n"
            "Could not locate `shared/scripts/lib/llm_review.py`. "
            "Skipped review; run manually after resolving.\n",
            encoding="utf-8",
        )
        return {
            "status": "skipped",
            "reason": "llm_review_not_found",
            "review_path": str(review_path),
            "provider": None,
        }

    # Import llm_review dynamically
    sys.path.insert(0, str(llm_review_path.parent))
    try:
        import llm_review  # type: ignore
    except ImportError as e:
        review_path.write_text(
            f"# Adopt Review — SKIPPED\n\nImport error: {e}\n",
            encoding="utf-8",
        )
        return {
            "status": "skipped",
            "reason": f"import_error: {e}",
            "review_path": str(review_path),
            "provider": None,
        }

    # Build review content: concat of generated docs
    parts: list[str] = []
    for rel in ("CLAUDE.md", ".shipwright/agent_docs/architecture.md", ".shipwright/agent_docs/conventions.md"):
        p = project_root / rel
        if p.exists():
            parts.append(f"## {rel}\n\n{p.read_text(encoding='utf-8')}\n")
    # Add first split spec
    planning = project_root / ".shipwright" / "planning"
    if planning.is_dir():
        for spec in planning.rglob("spec.md"):
            parts.append(f"## {spec.relative_to(project_root).as_posix()}\n\n{spec.read_text(encoding='utf-8')}\n")
            break
    content = "\n\n---\n\n".join(parts)

    context = (
        f"Shipwright adopted this repo. Profile: {snapshot.get('profile', {}).get('matched', '?')}. "
        f"Features inferred: {len(snapshot.get('features', []))}. "
        f"Primary language: {snapshot.get('stack', {}).get('primary_language', '?')}. "
        "Please flag: (1) FR descriptions that don't match route files, "
        "(2) contradictions between CLAUDE.md and the README, "
        "(3) ADR backfill entries that seem implausible given their commit subjects, "
        "(4) architecture_prose that disagrees with the folder structure."
    )

    try:
        result = llm_review.run_review(content, context)
    except Exception as e:  # pragma: no cover
        review_path.write_text(
            f"# Adopt Review — ERROR\n\nllm_review raised: {e!r}\n",
            encoding="utf-8",
        )
        return {
            "status": "skipped",
            "reason": f"llm_review_error: {e!r}",
            "review_path": str(review_path),
            "provider": None,
        }

    provider = result.get("provider", "unknown")
    reviews = result.get("reviews", {})
    body = f"# Adopt Review — {provider}\n\n"
    for name, rev in reviews.items():
        status = rev.get("status", "unknown")
        feedback = rev.get("feedback", "_no feedback_")
        body += f"## {name} — {status}\n\n{feedback}\n\n---\n\n"
    review_path.write_text(body, encoding="utf-8")

    return {
        "status": "completed" if result.get("success") else "skipped",
        "reason": "" if result.get("success") else "llm_returned_unsuccess",
        "review_path": str(review_path),
        "provider": provider,
    }
