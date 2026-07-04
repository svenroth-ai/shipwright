# Iterate: G3 — Stunning self-contained HTML report + terminal card

- **Run ID:** iterate-2026-07-04-grade-g3-html-report
- **Campaign:** 2026-07-03-shipwright-grade / sub-iterate **G3**
- **Intent:** FEATURE · **Complexity:** medium
- **Spec (locked):** `.shipwright/planning/iterate/campaigns/2026-07-03-shipwright-grade/sub-iterates/G3-html-report.md`
- **Design:** `Spec/shipwright-grade-plan.md` §7 + §14 A.

## Spec Impact
**NONE** (framework/grader tooling — consistent with G1/G2's FR-gate
classification). This adds a new `html` output format off the existing typed
`report_model` view-model: no engine change, no change to the scoring path, and
the existing terminal/markdown renderers' contract is byte-identical (the
terminal card already stripped ANSI/control/OSC-8/bidi via `sanitize.one_line`;
G3 only adds a defensive grade/mode wrap that is a no-op for the enum values).
No **existing framework FR** is touched — the grader is standalone read-only
tooling — so the F5b FR-gate takes the No-FR branch (`change_type: tooling`),
matching the G1 and G2 finalize events.

## Mini-Plan

**The headline requirement is security, not polish.** The HTML report renders
UNTRUSTED repo strings (dir name, remote owner/repo, and — once G2 network
enrichment is on — SARIF messages / PR titles). Escape-only templating is the
#1 AC.

New modules (each ≤300 LOC):
1. `scripts/lib/html_report.py` — `render_html(model, *, generated_at=None) -> str`.
   Builds the document through a tiny **auto-escaping element builder**
   (`el(tag, *children, **attrs)` returning a `_Raw` marker; a `_Raw` child is
   emitted verbatim, **any other child is HTML-escaped as a text node by
   default**). This is the structural fix for the external-review High finding
   (both models): safety no longer depends on remembering `_h()` at every seam —
   a forgotten wrap on a model string is auto-escaped, not injected. Attribute
   values are always escaped. Text-node cleaning uses `sanitize.strip_terminal`
   (strips ANSI/OSC-8/bidi/control, **preserves newlines** — GPT #4/Gemini #2:
   don't flatten multi-line reasons) + `html.escape`; CSS `white-space: pre-wrap`
   + `overflow-wrap: anywhere` render the newlines and defuse long hostile tokens.
   ZERO inline JS (theme via CSS `@media (prefers-color-scheme)`) → no repo data
   ever reaches a script/JS/event-handler context. NO model-driven `href` — the
   open-standard `anchor` renders as text; the CTA is a non-functional placeholder.
2. `scripts/lib/_html_styles.py` — the CSS constant (`STYLES`) + the document
   skeleton constants (DOCTYPE + restrictive meta CSP). Cohesive extraction that
   keeps `html_report.py` focused and under the 300-LOC gate. Zero binary assets
   (Gemini #4): status/badges are CSS + text, no `<img>`.

**Terminal card (clarifies review #5):** `render_terminal.py` ALREADY emits a
compact card off the same model and ALREADY strips ANSI/OSC-8/bidi/control via
`sanitize.one_line`. G3 keeps its contract unchanged and only **adds** the
missing snapshot + control-stripping security tests the AC asks for.

Sections (all from the model): Hero (letter + score + one-line verdict +
heuristic/authoritative badge + "N of M controls measured") · Dimension cards
(signal detail + open-standard anchor + ok/gap/**N/A** status + per-dimension
provenance source/mode/freshness/sampled) · "Controls Shipwright would light up"
funnel panel for the n/a dims · Top 1–3 fixable reasons · Honest-ceiling
disclaimer (C-R6) + `verified_from` provenance stamp + network provenance line +
CTA placeholder.

Determinism: `render_html` takes `generated_at` explicitly; the scored content is
byte-identical regardless of it, and the timestamp appears ONLY in the footer.
The CLI passes the wall-clock; tests pass a fixed value → stable snapshots.

3. Wire `--format html` into `scripts/tools/grade.py`.

**Alternative considered:** a Jinja2 template. Rejected — adds a dependency, and a
templating engine's auto-escape is a weaker guarantee here than a tiny audited
"one escaping seam" that a security test can exhaustively pin. Escape-only string
building keeps the trusted/untrusted boundary a single grep-able function.

## Confidence Calibration
- **Boundaries touched:** HTML output boundary — untrusted repo strings
  (`target_display`, network owner/repo, dimension details, reasons,
  `verified_from`) interpolated into an HTML document. XSS/Trojan-source surface;
  the boundary contract is "rendered inert."
- **Empirical probes run:**
  - Rendered a **real** HTML report for a live sample git repo via the CLI
    (`grade.py … --format html`, 11,985 bytes) → a grep for every
    external-request surface (`<script`, `src="http`, `href="http`, `@import`,
    `url(http`, `srcset=`, `action=`, `ping=`) returned **empty**; a
    tag-balance parser reported **0 unclosed / 0 mismatched** tags.
  - Fed hostile payloads (`<script>`, `"><img onerror=`, `javascript:`, bidi
    override U+202E, ANSI CSI, OSC-8 hyperlink, NUL/BEL) through **every**
    text-bearing model field → escaped form present, raw form + control bytes
    absent (`test_every_text_field_routes_through_escaper`).
  - Determinism probe: two renders with different footer timestamps → scored
    content byte-identical after nulling the stamp
    (`test_scored_content_byte_identical_across_timestamps`).
- **Test Completeness Ledger:** all 8 AC behaviors testable ⇒ tested; 0
  untested-testable (machine-readable block in `shipwright_test_results.json`).

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | Self-contained HTML, no external fetch, meta CSP | tested | `TestSelfContained::{test_is_a_full_html_document,test_restrictive_meta_csp,test_no_external_request_surface}` + `test_grade_cli::test_html_format_emits_self_contained_document` |
  | All sections (hero/cards/funnel/reasons/disclaimer/provenance/CTA) | tested | `TestSections::*` + `test_would_light_panel_lists_na_dims` |
  | Theme-aware + responsive + wide-content scroll | tested | `TestThemeAndResponsive::*` |
  | Deterministic byte-identical scored content | tested | `TestDeterminism::*` |
  | Escape-only: XSS/onerror/`javascript:`/bidi/ANSI/OSC-8 inert (HTML) | tested | `TestEscapeOnly::*` |
  | Terminal card control-stripped | tested | `test_render_terminal::TestTerminalControlStripping::*` |
  | Snapshot stability (HTML + terminal) | tested | `test_render_snapshots::*` (golden files) |
  | n/a → "N/A", excluded, in funnel (never failing 0) + reasons ≤3 | tested | `TestNaSemantics::*` |

- **Confidence-pattern check:**
  - *Asymptote (depth):* the escape seam is **structural** (`el`/`_Raw`
    escape-by-default), not per-call discipline — `test_every_text_field_routes_
    through_escaper` walks every model text field and proves none reaches the
    document raw. Depth bounded by one auditable seam, addressing the external
    review's sole High finding.
  - *Coverage (breadth):* 8 ACs enumerated → each ≥1 test; +28 new tests; full
    plugin suite 213→**215** green; ruff clean; both new modules ≤300 LOC.
  - *Integration composition:* **N/A** — G3 is a pure renderer off an existing
    view-model; touches no `cross_component` machinery (no merge/hook/pipeline
    seam), so no integration-coverage behavior is required.
