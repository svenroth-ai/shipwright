/*
 * Diagnostics — CLI version gate + launcher availability + session counts.
 * Backed by GET /api/diagnostics.
 */

import { useDiagnostics } from "../hooks/useDiagnostics";

export default function DiagnosticsPage() {
  const { data, error, isLoading } = useDiagnostics();

  if (isLoading) {
    return <div className="p-4 text-sm text-neutral-500">Loading diagnostics…</div>;
  }
  if (error || !data) {
    return (
      <div className="p-4 text-sm text-red-700" data-testid="diagnostics-error">
        Error loading diagnostics: {error ? String(error) : "unknown"}
      </div>
    );
  }

  const { claudeCli, sessions, launchers } = data;

  return (
    <div className="flex h-full flex-col gap-4 p-4" data-testid="diagnostics-page">
      <h1 className="text-xl font-semibold">Diagnostics</h1>

      <Section title="Claude CLI">
        <KV label="Detected" value={claudeCli.raw || "(not found on PATH)"} />
        <KV label="Parsed" value={claudeCli.parsed ? `${claudeCli.parsed.major}.${claudeCli.parsed.minor}.${claudeCli.parsed.patch}` : "—"} />
        <KV label="Minimum supported" value={claudeCli.minSupported} />
        <KV
          label="Supported?"
          value={
            <span
              className={`rounded px-2 py-0.5 text-xs font-semibold ${claudeCli.supported ? "bg-green-100 text-green-900" : "bg-red-100 text-red-900"}`}
              data-testid="cli-supported-badge"
            >
              {claudeCli.supported ? "yes" : "no"}
            </span>
          }
        />
        {!claudeCli.supported && (
          <div className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
            Install / upgrade the Claude CLI: <code>claude install latest</code>.
            Version &ge; <code>{claudeCli.minSupported}</code> is required.
          </div>
        )}
      </Section>

      <Section title="Sessions">
        <KV label="Total tracked" value={sessions.total} />
        {Object.entries(sessions.byState).map(([state, count]) => (
          <KV key={state} label={state} value={count} />
        ))}
      </Section>

      <Section title="Launchers">
        <LauncherRow name="Copy" available={launchers.copy.available} reason={""} />
        <LauncherRow name="Terminal" available={launchers.terminal.available} reason={launchers.terminal.reason} />
        <LauncherRow name="VSCode" available={launchers.vscode.available} reason={launchers.vscode.reason} />
        <LauncherRow name="Desktop" available={launchers.desktop.available} reason={launchers.desktop.reason} />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border border-neutral-200 bg-white p-3">
      <h2 className="mb-2 text-sm font-semibold text-neutral-700">{title}</h2>
      <div className="flex flex-col gap-1 text-sm">{children}</div>
    </section>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-36 shrink-0 text-xs text-neutral-500">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function LauncherRow({ name, available, reason }: { name: string; available: boolean; reason: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-24 shrink-0 text-xs font-semibold">{name}</span>
      <span
        className={`rounded px-2 py-0.5 text-xs font-semibold ${available ? "bg-green-100 text-green-900" : "bg-neutral-200 text-neutral-600"}`}
      >
        {available ? "available" : "unavailable"}
      </span>
      {reason && <span className="text-xs text-neutral-500">{reason}</span>}
    </div>
  );
}
