"""Pure merge-logic SSoT for Shipwright-managed ``.gitattributes`` rules.

The monorepo root ``.gitattributes`` declares ``merge=union`` for the two
append-only JSONL logs (``shipwright_events.jsonl``, ``.shipwright/triage.jsonl``)
AND the two curated agent-docs whose ``## …Updates``/``## Learnings`` sections are
bullet-prepended by parallel iterates (``CURATED_DOC_UNION_PATHS``), so concurrent
appends auto-line-union instead of producing conflict markers. That protection was
**monorepo-local** — so every adopted repo (WebUI, leadwright, any end-user
project) fell back to git's default conflict behavior. This module is the single
source of merge logic that lands it everywhere. The fragment also marks immutable
per-run test evidence ``-text -diff`` so Git preserves its exact bytes and does
not apply text whitespace diagnostics:

* :func:`merge_into` — pure, idempotent merge of the union fragment into an
  existing ``.gitattributes`` (never clobbers user entries). Consumed by the
  adopt scaffolder (``gitattributes_scaffolder.py``, loaded by file path to dodge
  the adopt-``lib`` / shared-``lib`` collision) and by the self-heal sibling.
* The guarded git commit-path that backfills these lines into an already-adopted
  repo (``self_heal_gitattributes``) lives in ``lib.gitattributes_selfheal`` —
  split out so each module stays within the bloat limit.

Module top-level is import-pure (stdlib only): the adopt scaffolder loads this
file by absolute path, so it must not ``from lib.* import`` at module scope. (The
commit-path sibling is imported normally, so it may ``from lib.* import``.)
"""

from __future__ import annotations

from pathlib import Path

# Layout (identical in the dev repo and the ~/.claude marketplace cache):
#   <root>/shared/scripts/lib/gitattributes_union.py   ← this file
#   <root>/shared/templates/gitattributes-union.template
# parents[0]=lib, [1]=scripts, [2]=shared, [3]=<root>.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where the rendered driver lives in a managed repo (repo root).
GITATTRIBUTES_PATH = ".gitattributes"
#: SSoT for the fragment content. The drift test pins its shape to UNION_PATHS.
TEMPLATE_PATH = "shared/templates/gitattributes-union.template"

#: The tracked append-log artifacts that need the line-union merge driver.
#: HARD-CODED here (not imported from ``lib.churn_merge``) so this module stays
#: import-pure for the file-path loader; the drift test asserts this equals
#: ``{churn_merge.EVENTS_LOG, churn_merge.TRIAGE_LOG}`` so the two cannot diverge.
#: This is also the "is this a managed repo?" signal for the self-heal sibling.
UNION_PATHS: tuple[str, ...] = ("shipwright_events.jsonl", ".shipwright/triage.jsonl")

#: Curated agent-docs whose ``## …Updates`` / ``## Learnings`` append-sections
#: collide when parallel iterates each prepend a bullet (a DISTINCT category from
#: the JSONL logs: curated prose, NOT in ``CHURN_ALLOWLIST``, never regenerated).
#: ``merge=union`` keeps both bullets (honored server-side). Rationale + the
#: line-union garble caveat: docs/hooks-and-pipeline.md + the template comment.
CURATED_DOC_UNION_PATHS: tuple[str, ...] = (
    ".shipwright/agent_docs/architecture.md",
    ".shipwright/agent_docs/conventions.md",
)

#: Every path receiving ``merge=union`` (both union categories). The managed-repo
#: probe stays on ``UNION_PATHS`` (the JSONL logs).
ALL_UNION_PATHS: tuple[str, ...] = (*UNION_PATHS, *CURATED_DOC_UNION_PATHS)

#: Immutable JSON evidence is intentionally NOT a Git text file: source EOL bytes
#: are part of the evidence contract and must survive ``core.autocrlf``.
NON_TEXT_PATHS: tuple[str, ...] = (
    "/.shipwright/agent_docs/iterates/*.test-results.json",
)

#: Every path/pattern declared by the managed fragment.
ALL_MANAGED_PATHS: tuple[str, ...] = (*ALL_UNION_PATHS, *NON_TEXT_PATHS)

#: First line of the template — the sentinel that marks our managed block, so a
#: partial backfill appends only the missing lines without a duplicate header.
MANAGED_MARKER = (
    "# Shipwright append-log union merge driver (managed block — do not hand-edit)."
)


def load_fragment() -> str:
    """Return the canonical fragment text (LF-normalised, trailing newline).

    Raises ``FileNotFoundError`` loudly if the template is missing — that is a
    development-time bug (a managed repo never reaches this code path), mirroring
    ``gitleaks_config_scaffolder``'s loud-failure contract.
    """
    template = _REPO_ROOT / TEMPLATE_PATH
    if not template.exists():
        raise FileNotFoundError(
            f"gitattributes union template missing at {template}. "
            f"shared/scripts/lib/gitattributes_union.py declares "
            f"TEMPLATE_PATH={TEMPLATE_PATH!r} but no such file exists in the tree."
        )
    text = template.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _union_line(path: str) -> str:
    return f"{path} merge=union"


def _declares_union(text: str, path: str) -> bool:
    """True when ``text`` already declares ``merge=union`` for ``path``.

    Tolerant of extra attributes / surrounding whitespace; ignores comments. A
    user line like ``shipwright_events.jsonl merge=union -text`` counts as present.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        toks = line.split()
        if toks and toks[0] == path and "merge=union" in toks[1:]:
            return True
    return False


def _declares_exact_bytes(text: str, path: str) -> bool:
    """True when ``text`` disables normalization and text diffs for ``path``."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        toks = line.split()
        if toks and toks[0] == path and {"-text", "-diff"} <= set(toks[1:]):
            return True
    return False


def missing_union_paths(text: str | None) -> list[str]:
    """The subset of :data:`ALL_UNION_PATHS` not yet declared in ``text`` (both the
    JSONL append-logs and the curated agent-docs — the full fragment coverage)."""
    body = text or ""
    return [p for p in ALL_UNION_PATHS if not _declares_union(body, p)]


def missing_managed_paths(text: str | None) -> list[str]:
    """Every union or exact-byte pattern absent from the managed fragment."""
    body = text or ""
    missing = missing_union_paths(body)
    missing.extend(p for p in NON_TEXT_PATHS if not _declares_exact_bytes(body, p))
    return missing


def merge_into(existing_text: str | None) -> tuple[str, bool]:
    """Idempotently merge the union fragment into ``existing_text``.

    Returns ``(merged_text, changed)``. ``changed`` is False when every managed
    rule is already present (round-trip stable: ``merge_into(merge_into(x)[0])``
    reports ``changed=False``). An empty / whitespace-only / ``None`` input is
    treated as "no file" → the full template is returned. An existing file with
    user entries is preserved verbatim; only missing managed rules (under the
    managed marker, added once) are appended, with the file's existing EOL style.
    """
    if not existing_text or not existing_text.strip():
        return load_fragment(), True

    missing = missing_managed_paths(existing_text)
    if not missing:
        return existing_text, False

    eol = "\r\n" if "\r\n" in existing_text else "\n"
    block_lines: list[str] = []
    if MANAGED_MARKER not in existing_text:
        block_lines.append(MANAGED_MARKER)
    block_lines.extend(
        f"{p} -text -diff" if p in NON_TEXT_PATHS else _union_line(p)
        for p in missing
    )

    core = existing_text.rstrip("\r\n")
    merged = core + eol + eol + eol.join(block_lines) + eol
    return merged, True
