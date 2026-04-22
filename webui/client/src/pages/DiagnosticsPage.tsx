/*
 * Diagnostics — CLI version gate + launcher availability + session counts.
 * Backed by GET /api/diagnostics.
 *
 * iterate 3.7k (Sven UAT 2026-04-22): restyled to match Projects / Inbox /
 * Settings — full-bleed surface header strip + .page-container body +
 * warm-beige palette tokens. Previously used neutral-* / red-* / green-*
 * Tailwind defaults, which looked unstyled against the rest of the app.
 * Load-bearing testids preserved (`diagnostics-page`, `diagnostics-error`,
 * `cli-supported-badge`).
 */

import type { ReactNode } from "react";
import { useDiagnostics } from "../hooks/useDiagnostics";

export default function DiagnosticsPage() {
  const { data, error, isLoading } = useDiagnostics();

  return (
    <div
      className="flex h-full flex-col bg-[var(--color-bg)]"
      data-testid="diagnostics-page"
    >
      {/* Header — full-bleed surface bar, matches ProjectsPage geometry. */}
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
          <h1
            className="font-bold"
            style={{
              fontSize: "24px",
              color: "var(--color-text)",
              letterSpacing: "-0.01em",
            }}
          >
            Diagnostics
          </h1>
        </header>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div
          className="page-container w-full"
          style={{ paddingTop: "24px", paddingBottom: "24px" }}
        >
          {isLoading ? (
            <div
              className="text-[13px]"
              style={{ color: "var(--color-muted)", padding: "32px 0" }}
            >
              Loading diagnostics…
            </div>
          ) : error || !data ? (
            <div
              data-testid="diagnostics-error"
              role="alert"
              className="rounded-[var(--radius-card)] text-[13px]"
              style={{
                padding: "16px 20px",
                background: "var(--color-error-bg)",
                color: "var(--color-error)",
                border: "1px solid var(--color-error)",
              }}
            >
              Error loading diagnostics: {error ? String(error) : "unknown"}
            </div>
          ) : (
            <div className="flex flex-col" style={{ gap: "16px" }}>
              <Section title="Claude CLI">
                <KV
                  label="Detected"
                  value={data.claudeCli.raw || "(not found on PATH)"}
                />
                <KV
                  label="Parsed"
                  value={
                    data.claudeCli.parsed
                      ? `${data.claudeCli.parsed.major}.${data.claudeCli.parsed.minor}.${data.claudeCli.parsed.patch}`
                      : "—"
                  }
                />
                <KV
                  label="Minimum supported"
                  value={data.claudeCli.minSupported}
                />
                <KV
                  label="Supported?"
                  value={
                    <span
                      className="inline-flex items-center rounded-[999px] font-semibold"
                      style={{
                        padding: "2px 10px",
                        fontSize: "11px",
                        background: data.claudeCli.supported
                          ? "var(--color-success-bg)"
                          : "var(--color-error-bg)",
                        color: data.claudeCli.supported
                          ? "var(--color-success-text)"
                          : "var(--color-error)",
                      }}
                      data-testid="cli-supported-badge"
                    >
                      {data.claudeCli.supported ? "yes" : "no"}
                    </span>
                  }
                />
                {!data.claudeCli.supported && (
                  <div
                    className="rounded-[var(--radius-button)] text-[12px]"
                    style={{
                      marginTop: "8px",
                      padding: "10px 14px",
                      background: "var(--color-warning-bg)",
                      color: "var(--color-warning-text)",
                      border: "1px solid var(--color-warning)",
                    }}
                  >
                    Install / upgrade the Claude CLI:{" "}
                    <code>claude install latest</code>. Version ≥{" "}
                    <code>{data.claudeCli.minSupported}</code> is required.
                  </div>
                )}
              </Section>

              <Section title="Sessions">
                <KV label="Total tracked" value={data.sessions.total} />
                {Object.entries(data.sessions.byState).map(([state, count]) => (
                  <KV key={state} label={state} value={count} />
                ))}
              </Section>

              <Section title="Launchers">
                <LauncherRow
                  name="Copy"
                  available={data.launchers.copy.available}
                  reason=""
                />
                <LauncherRow
                  name="Terminal"
                  available={data.launchers.terminal.available}
                  reason={data.launchers.terminal.reason}
                />
                <LauncherRow
                  name="VSCode"
                  available={data.launchers.vscode.available}
                  reason={data.launchers.vscode.reason}
                />
                <LauncherRow
                  name="Desktop"
                  available={data.launchers.desktop.available}
                  reason={data.launchers.desktop.reason}
                />
              </Section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      className="rounded-[var(--radius-card)]"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        padding: "18px 22px",
      }}
    >
      <h2
        className="font-semibold uppercase tracking-[0.06em]"
        style={{
          fontSize: "11px",
          color: "var(--color-muted)",
          marginBottom: "12px",
        }}
      >
        {title}
      </h2>
      <div className="flex flex-col" style={{ gap: "8px" }}>
        {children}
      </div>
    </section>
  );
}

function KV({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline" style={{ gap: "12px" }}>
      <span
        className="shrink-0 text-[12px]"
        style={{ width: "170px", color: "var(--color-muted)" }}
      >
        {label}
      </span>
      <span
        className="text-[13px]"
        style={{ color: "var(--color-text)" }}
      >
        {value}
      </span>
    </div>
  );
}

function LauncherRow({
  name,
  available,
  reason,
}: {
  name: string;
  available: boolean;
  reason: string;
}) {
  return (
    <div className="flex items-baseline" style={{ gap: "12px" }}>
      <span
        className="shrink-0 text-[12px] font-semibold"
        style={{ width: "100px", color: "var(--color-text)" }}
      >
        {name}
      </span>
      <span
        className="inline-flex items-center rounded-[999px] font-semibold"
        style={{
          padding: "2px 10px",
          fontSize: "11px",
          background: available
            ? "var(--color-success-bg)"
            : "var(--color-muted-bg)",
          color: available
            ? "var(--color-success-text)"
            : "var(--color-muted)",
        }}
      >
        {available ? "available" : "unavailable"}
      </span>
      {reason && (
        <span
          className="text-[12px]"
          style={{ color: "var(--color-muted)" }}
        >
          {reason}
        </span>
      )}
    </div>
  );
}
