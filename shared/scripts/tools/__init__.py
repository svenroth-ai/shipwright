"""Shipwright shared tools package.

Historically this was a namespace package (implicit); the explicit
``__init__.py`` was added so regular-package ``tools`` modules living
inside individual plugins (e.g. ``plugins/shipwright-compliance/scripts/
tools/``) do not shadow this package when both end up on ``sys.path``.
Python's import machinery prefers a regular package over a namespace
package wherever each sits on ``sys.path``, so without this file a
plugin-level regular ``tools`` won that contest outright. With it, both
sides are regular packages and the earlier ``sys.path`` entry wins.

That is as far as it goes, and the limit matters (see
``shared/contracts/compliance.py``): ``sys.path`` decides only the FIRST
import. A regular package is cached in ``sys.modules`` from then on and
never re-resolves, so once one tree has claimed ``tools`` — or
``scripts.tools``, or ``lib`` — no later ``sys.path`` insertion can hand
the name to another tree. That is why this repo runs one test root per
pytest process rather than trying to order its way out of the conflict.

Adding this file is strictly additive: nothing that worked with the
namespace form stops working — every existing import path
(``from tools.verifiers.common import X`` etc.) still resolves, and
plugin-level regular ``tools`` packages continue to work in isolation.
"""
