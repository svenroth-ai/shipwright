"""Shared pure helpers for adopt's agent-doc renderers.

Extracted from ``artifact_writer.py`` (which sits at its bloat baseline) so
the renderer modules can share ``_utc_today`` / ``_fmt_stack_line`` without
either file growing past its ceiling. Neutral leaf module — imports nothing
local, so it introduces no ``lib.*`` import cycle.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Layer names mirror shared/scripts/lib/requirement_model.LAYERS — kept as literals
# here so this stays a neutral leaf module (no cross-package import / cycle). The
# adopt test cross-checks every emitted layer against the shared vocab (R5).
_LAYER_UNIT = "unit"
_LAYER_INTEGRATION = "integration"
_LAYER_E2E = "e2e"

# Surface → layer signals for reverse-engineered FRs (Spec D2 / adopt inference,
# AC2). A UI surface (page/view/screen/component) needs an e2e; a persistence
# surface (migration/schema/table/RLS policy) needs an integration test; every FR
# needs a unit test. Matched on the FR's detected source_file, case-insensitively.
#
# The e2e signal must be UI-SPECIFIC — `bool(route) or bool(framework)` over-fired,
# because feature_inferrer sets route+framework on EVERY feature incl. backend
# (express/fastapi/flask), so a pure-API FR wrongly inferred e2e. So e2e requires
# EITHER a UI framework token OR a UI-file source; a bare API route stays unit
# (or integration if it is a data route). Deliberately drops bare `app/`+`routes/`
# (backend FastAPI `app/`, Express `routes/`) — Next App-Router / SvelteKit / Remix
# are caught by the framework token instead.
_E2E_SOURCE_RE = re.compile(
    r"(?:^|/)(?:pages?|views?|screens?|components?)/"
    r"|(?:^|/)page\.(?:tsx?|jsx?|svelte|vue)$|\.page\.|\.(?:svelte|vue)$",
    re.IGNORECASE,
)
# Substring-matched against the detected `framework` value (feature_inferrer emits
# e.g. `next-app-router` / `next-pages-router` for UI; `express` / `fastapi` /
# `flask` for backend, which must NOT infer e2e).
_UI_FRAMEWORK_TOKENS = (
    "next", "react", "vue", "svelte", "nuxt", "remix", "astro", "gatsby",
    "angular", "solid", "preact", "qwik", "sveltekit",
)
# A KNOWN backend framework suppresses the e2e signal entirely — even a UI-looking
# source segment (e.g. Flask's `app/views/` handlers, which are NOT UI views) must
# not infer e2e for a pure-API feature.
_BACKEND_FRAMEWORK_TOKENS = (
    "fastapi", "flask", "express", "django", "hono", "fastify", "koa",
    "nest", "gin", "rails", "sinatra", "laravel", "spring",
)
_INTEGRATION_SOURCE_RE = re.compile(
    r"(?:^|/)(?:migrations?|schema|schemas|db|database|models?|tables?|repositor(?:y|ies)"
    r"|policies|prisma|alembic)(?:/|\b)|\.sql$|_rls\b|\brls\b|_policy\b",
    re.IGNORECASE,
)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fmt_stack_line(stack_group: dict[str, str]) -> str:
    if not stack_group:
        return "—"
    return ", ".join(sorted(stack_group.keys()))


def infer_required_layers(feature: dict[str, Any]) -> tuple[str, ...]:
    """Infer the ``required_layers`` set for a reverse-engineered adopt FR (AC2).

    ``unit`` is always required. A UI surface (a UI framework token like next/react/
    vue/svelte, OR a page/view/screen/component source file) adds ``e2e`` — a bare
    backend API route (fastapi/flask/express) does NOT; a migration / schema / table
    / RLS-policy surface adds ``integration``. The
    returned tuple is ordered ``unit`` → ``integration`` → ``e2e`` so the rendered
    ``Layers`` column is deterministic. Unknown surfaces default to ``unit`` only —
    deliberately conservative so an adopted repo is not instantly drowned in
    "MISSING e2e" findings (Spec §9 landmine).
    """
    signals = " ".join(str(feature.get(k, "")) for k in ("source_file", "route", "url"))
    framework = str(feature.get("framework") or "").lower()
    layers = [_LAYER_UNIT]
    # e2e ONLY on a UI-specific signal — a UI framework token OR a UI-file source —
    # and NEVER when the framework is a known backend one (a bare backend route in
    # fastapi/flask/express is not a UI surface, even under a `views/`-looking path).
    is_backend_fw = any(tok in framework for tok in _BACKEND_FRAMEWORK_TOKENS)
    is_ui = any(tok in framework for tok in _UI_FRAMEWORK_TOKENS) \
        or (not is_backend_fw and bool(_E2E_SOURCE_RE.search(signals)))
    if _INTEGRATION_SOURCE_RE.search(signals):
        layers.append(_LAYER_INTEGRATION)
    if is_ui:
        layers.append(_LAYER_E2E)
    return tuple(layers)
