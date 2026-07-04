"""_html_styles — CSS + document-skeleton constants for the HTML report.

Extracted from :mod:`html_report` (cohesive split: keeps the render logic —
where the escape-only security seam lives — focused and under the 300-LOC gate).
The report embeds **zero binary assets** (Gemini #4): grade medallion, status
pills and badges are drawn with CSS + text, so ``<img>`` is never emitted and no
``data:``/``url()`` asset ingestion is needed. Theme is pure CSS
(``prefers-color-scheme``) — no inline JS, so no repo data reaches a JS context.
"""

from __future__ import annotations

# Restrictive meta CSP (plan §14 A). ``default-src 'none'`` blocks every
# external request class (scripts, fetch, frames, fonts); only inline styles and
# ``data:`` images are permitted, and the report emits neither script nor image.
# NOTE: a ``<meta http-equiv>`` CSP is best-effort defense-in-depth — some
# browsers do not enforce it for ``file://``-opened documents, which is how this
# lead-magnet report is typically viewed. The load-bearing guarantee is the
# escape-only output (html_report), NOT the CSP; the CSP is the second layer.
META_CSP = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
    "base-uri 'none'; form-action 'none'"
)

STYLES = """
:root {
  --bg: #f4f6f9; --panel: #ffffff; --ink: #12181f; --muted: #5b6773;
  --line: #e2e7ee; --accent: #2f6df6; --shadow: 0 1px 2px rgba(16,24,32,.06),
    0 8px 24px rgba(16,24,32,.06);
  --ok: #16794a; --ok-bg: #e7f5ee; --gap: #9a6a05; --gap-bg: #fbf1dc;
  --na: #5b6773; --na-bg: #eef1f5;
  --g-a: #16794a; --g-b: #2f6df6; --g-c: #9a6a05; --g-d: #b4530f; --g-f: #b3261e;
  --g-na: #5b6773;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1217; --panel: #161c24; --ink: #e8edf3; --muted: #9aa7b4;
    --line: #263039; --accent: #6ea0ff; --shadow: 0 1px 2px rgba(0,0,0,.4),
      0 8px 24px rgba(0,0,0,.35);
    --ok: #5fd39a; --ok-bg: #10331f; --gap: #e8b74a; --gap-bg: #33290c;
    --na: #9aa7b4; --na-bg: #1d242c;
    --g-a: #5fd39a; --g-b: #6ea0ff; --g-c: #e8b74a; --g-d: #f0894a; --g-f: #f0716a;
    --g-na: #9aa7b4;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page { max-width: 940px; margin: 0 auto; padding: 32px 20px 56px; }
.section-title { font-size: 15px; letter-spacing: .04em; text-transform: uppercase;
  color: var(--muted); margin: 34px 0 14px; }
.eyebrow { font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); }
h2, h3 { margin: 0; }
p { margin: 0; overflow-wrap: anywhere; }
.scroll-x { overflow-x: auto; -webkit-overflow-scrolling: touch; }

/* Hero */
.hero { display: flex; gap: 24px; align-items: center; background: var(--panel);
  border: 1px solid var(--line); border-radius: 18px; padding: 26px 28px;
  box-shadow: var(--shadow); }
.grade { flex: 0 0 auto; width: 108px; height: 108px; border-radius: 24px;
  display: grid; place-items: center; font-size: 62px; font-weight: 800;
  color: #fff; line-height: 1; }
.grade-a { background: var(--g-a); } .grade-b { background: var(--g-b); }
.grade-c { background: var(--g-c); } .grade-d { background: var(--g-d); }
.grade-f { background: var(--g-f); } .grade-na { background: var(--g-na); }
.hero-body { flex: 1 1 auto; min-width: 0; }
.score-row { display: flex; align-items: baseline; gap: 4px; margin: 2px 0 6px; }
.score { font-size: 40px; font-weight: 750; }
.score-max { font-size: 17px; color: var(--muted); }
.verdict { font-size: 16px; overflow-wrap: anywhere; }
.badges { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
.badge { font-size: 12px; padding: 3px 10px; border-radius: 999px;
  background: var(--na-bg); color: var(--muted); border: 1px solid var(--line); }
.badge-mode { text-transform: capitalize; color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }
.target { margin-top: 12px; font-size: 13px; color: var(--muted);
  overflow-wrap: anywhere; }

/* Dimension cards */
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill,
  minmax(272px, 1fr)); gap: 14px; min-width: 272px; }
.dim-card { background: var(--panel); border: 1px solid var(--line);
  border-left: 4px solid var(--na); border-radius: 14px; padding: 16px 18px;
  box-shadow: var(--shadow); }
.dim-card.status-ok { border-left-color: var(--ok); }
.dim-card.status-gap { border-left-color: var(--gap); }
.dim-card.status-na { border-left-color: var(--na); }
.dim-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.pill { font-size: 11px; font-weight: 700; letter-spacing: .03em; padding: 2px 8px;
  border-radius: 6px; }
.pill.status-ok { color: var(--ok); background: var(--ok-bg); }
.pill.status-gap { color: var(--gap); background: var(--gap-bg); }
.pill.status-na { color: var(--na); background: var(--na-bg); }
.weight { font-size: 12px; color: var(--muted); }
.dim-score { margin-left: auto; font-variant-numeric: tabular-nums;
  font-weight: 700; }
.dim-label { font-size: 15px; margin-bottom: 4px; }
.anchor { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.detail { font-size: 13.5px; white-space: pre-wrap; overflow-wrap: anywhere; }
.prov { margin-top: 10px; font-size: 11.5px; color: var(--muted);
  overflow-wrap: anywhere; }
.disabled-enrich { margin-top: 6px; font-size: 11.5px; color: var(--accent);
  overflow-wrap: anywhere; }

/* Panels */
.funnel, .cta { background: var(--panel); border: 1px solid var(--line);
  border-radius: 14px; padding: 18px 20px; box-shadow: var(--shadow); }
.panel-lede, .cta-copy { color: var(--muted); font-size: 14px; margin-bottom: 10px;
  overflow-wrap: anywhere; }
.light-list { margin: 0; padding-left: 20px; }
.light-list li { margin: 4px 0; }
.reasons, .reasons li { overflow-wrap: anywhere; }
.disclaimer { margin-top: 22px; background: var(--na-bg); border: 1px solid
  var(--line); border-radius: 12px; padding: 14px 16px; font-size: 13.5px;
  color: var(--muted); overflow-wrap: anywhere; }
.disc-title { color: var(--ink); }
.provenance { margin-top: 18px; font-size: 12.5px; color: var(--muted); }
.prov-row { display: flex; gap: 8px; padding: 3px 0; overflow-wrap: anywhere; }
.prov-row .k { flex: 0 0 auto; color: var(--muted); }
.prov-row .v { overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.cta { margin-top: 24px; border-color: color-mix(in srgb, var(--accent) 45%,
  var(--line)); }
.cta-title { font-size: 18px; margin-bottom: 6px; }
.cta-chip { display: inline-block; margin-top: 6px; padding: 8px 16px;
  border-radius: 999px; background: var(--accent); color: #fff; font-weight: 650;
  font-size: 13px; }
.page-footer { margin-top: 30px; text-align: center; font-size: 12px;
  color: var(--muted); }
@media (max-width: 560px) {
  .hero { flex-direction: column; text-align: center; align-items: center; }
  .badges { justify-content: center; }
}
"""
