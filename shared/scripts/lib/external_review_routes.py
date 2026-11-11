"""An ordered route list for one reviewer leg that falls through on failure (issue #1034).

``external_review.gpt_leg.provider`` picks ONE transport and only falls back to the API chain
when the Codex CLI is unavailable *before* the call. If ``codex exec`` then fails at runtime
(quota, timeout, launch failure) the leg ends in ``error`` although an API key would have answered.

``external_review.gpt_leg.routes`` is the opt-in alternative: an ordered list such as
``["codex", "openrouter", "direct"]``. The leg tries the routes in order and moves on both when a
route is unavailable (not installed, no key) and when it fails while running. Every route that was
skipped or failed is recorded in the leg's ``attempts`` list, so a metered fallback after a
flat-cost route failed stays visible. Without ``routes`` nothing changes.
"""

from __future__ import annotations

from typing import Any, Callable

try:  # bare: shared/scripts/lib is on sys.path (tools/external_review.py)
    from external_review_default_legs import is_codex_available
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_default_legs":
        raise
    from lib.external_review_default_legs import is_codex_available  # type: ignore[no-redef]

__all__ = ["GPT_ROUTES", "gpt_leg_routes", "route_available", "run_route_chain"]

#: The routes that can answer the 'openai' reviewer identity.
GPT_ROUTES: tuple[str, ...] = ("codex", "openrouter", "direct")
_KNOWN_STATUSES = ("success", "error", "degraded", "skipped")


def gpt_leg_routes(config: dict[str, Any]) -> list[str] | None:
    """The configured ordered route list, or ``None`` when the project did not set one.

    Degrades instead of crashing on a malformed override: unknown names and repeats are dropped,
    and a list with nothing valid left means "not configured" (the ``provider`` setting then
    decides, exactly as before)."""
    section = config.get("external_review")
    leg = section.get("gpt_leg") if isinstance(section, dict) else None
    raw = leg.get("routes") if isinstance(leg, dict) else None
    if not isinstance(raw, list):
        return None
    routes: list[str] = []
    for name in raw:
        if isinstance(name, str) and name in GPT_ROUTES and name not in routes:
            routes.append(name)
    return routes or None


def route_available(route: str, *, has_openrouter: bool, has_openai: bool) -> tuple[bool, str]:
    """Whether ``route`` can be attempted at all, with the reason when it cannot."""
    if route == "codex":
        return is_codex_available()
    if route == "openrouter":
        return (True, "") if has_openrouter else (False, "No OPENROUTER_API_KEY set")
    return (True, "") if has_openai else (False, "No OPENAI_API_KEY set")


def _attempt(route: str, outcome: str, reason: str | None) -> dict[str, str]:
    return {"route": route, "outcome": outcome, **({"reason": str(reason)[:300]} if reason else {})}


def run_route_chain(
    routes: list[str], runners: dict[str, Callable[[], dict]], *, has_openrouter: bool, has_openai: bool,
) -> dict:
    """Try ``routes`` in order; the first success wins. Returns the winning (or last) leg result,
    always carrying ``attempts``. Nothing usable at all is ``skipped``, like a leg with no key."""
    attempts: list[dict[str, str]] = []
    last: dict | None = None
    for route in routes:
        available, why = route_available(route, has_openrouter=has_openrouter, has_openai=has_openai)
        if not available:
            attempts.append(_attempt(route, "skipped", why))
            continue
        try:
            result = runners[route]()
        except Exception as exc:  # noqa: BLE001 - a route that blows up must not end the chain
            result = {"status": "error", "via": route, "reason": str(exc)}
        outcome = str(result.get("status") or "error")
        if outcome not in _KNOWN_STATUSES:  # an unknown status is a failure, never a silent pass-through
            outcome, result = "error", {**result, "status": "error"}
        attempts.append(_attempt(route, outcome, None if outcome == "success" else result.get("reason")))
        if outcome == "success":
            failed = [a for a in attempts if a["outcome"] != "success"]
            if failed:  # the answer came from a later route: say what was skipped or failed first
                result["fallback_reason"] = "; ".join(
                    f"{a['route']} {a['outcome']}" + (f" ({a['reason']})" if a.get("reason") else "") for a in failed
                )
            return {**result, "attempts": attempts}
        if outcome != "skipped":  # a runtime-skipped route never hides an earlier real failure
            last = result
    if last is None:
        why = "; ".join(f"{a['route']}: {a.get('reason', a['outcome'])}" for a in attempts)
        return {"status": "skipped", "reason": f"no configured route is available ({why})", "attempts": attempts}
    return {**last, "attempts": attempts}
