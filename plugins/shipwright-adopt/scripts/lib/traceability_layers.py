"""Adopt ``required_layers`` ambiguity resolution (traceability TT7, Spec §11-R5).

Pure, total, prompt-free. When adopt reverse-engineers FRs, some have no author-chosen
``Layers`` — the collector infers them (``inferred_legacy`` / ``defaulted_legacy``). The
interactive path would ask the operator about those; an UNATTENDED run must resolve them
against P1's predeclared-decision fixture instead and **never stall** (binding). This
module classifies which FRs are ambiguous (cell authorship only — it does NOT re-infer
layers; the collector owns that, no fork) and maps each to a resolution.

Imports NO ``lib`` package (ADR-045) — split out of ``traceability_baseline`` only to
keep both modules under the 300-LOC source cap.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_FR_ROW_RE = re.compile(r"^FR-\d+\.\d+$")
_INFERRED_MARKER_RE = re.compile(r"\(\s*inferred\s*\)", re.IGNORECASE)
# Split a markdown table row on UNESCAPED pipes only, so a cell containing an escaped
# pipe (``filter by status \| priority`` — plausible in a reverse-engineered Description)
# does NOT shift the columns and clobber a neighbour (doubt MED#1). ``\|`` stays in-cell.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _split_row(stripped_line: str) -> list[str]:
    """Split a ``|``-delimited table row into stripped cells, honouring ``\\|`` escapes."""
    inner = stripped_line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [c.strip() for c in _UNESCAPED_PIPE_RE.split(inner)]


def _layers_index(cells: list[str]) -> int | None:
    low = [c.lower() for c in cells]
    if "priority" not in low:
        return None
    return low.index("layers") if "layers" in low else (low.index("layer") if "layer" in low else None)


@dataclass(frozen=True)
class LayerResolution:
    """One ``required_layers`` ambiguity resolution — pure record, no I/O.

    ``resolved_from`` is ``predeclared_decision`` when P1's canned fixture supplied the
    answer (unattended path), else ``inference_default`` (no fixture answer → defer to
    the collector's inference; NEVER prompt). ``provenance`` mirrors the requirement-model
    vocab (explicit | inferred_legacy | defaulted_legacy).
    """

    key: str
    fr_id: str
    required_layers: list[str]
    provenance: str
    resolved_from: str


def find_ambiguous_frs(spec_text: str, namespace: str) -> list[dict]:
    """Return the ACTIVE FRs whose ``Layers`` cell is not author-explicit.

    Ambiguous = empty cell OR an adopt ``(inferred)`` marker — i.e. the collector, not
    the author, chose the layers. These are the FRs the interactive path would ask about;
    unattended, they resolve against the fixture. Header-aware (reads BOTH the 4-col
    traceability + 6-col adopt shapes); classifies cell authorship only. Rows under
    ``## Removed Requirements`` are skipped.

    **``namespace`` is the SPLIT-NAME here, and that is deliberate — do not "fix" it.**
    The emitted ``key`` (``app::FR-03.02``) looks like a traceability-manifest key and is
    not one: it never joins the manifest. It is the lookup key of the adopt *decisions*
    map (``load_decisions`` → ``answers``), a user-authored file that operators and
    fixtures already have on disk. Campaign S3 moved the MANIFEST key to an id-derived
    namespace (``03::FR-03.02``); applying that here would silently stop matching every
    existing predeclared decision file. The two key forms diverge on purpose.
    """
    out: list[dict] = []
    layers_idx: int | None = None
    header_count = 0
    in_removed = False
    for line in spec_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_removed = stripped.lstrip("#").strip().lower().startswith("removed requirements")
            continue
        if not stripped.startswith("|"):
            continue
        cells = _split_row(stripped)
        if not cells:
            continue
        idx = _layers_index(cells)
        if idx is not None and not _FR_ROW_RE.match(cells[0]):
            layers_idx, header_count = idx, len(cells)
            continue
        if in_removed or not _FR_ROW_RE.match(cells[0]):
            continue
        # Guard a row whose cell-count differs from the header (an un-escaped pipe shifted
        # the columns): skip it rather than read the wrong cell as Layers (doubt MED#1).
        if header_count and len(cells) != header_count:
            continue
        cell = cells[layers_idx].strip() if layers_idx is not None and layers_idx < len(cells) else ""
        if cell and not _INFERRED_MARKER_RE.search(cell):
            continue  # author-explicit → not ambiguous
        title = cells[1] if len(cells) > 1 else ""
        out.append({"key": f"{namespace}::{cells[0]}", "id": cells[0], "title": title})
    return out


def load_decisions(path: Path | None) -> dict:
    """Load P1's predeclared adopt-ambiguity answers (``answers`` map), or ``{}``.

    A missing/malformed file returns ``{}`` — an unattended run with no fixture must
    still proceed (defaulting), never crash.
    """
    if path is None or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data.get("answers", {}) if isinstance(data, dict) else {}


def apply_layer_decisions_to_spec(spec_path: Path, resolutions: list[LayerResolution]) -> int:
    """Write predeclared-decision layers back into the spec's ``Layers`` cells (O1).

    A predeclared decision is authoritative over auto-inference, so it must reach the
    spec BEFORE Step F's collector runs — else the operator's choice is silently
    discarded. Rewrites the ``Layers`` cell of each FR resolved ``predeclared_decision``
    (with non-empty layers) to ``<layers> (inferred)``. The ``(inferred)`` marker is stamped
    for BOTH ``inferred_legacy`` and ``defaulted_legacy`` decisions (a deliberate collapse —
    both route to advisory ``inferred_legacy``, never a false hard gate; the exact provenance
    survives in the ``layer_resolutions`` summary). Robust on a real repo's spec.md (doubt
    MED#1): honours ``\\|`` escapes + guards a mis-columned row, preserves each line's original
    ending (no CRLF→LF churn on a Windows spec), and is IDEMPOTENT (an unchanged cell is not
    rewritten, so a re-adopt writes nothing). Returns the count of cells CHANGED.
    """
    decided = {r.fr_id: r.required_layers for r in resolutions
               if r.resolved_from == "predeclared_decision" and r.required_layers}
    if not decided:
        return 0
    # Read RAW bytes (NOT read_text, whose universal-newline translation would silently
    # LF-normalise a CRLF spec; and read_text(newline=...) is 3.13-only) — keepends then
    # preserves each line's true CRLF/LF ending (TT6 ADR-104 C1 pattern).
    raw_lines = spec_path.read_bytes().decode("utf-8").splitlines(keepends=True)
    layers_idx: int | None = None
    header_count = 0
    written = 0
    for i, raw in enumerate(raw_lines):
        body = raw.rstrip("\r\n")
        ending = raw[len(body):]                     # "" | "\n" | "\r\n" — preserved verbatim
        stripped = body.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_row(stripped)
        if not cells:
            continue
        idx = _layers_index(cells)
        if idx is not None and not _FR_ROW_RE.match(cells[0]):
            layers_idx, header_count = idx, len(cells)
            continue
        if layers_idx is None or not _FR_ROW_RE.match(cells[0]) or cells[0] not in decided:
            continue
        if (header_count and len(cells) != header_count) or layers_idx >= len(cells):
            continue                                  # mis-columned row → leave it alone
        new_cell = f"{', '.join(decided[cells[0]])} (inferred)"
        if cells[layers_idx] == new_cell:
            continue                                  # already resolved → idempotent no-op
        cells[layers_idx] = new_cell
        raw_lines[i] = "| " + " | ".join(cells) + " |" + ending
        written += 1
    if written:
        spec_path.write_bytes("".join(raw_lines).encode("utf-8"))
    return written


def resolve_layer_ambiguities(ambiguous_frs: list[dict], decisions: dict) -> list[LayerResolution]:
    """Resolve every ambiguous FR WITHOUT stalling (Spec §11-R5, binding).

    Pure + total: returns exactly one resolution per input FR. A predeclared answer
    (``decisions[key]``) is honoured (its ``decision`` provenance + ``required_layers``);
    otherwise the FR defers to the collector's inference (``inference_default``). It NEVER
    prompts — the interactive branch (AskUserQuestion) lives in the SKILL, not here.
    """
    resolutions: list[LayerResolution] = []
    for fr in ambiguous_frs:
        answer = decisions.get(fr["key"])
        if answer:
            resolutions.append(LayerResolution(
                key=fr["key"], fr_id=fr["id"],
                required_layers=list(answer.get("required_layers", [])),
                provenance=answer.get("decision", "inferred_legacy"),
                resolved_from="predeclared_decision",
            ))
        else:
            resolutions.append(LayerResolution(
                key=fr["key"], fr_id=fr["id"], required_layers=[],
                provenance="", resolved_from="inference_default",
            ))
    return resolutions


__all__ = [
    "LayerResolution", "apply_layer_decisions_to_spec", "find_ambiguous_frs",
    "load_decisions", "resolve_layer_ambiguities",
]
