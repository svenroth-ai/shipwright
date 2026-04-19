"""Shipwright shared tools package.

Historically this was a namespace package (implicit); the explicit
``__init__.py`` was added so regular-package ``tools`` modules living
inside individual plugins (e.g. ``plugins/shipwright-compliance/scripts/
tools/``) do not shadow this package when both end up on ``sys.path``.
Python's import machinery prefers a regular package over a namespace
package regardless of ``sys.path`` order; having a regular ``__init__``
here lets plain sys.path ordering resolve the conflict.

Adding this file is strictly additive: nothing that worked with the
namespace form stops working — every existing import path
(``from tools.verifiers.common import X`` etc.) still resolves, and
plugin-level regular ``tools`` packages continue to work in isolation.
"""
