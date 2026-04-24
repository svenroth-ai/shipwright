"""Pitfall #6 regression guard — `server.hmr.port` must not be pinned.

docs/guide.md §8.5 Pitfall #6:

> Hot-module-reload (HMR). Vite's HMR uses the same port as the dev
> server by default; two instances with different `VITE_PORT` values
> each get their own HMR port automatically. Do **not** pin
> `server.hmr.port` explicitly — that would force both instances onto
> one HMR port and create the exact collision this chapter aims to
> avoid.

This test reads `webui/client/vite.config.ts` as text and forbids a
literal-pinned `server.hmr.port` (numeric literal). Env-driven pins
such as `hmr: { port: parseInt(process.env.VITE_HMR_PORT || '0', 10) }`
are allowed — the hazard is specifically the hardcoded integer.

Known blind spot: a named-constant indirection like
``const HMR_PORT = 24678; ... hmr: { port: HMR_PORT }`` would pass this
regex. This is a tripwire, not a proof; a full TS AST parse is overkill
for one invariant. If that pattern appears, fail it explicitly in a
follow-up iterate.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VITE_CONFIG = ROOT / "webui" / "client" / "vite.config.ts"


def test_vite_config_exists() -> None:
    assert VITE_CONFIG.is_file(), f"vite.config.ts not found at {VITE_CONFIG}"


def test_no_literal_hmr_port_pin() -> None:
    """Forbid `hmr: { … port: <int-literal> … }` anywhere in the config."""
    text = VITE_CONFIG.read_text(encoding="utf-8")
    # Match `hmr` object literal followed by a port key bound to a bare
    # int. Tolerate whitespace, other keys, and trailing properties via
    # DOTALL on the `[^}]*` interior — the regex never crosses a `}`.
    pattern = re.compile(
        r"hmr\s*:\s*\{[^}]*\bport\s*:\s*\d+",
        flags=re.DOTALL,
    )
    match = pattern.search(text)
    assert match is None, (
        "Pitfall #6 violation: `server.hmr.port` is pinned to a literal "
        f"integer in {VITE_CONFIG.relative_to(ROOT)}.\n"
        f"Match: {match.group(0)!r}\n"
        "Remove the pin — each parallel Vite instance must pick its own "
        "HMR port. See docs/guide.md §8.5 Pitfall #6."
    )


def test_strictport_is_enabled() -> None:
    """Companion invariant — `strictPort: true` must stay set (docs/guide.md §8.5)."""
    text = VITE_CONFIG.read_text(encoding="utf-8")
    assert re.search(r"\bstrictPort\s*:\s*true\b", text), (
        "Pitfall #6 companion: `server.strictPort: true` is the contract "
        "that makes Vite fail loud on port collisions. Removing it would "
        "let Vite silently fall back to port+1 and break parallel worktrees."
    )


def test_vite_port_is_env_driven() -> None:
    """Companion invariant — VITE_PORT env must drive `server.port`."""
    text = VITE_CONFIG.read_text(encoding="utf-8")
    # Accept both `process.env.VITE_PORT` and `import.meta.env.VITE_PORT`
    # since a future migration may switch conventions.
    assert re.search(
        r"(process\.env\.VITE_PORT|import\.meta\.env\.VITE_PORT)",
        text,
    ), (
        "Pitfall #6 companion: `server.port` must read `VITE_PORT` from "
        "env so parallel worktrees can override it. A hardcoded number "
        "breaks the worktree-parallel workflow."
    )
