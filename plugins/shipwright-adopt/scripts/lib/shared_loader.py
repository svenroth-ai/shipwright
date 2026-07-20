"""Pollution-free loader for shipwright ``shared/`` modules from the adopt plugin.

Adopt scaffolders reuse helpers under ``shared/scripts/lib/`` without importing
them as the ``lib`` package — that would shadow the adopt plugin's own ``lib/``.
The idiom is ADR-045's ``spec_from_file_location``, but a naive copy of it has
two sharp edges this helper removes once for every caller (trg-a67aa561):

- ``spec_from_file_location`` returns a *non-None* spec (with a non-None loader)
  for a path that does not exist, so a missing ``shared/`` tree surfaces as a
  bare ``FileNotFoundError`` out of ``exec_module`` — on the documented
  plugins-without-``shared/`` install that is a confusing crash. Guard with
  ``is_file()`` and raise a **named** ``ImportError`` instead.
- Registering the module in ``sys.modules`` *before* ``exec_module`` is REQUIRED
  for a shared module whose ``@dataclass`` (or other PEP-563 string annotation)
  resolves its own ``__module__`` via ``sys.modules`` during exec — a file-path
  load otherwise leaves it unregistered and raises ``AttributeError`` (see
  ``gitattributes_union``). But registering before exec and NOT cleaning up on
  failure poisons the cache: a raising ``exec_module`` leaves a half-initialised
  module memoised under the sentinel, so every later call returns the broken
  module instead of re-raising. This helper does both — register before exec,
  then pop on a failing exec — so it is correct for every caller.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# parents[0]=lib [1]=scripts [2]=shipwright-adopt [3]=plugins [4]=<repo root>.
_REPO_ROOT = Path(__file__).resolve().parents[4]


def load_shared_module(relative_path: str, sentinel: str) -> ModuleType:
    """Load ``shared/<relative_path>`` under ``sentinel`` without polluting ``lib``.

    ``relative_path`` is POSIX-style, relative to the repo's ``shared/`` tree
    (e.g. ``"scripts/lib/bloat_baseline.py"``). ``sentinel`` is the unique
    ``sys.modules`` key the caller owns. Returns the executed module, cached
    under ``sentinel`` so repeated calls are a cache hit.

    Raises ``ImportError`` — never a bare ``FileNotFoundError`` — when the
    ``shared/`` tree is absent, naming the missing dependency so the
    plugins-without-``shared/`` install fails legibly. A raising ``exec_module``
    propagates and the sentinel is popped from ``sys.modules`` (no half-built
    module is memoised), so a later retry re-raises rather than returning a
    broken module.
    """
    cached = sys.modules.get(sentinel)
    if cached is not None:
        return cached
    file_path = _REPO_ROOT.joinpath("shared", *relative_path.split("/"))
    if not file_path.is_file():
        raise ImportError(
            f"shared helper not found at {file_path} — the shipwright `shared/` "
            "tree must sit alongside the adopt plugin"
        )
    spec = importlib.util.spec_from_file_location(sentinel, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec so a @dataclass / PEP-563 annotation in the shared
    # module can resolve its own __module__ via sys.modules (gitattributes_union
    # relies on this). Pop on a failing exec so a half-initialised module is
    # never memoised — the cache-poisoning the naive per-file loaders risked.
    sys.modules[sentinel] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(sentinel, None)
        raise
    return module
