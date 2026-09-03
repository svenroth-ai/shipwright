"""The three locked-down review legs: OpenRouter, direct OpenAI, Codex CLI.

Split out of ``llm_review.py`` (keeping it under the 300-line guideline) alongside the sibling
``external_review_gateway.py`` split. All three legs here are identity-locked —
``resolve_reviewer_model``/``openrouter_extra_body`` enforce the fixed GLM/OpenAI bindings and the
GLM ZDR allowlist — in deliberate contrast to the gateway leg, which carries neither.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:  # bare: this directory is on sys.path
    from external_review_degraded import MAX_OUTPUT_TOKENS, classify_reply, openai_finish_reason
    from external_review_config import gpt_leg_provider
    from external_review_routing import ReviewModelPolicyError, openrouter_extra_body, resolve_reviewer_model
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_degraded":
        raise
    from lib.external_review_degraded import (  # type: ignore[no-redef]
        MAX_OUTPUT_TOKENS,
        classify_reply,
        openai_finish_reason,
    )
    from lib.external_review_config import gpt_leg_provider  # type: ignore[no-redef]
    from lib.external_review_routing import (  # type: ignore[no-redef]
        ReviewModelPolicyError,
        openrouter_extra_body,
        resolve_reviewer_model,
    )

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CODEX_DEFAULT_TIMEOUT_SECONDS = 600
CODEX_DEFAULT_MAX_RETRIES = 1
_CODEX_LOGIN_STATUS_TIMEOUT_SECONDS = 15


def review_openrouter(
    content: str, context: str, system_prompt: str, user_prompt: str,
    config: dict, model_key: str, timeout: int,
) -> dict:
    """Send content for review via OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"}

    try:
        from openai import OpenAI

        model_name = resolve_reviewer_model(config, model_key, "openrouter")
        extra_body = openrouter_extra_body(model_key, config)

        client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=timeout)
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_OUTPUT_TOKENS,
            extra_body=extra_body,
        )
        return classify_reply(response.choices[0].message.content, openai_finish_reason(response), via="openrouter")

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def review_openai(
    content: str, context: str, system_prompt: str, user_prompt: str,
    config: dict, timeout: int,
) -> dict:
    """Send content for review to OpenAI (direct API)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENAI_API_KEY set"}

    try:
        from openai import OpenAI

        model_name = resolve_reviewer_model(config, "openai", "direct")
        client = OpenAI(api_key=api_key, timeout=timeout)
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            # gpt-5.x rejects `max_tokens` on the direct Chat Completions API;
            # `max_completion_tokens` is the supported replacement.
            max_completion_tokens=MAX_OUTPUT_TOKENS,
        )
        return classify_reply(response.choices[0].message.content, openai_finish_reason(response), via="direct")

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _resolve_codex_binary() -> str | None:
    """``shutil.which("codex")``, but reject a hit that only resolved because Windows implicitly
    searches the current working directory before PATH (the BatBadBut class) — a reviewed repo could
    otherwise plant its own ``codex.exe``/``codex.cmd``/``codex.bat`` at its root and have it run
    instead of the real CLI, since this process's cwd is typically the project under review."""
    found = shutil.which("codex")
    if found is None:
        return None
    try:
        # RuntimeError alongside OSError: Path.resolve() raises RuntimeError on a symlink loop,
        # not OSError — this function's "never raises" contract (is_codex_available's docstring)
        # covers both, since a raise here would otherwise propagate uncaught through the review gate.
        if Path(found).resolve().parent == Path.cwd().resolve():
            return None
    except (OSError, RuntimeError):
        return None
    return found


def is_codex_available() -> tuple[bool, str]:
    """Whether the Codex CLI is installed and authenticated for this operator. Never raises —
    every failure mode returns a stated reason so the caller degrades to a graceful fallback/skip
    instead of crashing. Bounded by its own short timeout: an unauthenticated ``codex`` can
    otherwise block on an interactive login prompt rather than exiting with a distinguishable code,
    which would hang the whole review pass."""
    codex_bin = _resolve_codex_binary()
    if not codex_bin:
        return False, "codex CLI not found on PATH"
    try:
        # --ignore-user-config/--ignore-rules mirror the real `codex exec` call below — the probe checks auth
        # under the same config isolation the real leg runs with, so a config-dependent auth path can't pass
        # the probe and then fail (or vice versa) at exec time.
        result = subprocess.run(
            [codex_bin, "login", "status", "--ignore-user-config", "--ignore-rules"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=_CODEX_LOGIN_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "codex login status check timed out (may be waiting on interactive input)"
    except OSError as exc:
        return False, f"codex login status check failed: {exc}"
    if result.returncode != 0:
        return False, "codex CLI is not authenticated (run `codex login`)"
    return True, ""


def codex_settings(config: dict) -> tuple[float, int]:
    """`(timeout_seconds, max_retries)` from `config["codex"]`, defaulted and clamped the same way
    as ``llm_client_settings`` — see its docstring for why a hand-edited negative retry count must
    not reach `range()` raw. A non-positive/non-numeric timeout would otherwise reach
    `subprocess.run` as `None`/0 and block the worker thread forever (`None` means "no timeout" to
    `subprocess.run`, not "use the default")."""
    codex_cfg = config.get("codex")
    codex_cfg = codex_cfg if isinstance(codex_cfg, dict) else {}
    max_retries = codex_cfg.get("max_retries", CODEX_DEFAULT_MAX_RETRIES)
    timeout = codex_cfg.get("timeout_seconds", CODEX_DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(timeout)
        # isfinite: NaN/+-inf both satisfy `timeout <= 0` as False and would reach subprocess.run raw.
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except (TypeError, ValueError):
        timeout = CODEX_DEFAULT_TIMEOUT_SECONDS
    try:
        max_retries = max(0, int(max_retries))
    except (TypeError, ValueError):
        max_retries = CODEX_DEFAULT_MAX_RETRIES
    return timeout, max_retries


def review_codex(prompt: str, system_prompt: str, config: dict) -> dict:
    """Send an ALREADY-RENDERED user prompt for review via the Codex CLI — the flat-cost route
    for the 'openai' reviewer identity under a ChatGPT/Codex subscription.

    Deliberately takes a rendered ``prompt`` rather than a template plus content/context: the CLI
    (``external_review.py``) and library (``llm_review.py``) callers substitute a DIFFERENT
    placeholder set (``{SPEC}``/``{DIFF}``/``{PLAN}``/``{BRIEF}`` vs ``{CONTENT}``/``{CONTEXT}``)
    into their own templates, so only the caller knows which rule applies. Rendering here once
    caused a silent no-op: this function's own ``{CONTENT}``/``{CONTEXT}`` substitution never
    matched the CLI's template, and Codex reviewed the literal placeholder text as a passing review.

    Codex is agentic (free-form stdout, not a Chat Completions response), so this feeds it the exact
    same prompt text the API legs get and captures its FINAL message via ``-o`` rather than parsing
    streamed events; ``classify_reply`` then applies the identical empty/truncated check every leg
    uses — the shipped reviewer prompts already ask for prose ending in one ``SHIPWRIGHT_VERDICT``
    sentinel line, which is exactly what Codex's final message is.

    Run in a fresh, empty scratch directory per attempt (never the real project tree) with
    ``--sandbox read-only`` and both ``--ignore-user-config``/``--ignore-rules`` — this keeps it
    seeing only the prompt text the other two legs see, and strips the operator's own ``$CODEX_HOME``
    config (custom MCP servers, notify hooks, execpolicy rules) out of the run. ``--sandbox
    read-only`` blocks writes to the scratch dir it can see, NOT reads or outbound network — it is
    not a network sandbox, so a prompt-injected diff still runs against whatever network access the
    operator's own environment grants the ``codex`` process; this leg trusts the same content the
    other two legs already send an external LLM. Authentication is unaffected
    (``--ignore-user-config`` explicitly keeps using ``$CODEX_HOME`` for that).

    Retry scope matches ``retrying_completion``: ONLY a successfully-run codex exec that classifies
    as "degraded" (empty/truncated final message) is retried. A transport-level failure (launch
    error, timeout, nonzero exit) is terminal on the attempt it occurs — retrying a 600s timeout
    would otherwise double the worst-case wall clock for this leg. Worst case for this leg alone:
    ``(max_retries + 1) * timeout_seconds`` — default config is 2 * 600s = 1200s (20 min); callers
    invoking this synchronously must budget their own timeout above that.
    """
    # TOCTOU re-check for direct callers, not just resolve_openai_route — "error" not "skipped":
    # resolve_openai_route already committed to codex, so a failure here is attempted-and-failed,
    # not not-attempted; "skipped" would drop it from _attempted() and hide the loss.
    available, reason = is_codex_available()
    if not available:
        return {"status": "error", "via": "codex", "reason": reason}

    try:
        model_name = resolve_reviewer_model(config, "openai", "codex")
    except ReviewModelPolicyError as exc:
        return {"status": "error", "via": "codex", "reason": str(exc)}

    timeout, max_retries = codex_settings(config)
    full_prompt = f"{system_prompt}\n\n{prompt}"
    codex_bin = _resolve_codex_binary()
    if not codex_bin:
        return {"status": "error", "via": "codex", "reason": "codex CLI not found on PATH"}

    result: dict = {"status": "degraded", "reason": "no attempt made", "via": "codex"}
    for _attempt in range(max_retries + 1):
        with tempfile.TemporaryDirectory(
            prefix="shipwright-codex-review-", ignore_cleanup_errors=True
        ) as tmp:
            out_path = Path(tmp) / "review.txt"
            argv = [
                codex_bin, "exec", "-m", model_name, "--skip-git-repo-check", "--sandbox", "read-only",
                "--ephemeral", "--ignore-user-config", "--ignore-rules", "--cd", tmp, "-o", str(out_path),
            ]
            try:
                proc = subprocess.run(
                    argv, input=full_prompt, capture_output=True,
                    encoding="utf-8", errors="replace", timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return {"status": "error", "via": "codex", "reason": f"codex exec timed out after {timeout}s"}
            except OSError as exc:
                return {"status": "error", "via": "codex", "reason": f"failed to launch codex: {exc}"}

            if proc.returncode != 0:
                stderr_line = next((ln for ln in reversed((proc.stderr or "").splitlines()) if ln.strip()), "")
                return {"status": "error", "via": "codex", "reason": f"codex exec exited {proc.returncode}: {stderr_line[:500]}"}

            try:
                feedback = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
            except OSError as exc:
                return {"status": "error", "via": "codex", "reason": f"could not read codex output: {exc}"}
        result = classify_reply(feedback, None, via="codex")
        if result["status"] != "degraded":
            break
    return result


def api_route(has_openrouter_key: bool, has_openai_key: bool) -> str:
    """'openrouter' | 'direct' | 'none' from which env keys are set — the pre-existing GPT-leg
    routing rule, unchanged, now named so both the default 'api' path and the codex-unavailable
    fallback share it."""
    if has_openrouter_key:
        return "openrouter"
    if has_openai_key:
        return "direct"
    return "none"


def resolve_openai_route(
    config: dict, *, has_openrouter_key: bool, has_openai_key: bool,
) -> tuple[str, str]:
    """Which route answers the 'openai' reviewer leg, and why.

    Returns ``(route, note)`` where route is 'codex' | 'openrouter' | 'direct' | 'none'. When the
    project configures the codex route (``external_review.gpt_leg.provider == "codex"``) but codex
    is unavailable for this operator, this falls back to whichever API route the operator's keys
    support instead of a hard failure — ``note`` explains why, so an operator who chose codex
    specifically to avoid metered API cost sees clearly that the fallback (and its cost) happened
    and is not silently absorbed into a log line.
    """
    if gpt_leg_provider(config) == "codex":
        available, unavailable_reason = is_codex_available()
        if available:
            return "codex", ""
        fallback = api_route(has_openrouter_key, has_openai_key)
        return fallback, (
            f"codex unavailable ({unavailable_reason}); falling back to "
            f"{fallback if fallback != 'none' else 'no configured API key — skipping this leg'}"
        )
    return api_route(has_openrouter_key, has_openai_key), ""
