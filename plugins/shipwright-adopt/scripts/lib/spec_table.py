"""Render adopt's Functional Requirements table in the ONE converged shape.

Campaign "Requirements Catalog", sub-iterate S5. Adopt used to emit
``| ID | Name | Priority | Description | Source | Layers |`` and hand-format each
cell inside ``artifact_writer._render_spec_md``. Two things were wrong with that
beyond the column list:

* the shape was a *string literal in a producer*, so "both generators emit the
  same header" was only checkable by eye — it is now
  ``fr_table_shape.FR_TABLE_HEADER``, one constant, asserted by test;
* cells were interpolated unescaped, so a detected description containing ``|``
  silently split into extra columns. FV-3 (the RTM showing the wrong requirement
  text) is what that class of defect looks like once it reaches an audit
  artifact, and this producer could manufacture it from any repo whose code
  comments contain a pipe.

Lives outside ``artifact_writer`` because that module is grandfathered at its
bloat ceiling, and because the rendering rules below are worth testing directly
rather than through a whole generated document.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from lib.render_helpers import infer_required_layers

_PLACEHOLDER_DESCRIPTION = "TBD — refine via /shipwright-iterate"

#: Values that mean "we do not have this", not "we have this and it is short".
#: ``generate_adoption_artifacts`` defaults an unmatched ``source_file`` to the
#: literal ``"—"`` (it was a *display* placeholder for the old ``Source``
#: column), and a truthiness test reads that as evidence. Caught by an existing
#: merge test asserting the origin of a crawl-only route, which is exactly the
#: distinction this placeholder erases.
_ABSENT = {"", "-", "—", "–", "n/a", "none", "tbd", "?"}


def _has(value: object) -> bool:
    return str(value or "").strip().lower() not in _ABSENT


def _load_shared(name: str) -> ModuleType:
    """Load a ``shared/scripts`` module without polluting adopt's own ``lib``.

    Same sentinel technique as ``adopt_brief_intake._load_brief_intake``, and for
    the same reason: a plain import would bind ``lib`` to the shared package and
    shadow the plugin's own for the rest of the process (ADR-045).
    """
    sentinel = f"_shipwright_adopt_{name}"
    if sentinel in sys.modules:
        return sys.modules[sentinel]
    repo_root = Path(__file__).resolve().parents[4]
    candidates = (
        repo_root / "shared" / "scripts" / "lib" / f"{name}.py",
        repo_root / "shared" / "scripts" / f"{name}.py",
    )
    file_path = next((c for c in candidates if c.exists()), None)
    if file_path is None:
        # `spec_from_file_location` returns a non-None spec with a non-None
        # loader for a missing path, so the guard below cannot catch this and it
        # would surface as a bare FileNotFoundError from `exec_module`. Name the
        # missing dependency instead — the plugins-without-`shared/` install is a
        # documented, healable state.
        raise ImportError(
            f"shared module {name!r} not found under shared/scripts — this "
            "plugin needs the shipwright `shared/` tree alongside it"
        )
    spec = importlib.util.spec_from_file_location(sentinel, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    # Registered only after a successful exec, so a raising load cannot leave a
    # half-initialised module memoized for every later call.
    spec.loader.exec_module(module)
    sys.modules[sentinel] = module
    return module


def basis_for(feature: dict[str, Any]) -> str:
    """The ``Basis`` value for a detected feature (SPEC §3.2, decision D-S5-1).

    This answers campaign open question 3 — *"`enrichment` maps to
    `code`/`observed` depending on origin — is that lossy?"* — with **no**,
    because the discriminator is already present at the point the old ``Source``
    cell was rendered:

    * a feature carrying ``source_file`` was found by READING the repository
      → ``code``;
    * a feature carrying only ``url`` was found by the Playwright crawl, i.e.
      seen in the running application → ``observed``;
    * a feature with neither is a guess nobody evidenced → ``assumed``, which is
      the value that exists precisely so a guess cannot later read as fact.

    ``Source`` collapsed all three into a file path, which is why the question
    looked lossy: the loss was in the old column, not in the new vocabulary.

    Placeholder values count as ABSENT — see ``_ABSENT``. A crawl-only route
    carries ``source_file: "—"``, and treating that dash as evidence would
    label every crawled page ``code``, which is precisely backwards.
    """
    if _has(feature.get("source_file")):
        return "code"
    if _has(feature.get("url")):
        return "observed"
    return "assumed"


def render_fr_table(features: list[dict[str, Any]], *, split_name: str) -> str:
    """The full FR table — canonical header, separator, and one row per feature.

    Every ``Layers`` cell is machine-derived, so every one carries the literal
    ``(inferred)`` marker via ``render_layers``. That keeps an adopted repo's
    requirements on advisory provenance instead of collapsing them into the
    ``explicit`` hard-gate regime against test links that do not exist yet
    (SPEC §6.2). The marker is never hand-formatted here — one space short and
    the cell parses to zero layers.
    """
    shape = _load_shared("fr_table_shape")
    escape_cell = _load_shared("markdown_table").escape_cell

    lines = [shape.FR_TABLE_HEADER, shape.FR_TABLE_SEPARATOR]
    for feature in features:
        fr_id = feature.get("fr_id", "FR-01.?")
        cells = (
            fr_id,
            shape.area_for(fr_id, split_name),
            feature.get("label", feature.get("route", "?")),
            "Must",
            feature.get("description", _PLACEHOLDER_DESCRIPTION),
            basis_for(feature),
            shape.render_layers(infer_required_layers(feature), inferred=True),
        )
        lines.append("| " + " | ".join(escape_cell(c) for c in cells) + " |")

    if not features:
        # An adopted repo where detection found nothing still needs a
        # well-formed table: a header with no rows is what the reader reports as
        # `no_fr_rows`, and a placeholder row that an author can edit is more
        # useful than a state a gate has to special-case. `assumed` is the
        # honest basis for a row asserting the absence of findings.
        lines.append(
            "| " + " | ".join(escape_cell(c) for c in (
                "FR-01.01", shape.area_for("FR-01.01", split_name),
                "_no features detected_", "May",
                "Edit manually after adoption", "assumed",
                shape.render_layers(("unit",), inferred=True),
            )) + " |"
        )
    return "\n".join(lines)


__all__ = ["basis_for", "render_fr_table"]
