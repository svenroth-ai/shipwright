#!/usr/bin/env python3
"""Checks a Brief package gets AT INTAKE, before the run starts (campaign e2e-run-findings, E4; finding F6).

* :func:`check_content` -- the Project phase's content check, run early. It is NOT a second
  implementation: it runs ``tools/brief_project_mode.py check`` (the same ``check_capabilities``
  that ``apply`` uses) in its own interpreter, because this module is loaded as a privately named
  package (ADR-045) and the tool binds the ``lib`` / ``tools`` namespaces. Issues refuse the intake.
* :func:`token_warnings` -- ADVISORY: does the package's ``visual-guidelines.md`` carry the kit's
  colour and size tokens (``--color-bg: #f6f7f9``), and do the declared pairs meet the contrast rules of
  the kit's ``tokens-contract.md``? The rules are the design plugin's ``check_brand_tokens.py``
  (CONTRAST_PAIRS, contrast, nearest_passing), loaded from where that plugin sits next to ``shared``;
  when it cannot be found the check says so and is skipped. A warning never blocks.

Stdlib only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "brief_project_mode.py"
_KIT_REL = ("scripts", "tools", "check_brand_tokens.py")
_DECL_RE = re.compile(r"(--(?:color|font-size)-[\w-]+)\s*:\s*([^\s;`|,]+)")
_TIMEOUT_SECONDS = 60


def check_content(project_root: Path, brief_dir: str) -> list[dict]:
    """Content issues of ``<brief_dir>/brief.md`` (empty = fine); raises ``RuntimeError`` when the check could not run."""
    try:
        proc = subprocess.run(
            [sys.executable, str(_TOOL), "check", "--project-root", str(project_root), "--brief-dir", brief_dir],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1"}, timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"the brief content check did not run: no answer within {_TIMEOUT_SECONDS}s") from None
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = None
    if not isinstance(out, dict) or not isinstance(out.get("issues", []), list) or "ok" not in out:
        detail = (proc.stderr or proc.stdout or "no output").strip()[-300:]
        raise RuntimeError(f"the brief content check did not run (exit {proc.returncode}): {detail}")
    return out["issues"]


def _kit_checker(root: Path | None = None) -> Any:
    """The design plugin's ``check_brand_tokens`` module, or None when no copy sits next to ``shared``."""
    base = root or Path(__file__).resolve().parents[3]  # repo root (plugins/ + shared/) or the cache root
    versioned = sorted((base / "shipwright-design").glob("*/" + "/".join(_KIT_REL)),
                       key=lambda p: [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", p.parts[-4])])
    for path in [*reversed(versioned), base / "plugins" / "shipwright-design" / Path(*_KIT_REL)]:  # installed version first: the cache's plugins/ mirror can be stale
        if path.is_file():
            spec = importlib.util.spec_from_file_location("_shipwright_kit_check_brand_tokens", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            try:
                spec.loader.exec_module(mod)
            except BaseException:
                sys.modules.pop(spec.name, None)
                raise
            return mod
    return None


def token_warnings(guidelines: Path, kit: Any = None) -> list[str]:
    """Advisory, fail-open: any trouble loading or running the kit checker becomes one warning, never an exception."""
    try:
        return _token_warnings(guidelines, kit or _kit_checker())
    except Exception as exc:  # noqa: BLE001 -- an advisory check must never stop an intake
        return [f"kit token check could not run: {type(exc).__name__}: {exc}"]


def _token_warnings(guidelines: Path, kit: Any) -> list[str]:
    """Warnings for the package's visual guidelines (empty = a full, readable, contrast-clean token set).

    The kit's own ``check()`` judges the contract (one rule set, none restated here). A package
    declares only some tokens, so the rest are taken from the shipped ``warm`` set first: every
    failure then involves a declared token, because the shipped set passes on its own."""
    if kit is None:
        return ["kit token check skipped: the shipwright-design plugin (check_brand_tokens.py) was not found next to shared"]
    try:
        text = guidelines.read_text(encoding="utf-8-sig") if guidelines.is_file() else ""
    except (OSError, ValueError) as exc:
        return [f"{guidelines.name} could not be read for the kit token check: {exc}"]
    css = "\n".join(f"{name}: {value.rstrip('.*')};" for name, value in _DECL_RE.findall(text))
    colours, sizes = kit.parse_colours(css), kit.parse_sizes(css)
    wanted = sorted({n for p in kit.CONTRAST_PAIRS for n in p[:2]} | set(kit.OTHER_COLOURS))
    out = [f"{guidelines.name}: {w}" for w in kit.unreadable_values(css)]
    missing = [n for n in wanted if n not in colours]
    if missing:
        out.append(f"{guidelines.name} declares {len(wanted) - len(missing)} of the {len(wanted)} kit colour tokens; "
                   f"missing: {', '.join('--color-' + n for n in missing)}. Write them as '--color-bg: #f6f7f9' lines "
                   "(tokens-contract.md in the design kit); Design fills a missing one from a shipped set")
    base = (kit.KIT / "tokens" / "warm.css").read_text(encoding="utf-8")
    judged = kit.check({**kit.parse_colours(base), **colours}, {**kit.parse_sizes(base), **sizes})
    out += [f"{guidelines.name}: {line} (tokens not declared are taken from the 'warm' set)" for line in judged]
    return out
