/*
 * Settings — minimal stub for Plan D'' variant-a.
 *
 * The pre-Plan-D'' SettingsPage managed chat-mode / autonomy / phase-mapping
 * / model selector config. All of those vanish in the external-launch
 * architecture (the user's own Claude client owns them).
 *
 * This stub is intentionally near-empty. A real "Launcher preferences" tab
 * (default launcher choice, VSCode executable override, claude executable
 * override, plugin dir list) belongs in a follow-up iterate when the
 * Terminal + VSCode launchers actually ship.
 *
 * Iterate 3 remediation v2 Phase 0 (2026-04-21) — visual rebuild:
 *   - Sidebar-consistent header (matches InboxPage: 24px/700 title +
 *     muted subtitle, 20px/32px padding, surface bg + bottom border).
 *   - Content wrapped in .page-container (1280 max-width, centered).
 *   - Each settings group is a warm-beige card (surface bg, border,
 *     shadow-sm, 20px padding). No neutral-* / gray-* classes.
 *   - No new CSS tokens introduced — only palette tokens already in
 *     index.css are used.
 */

export default function SettingsPage() {
  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "var(--color-bg)" }}
      data-testid="settings-page"
    >
      {/* Header — mirrors InboxPage header for consistency across pages.
          R1/R2 (iterate 3.7e-a Foundation, 2026-04-22): header content wrapped
          inside `.page-container` so the title left-edge aligns with the
          settings cards in the body (same 24 px L/R padding, 1280 max-width). */}
      <div
        style={{
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <header
          className="page-container flex items-center justify-between"
          style={{ paddingTop: "20px", paddingBottom: "20px" }}
        >
          <div className="flex flex-col gap-[2px]">
            <h1
              className="font-bold"
              style={{
                fontSize: "24px",
                color: "var(--color-text)",
                letterSpacing: "-0.01em",
              }}
            >
              Settings
            </h1>
            <p
              className="font-medium"
              style={{
                fontSize: "13px",
                color: "var(--color-muted)",
              }}
            >
              Configure preferences in your own Claude client.
            </p>
          </div>
        </header>
      </div>

      {/* Body — .page-container centers to 1280px and applies 24px
          horizontal padding. Top padding gives a little breathing room
          under the header. */}
      <div
        className="page-container flex flex-col gap-4"
        style={{ paddingTop: "24px", paddingBottom: "24px" }}
      >
        <section
          className="flex flex-col gap-2"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-card)",
            boxShadow: "var(--shadow-sm)",
            padding: "20px",
          }}
        >
          <h2
            className="font-semibold"
            style={{
              fontSize: "15px",
              color: "var(--color-text)",
              margin: 0,
            }}
          >
            Launcher preferences
          </h2>
          <p
            style={{
              fontSize: "13px",
              color: "var(--color-muted)",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            Terminal / VSCode / Desktop launcher overrides land in a future
            iterate. Today the &ldquo;Copy command&rdquo; launcher is the
            only available path.
          </p>
        </section>

        {/* Section 03 (iterate 3) — actions.json stub link. Read-only; the
            full in-app editor is deferred past iterate 3. */}
        <section
          className="flex flex-col gap-2"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-card)",
            boxShadow: "var(--shadow-sm)",
            padding: "20px",
          }}
          data-testid="settings-configure-actions"
        >
          <h2
            className="font-semibold"
            style={{
              fontSize: "15px",
              color: "var(--color-text)",
              margin: 0,
            }}
          >
            Configure actions
          </h2>
          <p
            style={{
              fontSize: "13px",
              color: "var(--color-muted)",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            Each project declares its <code
              style={{
                background: "var(--color-muted-bg)",
                borderRadius: "4px",
                padding: "1px 6px",
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                fontSize: "12px",
              }}
            >+ New ▾</code> dropdown entries, phase
            allowlist, and preview gate in{" "}
            <code
              style={{
                background: "var(--color-muted-bg)",
                borderRadius: "4px",
                padding: "1px 6px",
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                fontSize: "12px",
              }}
            >
              &lt;project.path&gt;/.webui/actions.json
            </code>
            . The in-app editor is coming in a future iterate.
          </p>
        </section>
      </div>
    </div>
  );
}
